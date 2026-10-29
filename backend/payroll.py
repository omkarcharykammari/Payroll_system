"""Payroll runs: create -> calculate -> review -> finalize -> paid.

Frontend stepper  : Data Sync, Calculations, Review, Approval, Payment
Run status        : DRAFT (steps 1-2 done) -> REVIEWED -> FINALIZED -> PAID
                    current_step:   2          3            4           5

Safety rules enforced here
--------------------------
* One run per (company_id, year, month) - enforced per tenant company.
* DRAFT / REVIEWED runs can be edited and recalculated; FINALIZED / PAID runs cannot.
* Review and finalize re-run the maths in memory and refuse if attendance, leave,
  salary or rules changed since the last calculation ("stale" check).
* The only way back from FINALIZED is the audited ``reopen`` endpoint, and only
  while no payslip has been published. A PAID run is never reopened.
* HR can prepare and review; only an admin / owner can finalize, mark paid or reopen.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from auth import require_admin, require_staff
from database import get_db
from models import (
    ATT_ABSENT, ATT_HALF_DAY, EMP_ACTIVE, EMP_TERMINATED, LEAVE_APPROVED, PAYSLIP_DRAFT,
    PAYSLIP_PUBLISHED, RUN_DRAFT, RUN_EDITABLE, RUN_FINALIZED, RUN_PAID, RUN_REVIEWED, Attendance,
    Employee, LeaveRequest, PayrollItem, PayrollRun, Payslip, User, utcnow,
)
from payroll_engine import ZERO, PayInputs, PayResult, Rules, calculate, compute_lop_days, q2
from schemas import ItemUpdate, ReopenIn, RunCreate
from settings import load_rules
from utils import (
    daterange, holidays_between, log_audit, month_bounds, month_label, paginate, today_local,
    working_days,
)

router = APIRouter(prefix="/payroll", tags=["Payroll"])

STEPS = ["Data Sync", "Calculations", "Review", "Approval", "Payment"]
STEP_INDEX = {RUN_DRAFT: 2, RUN_REVIEWED: 3, RUN_FINALIZED: 4, RUN_PAID: 5}
ACTIONS = {
    RUN_DRAFT: ["recalculate", "review", "delete"],
    RUN_REVIEWED: ["recalculate", "finalize", "delete"],
    RUN_FINALIZED: ["mark_paid", "reopen"],
    RUN_PAID: [],
}
MONEY_FIELDS = ("basic", "hra", "allowances", "overtime_pay", "bonus", "gross", "pf", "tax",
                "lop_deduction", "professional_tax", "manual_deduction", "other_deductions", "net", "employer_pf")


def D(value) -> Decimal:
    return Decimal(str(value or 0))


def payment_status(run_status: str) -> str:
    """Labels used by the dashboard table badges (Paid / Pending / Processing)."""
    return {RUN_PAID: "Paid", RUN_FINALIZED: "Processing"}.get(run_status, "Pending")


# --------------------------------------------------------------------------- #
# Calculation context & per-employee computation
# --------------------------------------------------------------------------- #
@dataclass
class Context:
    start: date
    end: date
    rules: Rules
    working_dates: set
    attendance: dict
    leaves: dict
    today: date


def build_context(db: Session, start: date, end: date, company_id: Optional[int] = None) -> Context:
    cfg, rules = load_rules(db, company_id=company_id)
    wdates = set(working_days(start, end, cfg.weekly_off_days, holidays_between(db, start, end, company_id=company_id)))
    attendance = defaultdict(list)
    att_stmt = select(Attendance).where(Attendance.work_date.between(start, end))
    if company_id is not None:
        att_stmt = att_stmt.where(Attendance.company_id == company_id)
    for r in db.scalars(att_stmt):
        attendance[r.employee_id].append(r)
    leaves = defaultdict(list)
    leave_stmt = select(LeaveRequest).options(selectinload(LeaveRequest.leave_type)).where(
        LeaveRequest.status == LEAVE_APPROVED, LeaveRequest.start_date <= end, LeaveRequest.end_date >= start)
    if company_id is not None:
        leave_stmt = leave_stmt.where(LeaveRequest.company_id == company_id)
    for r in db.scalars(leave_stmt):
        leaves[r.employee_id].append(r)
    return Context(start, end, rules, wdates, attendance, leaves, today_local())


def eligible_employees(db: Session, start: date, end: date, company_id: Optional[int] = None) -> list[Employee]:
    stmt = (select(Employee)
            .options(selectinload(Employee.salary), selectinload(Employee.bank), selectinload(Employee.department))
            .where(Employee.joining_date <= end, Employee.status.in_([EMP_ACTIVE, EMP_TERMINATED]),
                   or_(Employee.exit_date.is_(None), Employee.exit_date >= start))
            .order_by(Employee.emp_code))
    if company_id is not None:
        stmt = stmt.where(Employee.company_id == company_id)
    return list(db.scalars(stmt))


def _warn(code: str, severity: str, message: str) -> dict:
    return {"code": code, "severity": severity, "message": message}


def compute_item_fields(emp: Employee, ctx: Context, bonus: Decimal = ZERO, manual: Decimal = ZERO) -> dict:
    """All PayrollItem column values for one employee, plus warnings. No DB writes."""
    days_in_month = (ctx.end - ctx.start).days + 1
    a_start = max(ctx.start, emp.joining_date)
    a_end = min(ctx.end, emp.exit_date) if emp.exit_date else ctx.end
    active_days = max(0, (a_end - a_start).days + 1)
    active_work = {d for d in ctx.working_dates if a_start <= d <= a_end}
    warnings: list[dict] = []
    lop = overtime_hours = ZERO

    sal = emp.salary
    if sal is None:
        warnings.append(_warn("NO_SALARY_STRUCTURE", "error",
                              "No salary structure is set. Add one, then recalculate."))
        result = PayResult()
    else:
        records = ctx.attendance.get(emp.id, [])
        absent = {r.work_date for r in records if r.status == ATT_ABSENT} & active_work
        half = {r.work_date for r in records if r.status == ATT_HALF_DAY}
        paid_leave: set = set()
        unpaid_leave: set = set()
        for req in ctx.leaves.get(emp.id, []):
            days = {d for d in daterange(max(req.start_date, a_start), min(req.end_date, a_end))} & active_work
            (paid_leave if req.leave_type.is_paid else unpaid_leave).update(days)
        lop = compute_lop_days(active_work, absent, half, paid_leave, unpaid_leave)
        overtime_hours = sum((r.overtime_hours for r in records if a_start <= r.work_date <= a_end), ZERO)

        result = calculate(PayInputs(
            basic=sal.basic, hra=sal.hra, allowances=sal.allowances, pf_enabled=sal.pf_enabled,
            days_in_month=days_in_month, active_days=active_days, working_days=len(ctx.working_dates),
            lop_days=lop, overtime_hours=overtime_hours, bonus=bonus, manual_deduction=manual,
        ), ctx.rules)

        recorded = {r.work_date for r in records} | paid_leave | unpaid_leave
        missing = sorted(d for d in active_work if d < ctx.today and d not in recorded)
        if missing:
            warnings.append(_warn("UNRECORDED_ATTENDANCE", "warning",
                                  f"{len(missing)} working day(s) have no attendance or leave record "
                                  f"(first: {missing[0].isoformat()}). No loss of pay was applied for them."))
        if active_days < days_in_month:
            warnings.append(_warn("PRORATED", "warning",
                                  f"Paid for {active_days} of {days_in_month} days (joined or left mid-month)."))
        if result.net < 0:
            warnings.append(_warn("NEGATIVE_NET", "error",
                                  "Deductions exceed gross pay, so net pay is negative. Reduce the manual deduction."))
    if emp.bank is None:
        warnings.append(_warn("MISSING_BANK", "warning", "No bank details on file - salary cannot be transferred."))

    fields = {name: getattr(result, name) for name in MONEY_FIELDS}
    fields.update(
        emp_code=emp.emp_code, employee_name=emp.full_name,
        department=emp.department.name if emp.department else None,
        designation=emp.designation, employment_type=emp.employment_type,
        days_in_month=days_in_month, active_days=active_days, working_days=len(ctx.working_dates),
        lop_days=lop, overtime_hours=overtime_hours, warnings=warnings,
    )
    if sal is None:
        fields["bonus"], fields["manual_deduction"] = q2(bonus), q2(manual)
    return fields


def sync_items(db: Session, run: PayrollRun) -> int:
    """(Re)calculate every eligible employee. Manual bonus/deduction entries are kept."""
    ctx = build_context(db, run.period_start, run.period_end, company_id=run.company_id)
    employees = eligible_employees(db, run.period_start, run.period_end, company_id=run.company_id)
    existing = {item.employee_id: item for item in run.items}
    for emp in employees:
        item = existing.pop(emp.id, None)
        fields = compute_item_fields(emp, ctx, item.bonus if item else ZERO, item.manual_deduction if item else ZERO)
        if item is None:
            item = PayrollItem(company_id=run.company_id, run_id=run.id, employee_id=emp.id)
            run.items.append(item)
        for key, value in fields.items():
            setattr(item, key, value)
    for stale_item in existing.values():
        run.items.remove(stale_item)
    run.calculated_at = utcnow()
    db.flush()
    return len(employees)


def stale_employees(db: Session, run: PayrollRun) -> list[str]:
    """Employee codes whose calculated figures no longer match today's source data."""
    ctx = build_context(db, run.period_start, run.period_end, company_id=run.company_id)
    employees = eligible_employees(db, run.period_start, run.period_end, company_id=run.company_id)
    items = {i.employee_id: i for i in run.items}
    stale = [] if {e.id for e in employees} == set(items) else ["(headcount changed)"]
    for emp in employees:
        item = items.get(emp.id)
        if item is None:
            continue
        fresh = compute_item_fields(emp, ctx, item.bonus, item.manual_deduction)
        if any(D(fresh[k]) != D(getattr(item, k)) for k in ("gross", "pf", "tax", "other_deductions", "net")):
            stale.append(emp.emp_code)
    return stale


# --------------------------------------------------------------------------- #
# Serialisers
# --------------------------------------------------------------------------- #
def run_totals(db: Session, run_id: int) -> dict:
    row = db.execute(select(
        func.count(PayrollItem.id), func.sum(PayrollItem.gross), func.sum(PayrollItem.pf),
        func.sum(PayrollItem.tax), func.sum(PayrollItem.other_deductions), func.sum(PayrollItem.net),
        func.sum(PayrollItem.employer_pf),
    ).where(PayrollItem.run_id == run_id)).one()
    count, gross, pf, tax, other, net, employer_pf = row
    gross, pf, tax, other, net, employer_pf = (D(v) for v in (gross, pf, tax, other, net, employer_pf))
    return {
        "employee_count": count or 0, "total_gross": gross, "total_pf": pf, "total_tax": tax,
        "total_other_deductions": other, "total_deductions": pf + tax + other, "total_net": net,
        "total_employer_pf": employer_pf, "total_cost": gross + employer_pf,
    }


def exception_rows(run: PayrollRun) -> list[dict]:
    rows = []
    for item in run.items:
        for w in item.warnings or []:
            rows.append({"item_id": item.id, "employee_id": item.employee_id, "emp_code": item.emp_code,
                         "name": item.employee_name, "department": item.department, **w})
    return rows


def run_out(db: Session, run: PayrollRun, with_exceptions: bool = True) -> dict:
    out = {
        "id": run.id, "year": run.year, "month": run.month, "label": month_label(run.year, run.month),
        "period_start": run.period_start, "period_end": run.period_end, "status": run.status,
        "payment_status": payment_status(run.status),
        "steps": STEPS, "current_step": STEP_INDEX[run.status], "allowed_actions": ACTIONS[run.status],
        "created_at": run.created_at, "calculated_at": run.calculated_at, "reviewed_at": run.reviewed_at,
        "finalized_at": run.finalized_at, "paid_at": run.paid_at,
        **run_totals(db, run.id),
    }
    if with_exceptions:
        rows = exception_rows(run)
        out["exceptions_count"] = len(rows)
        out["blocking_errors"] = sum(1 for r in rows if r["severity"] == "error")
    return out


def item_out(item: PayrollItem, run_status: str) -> dict:
    return {
        "id": item.id, "run_id": item.run_id, "employee_id": item.employee_id, "emp_code": item.emp_code,
        "name": item.employee_name, "department": item.department, "designation": item.designation,
        "employment_type": item.employment_type, "status": payment_status(run_status),
        "days_in_month": item.days_in_month, "active_days": item.active_days, "working_days": item.working_days,
        "lop_days": item.lop_days, "overtime_hours": item.overtime_hours,
        **{name: getattr(item, name) for name in MONEY_FIELDS},
        "adjustment_note": item.adjustment_note, "warnings": item.warnings or [],
    }


def get_run_or_404(db: Session, run_id: int, lock: bool = False, company_id: Optional[int] = None) -> PayrollRun:
    stmt = select(PayrollRun).options(selectinload(PayrollRun.items)).where(PayrollRun.id == run_id)
    if company_id is not None:
        stmt = stmt.where(PayrollRun.company_id == company_id)
    if lock:
        stmt = stmt.with_for_update(of=PayrollRun)
    run = db.scalar(stmt)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payroll run not found")
    return run


def _require_status(run: PayrollRun, allowed: tuple, action: str) -> None:
    if run.status not in allowed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot {action}: the run is {run.status}. "
            + ("Finalized payroll is locked - use the reopen workflow if a correction is needed."
               if run.status in (RUN_FINALIZED, RUN_PAID) else "Complete the previous step first."),
        )


def current_run(db: Session, company_id: Optional[int] = None) -> Optional[PayrollRun]:
    """The run the UI should focus on: newest unpaid run, else the newest run."""
    base = select(PayrollRun).options(selectinload(PayrollRun.items))
    if company_id is not None:
        base = base.where(PayrollRun.company_id == company_id)
    order = (PayrollRun.year.desc(), PayrollRun.month.desc())
    return (db.scalars(base.where(PayrollRun.status != RUN_PAID).order_by(*order)).first()
            or db.scalars(base.order_by(*order)).first())


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.get("/runs")
def list_runs(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    stmt = select(PayrollRun).options(selectinload(PayrollRun.items))
    if user.company_id:
        stmt = stmt.where(PayrollRun.company_id == user.company_id)
    stmt = stmt.order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
    runs = db.scalars(stmt).all()
    return [run_out(db, r, with_exceptions=False) for r in runs]


@router.get("/runs/current")
def get_current_run(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    run = current_run(db, company_id=user.company_id)
    return run_out(db, run) if run else None


@router.post("/runs", status_code=status.HTTP_201_CREATED)
def create_run(body: RunCreate, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    today = today_local()
    if (body.year, body.month) > (today.year, today.month):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "You cannot run payroll for a future month")
    chk = select(PayrollRun.id).where(PayrollRun.year == body.year, PayrollRun.month == body.month)
    if user.company_id:
        chk = chk.where(PayrollRun.company_id == user.company_id)
    dup = db.scalar(chk)
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"A payroll run for {month_label(body.year, body.month)} already exists (id {dup})")
    start, end = month_bounds(body.year, body.month)
    run = PayrollRun(
        company_id=user.company_id,
        year=body.year, month=body.month, period_start=start, period_end=end,
        status=RUN_DRAFT, created_by=user.id
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A payroll run for this period already exists")
    if sync_items(db, run) == 0:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No eligible employees for that pay period")
    log_audit(db, user, "payroll.run.create", "payroll_run", run.id, {"period": f"{body.year}-{body.month:02d}"})
    db.commit()
    return run_out(db, get_run_or_404(db, run.id, company_id=user.company_id))


@router.get("/runs/{run_id}")
def get_run(run_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return run_out(db, get_run_or_404(db, run_id, company_id=user.company_id))


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(run_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    run = get_run_or_404(db, run_id, lock=True, company_id=user.company_id)
    _require_status(run, RUN_EDITABLE, "delete this run")
    log_audit(db, user, "payroll.run.delete", "payroll_run", run.id, {"period": f"{run.year}-{run.month:02d}"})
    db.delete(run)
    db.commit()


@router.get("/runs/{run_id}/items")
def run_items(
    run_id: int, search: Optional[str] = Query(default=None, max_length=100),
    department: Optional[str] = None, only_exceptions: bool = False,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_staff), db: Session = Depends(get_db),
):
    run = get_run_or_404(db, run_id, company_id=user.company_id)
    stmt = select(PayrollItem).where(PayrollItem.run_id == run_id).order_by(PayrollItem.emp_code)
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PayrollItem.employee_name.ilike(like), PayrollItem.emp_code.ilike(like)))
    if department:
        stmt = stmt.where(func.lower(PayrollItem.department) == department.lower())
    if only_exceptions:
        rows = [i for i in db.scalars(stmt) if i.warnings]
        total = len(rows)
        rows = rows[(page - 1) * page_size: page * page_size]
    else:
        rows, total = paginate(db, stmt, page, page_size)
    return {"items": [item_out(i, run.status) for i in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/runs/{run_id}/exceptions")
def run_exceptions(run_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    run = get_run_or_404(db, run_id, company_id=user.company_id)
    rows = exception_rows(run)
    return {"run_id": run.id, "count": len(rows),
            "errors": sum(1 for r in rows if r["severity"] == "error"), "items": rows}


@router.patch("/runs/{run_id}/items/{item_id}")
def adjust_item(run_id: int, item_id: int, body: ItemUpdate, user: User = Depends(require_staff),
                db: Session = Depends(get_db)):
    run = get_run_or_404(db, run_id, lock=True, company_id=user.company_id)
    _require_status(run, RUN_EDITABLE, "adjust this payroll item")
    item = next((i for i in run.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payroll item not found in this run")
    data = body.model_dump(exclude_unset=True)
    bonus = data["bonus"] if data.get("bonus") is not None else item.bonus
    manual = data["manual_deduction"] if data.get("manual_deduction") is not None else item.manual_deduction
    emp = db.scalar(select(Employee).options(selectinload(Employee.salary), selectinload(Employee.bank),
                                             selectinload(Employee.department)).where(Employee.id == item.employee_id))
    ctx = build_context(db, run.period_start, run.period_end, company_id=user.company_id)
    before = {"bonus": str(item.bonus), "manual_deduction": str(item.manual_deduction), "net": str(item.net)}
    for key, value in compute_item_fields(emp, ctx, bonus, manual).items():
        setattr(item, key, value)
    if "adjustment_note" in data:
        item.adjustment_note = data["adjustment_note"]
    if run.status == RUN_REVIEWED:
        run.status, run.reviewed_at, run.reviewed_by = RUN_DRAFT, None, None
    log_audit(db, user, "payroll.item.adjust", "payroll_item", item.id,
              {"run_id": run.id, "before": before, "after": {"bonus": str(item.bonus),
               "manual_deduction": str(item.manual_deduction), "net": str(item.net)}})
    db.commit()
    return item_out(item, run.status)


@router.post("/runs/{run_id}/recalculate")
def recalculate(run_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    run = get_run_or_404(db, run_id, lock=True, company_id=user.company_id)
    _require_status(run, RUN_EDITABLE, "recalculate")
    if sync_items(db, run) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No eligible employees for that pay period")
    run.status, run.reviewed_at, run.reviewed_by = RUN_DRAFT, None, None
    log_audit(db, user, "payroll.run.recalculate", "payroll_run", run.id)
    db.commit()
    return run_out(db, get_run_or_404(db, run.id, company_id=user.company_id))


@router.post("/runs/{run_id}/review")
def review_run(run_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    run = get_run_or_404(db, run_id, lock=True, company_id=user.company_id)
    _require_status(run, (RUN_DRAFT,), "mark as reviewed")
    errors = [r for r in exception_rows(run) if r["severity"] == "error"]
    if errors:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{len(errors)} blocking error(s) must be fixed first. "
                            f"See GET /payroll/runs/{run.id}/exceptions")
    stale = stale_employees(db, run)
    if stale:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Source data changed since the last calculation (" + ", ".join(stale[:5])
                            + "). Recalculate first.")
    run.status, run.reviewed_by, run.reviewed_at = RUN_REVIEWED, user.id, utcnow()
    log_audit(db, user, "payroll.run.review", "payroll_run", run.id)
    db.commit()
    return run_out(db, get_run_or_404(db, run.id, company_id=user.company_id))


@router.post("/runs/{run_id}/finalize")
def finalize_run(run_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Locks the run and creates one (Draft) payslip per employee."""
    run = get_run_or_404(db, run_id, lock=True, company_id=user.company_id)
    _require_status(run, (RUN_REVIEWED,), "finalize")
    if not run.items or any(r["severity"] == "error" for r in exception_rows(run)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Blocking errors remain - recalculate and review again")
    stale = stale_employees(db, run)
    if stale:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Source data changed since the review (" + ", ".join(stale[:5])
                            + "). Recalculate and review again.")
    for item in run.items:
        db.add(Payslip(
            company_id=run.company_id,
            run_id=run.id, item_id=item.id, employee_id=item.employee_id, year=run.year,
            month=run.month, payslip_no=f"PS-{run.year}{run.month:02d}-{item.emp_code}",
            status=PAYSLIP_DRAFT
        ))
    run.status, run.finalized_by, run.finalized_at = RUN_FINALIZED, user.id, utcnow()
    totals = run_totals(db, run.id)
    log_audit(db, user, "payroll.run.finalize", "payroll_run", run.id,
              {"employees": totals["employee_count"], "total_net": str(totals["total_net"])})
    db.commit()
    return run_out(db, get_run_or_404(db, run.id, company_id=user.company_id))


@router.post("/runs/{run_id}/mark-paid")
def mark_paid(run_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    run = get_run_or_404(db, run_id, lock=True, company_id=user.company_id)
    _require_status(run, (RUN_FINALIZED,), "mark as paid")
    run.status, run.paid_at = RUN_PAID, utcnow()
    log_audit(db, user, "payroll.run.paid", "payroll_run", run.id)
    db.commit()
    return run_out(db, get_run_or_404(db, run.id, company_id=user.company_id))


@router.post("/runs/{run_id}/reopen")
def reopen_run(run_id: int, body: ReopenIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """The explicit correction workflow for a FINALIZED run (needs a written reason)."""
    run = get_run_or_404(db, run_id, lock=True, company_id=user.company_id)
    if run.status == RUN_PAID:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "A paid run cannot be reopened. Correct the mistake in the next run with a "
                            "bonus or manual deduction adjustment.")
    _require_status(run, (RUN_FINALIZED,), "reopen")
    published = db.scalar(select(func.count(Payslip.id)).where(
        Payslip.run_id == run.id, Payslip.status == PAYSLIP_PUBLISHED))
    if published:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{published} payslip(s) are already published to employees, so this run cannot be reopened.")
    db.execute(delete(Payslip).where(Payslip.run_id == run.id))
    run.status = RUN_DRAFT
    run.reviewed_at = run.reviewed_by = run.finalized_at = run.finalized_by = None
    log_audit(db, user, "payroll.run.reopen", "payroll_run", run.id, {"reason": body.reason})
    db.commit()
    return run_out(db, get_run_or_404(db, run.id, company_id=user.company_id))