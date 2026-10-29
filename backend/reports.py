"""Dashboard and reports (JSON + Excel/CSV export).
All data strictly scoped by tenant Company.
"""
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from attendance import daily_log, monthly_summary
from auth import get_current_user, require_staff
from database import get_db
from exports import CSV_MIME, XLSX_MIME, build_csv, build_xlsx
from leave import get_balance, pending_days
from models import (
    ATT_ABSENT, ATT_HALF_DAY, ATT_LATE, ATT_NOT_MARKED, ATT_ON_LEAVE, ATT_ON_TIME,
    EMP_ACTIVE, EMP_TERMINATED, LEAVE_APPROVED, LEAVE_PENDING, PAYSLIP_PUBLISHED,
    Attendance, AuditLog, Employee, Holiday, LeaveBalance, LeaveRequest, LeaveType,
    PayrollItem, PayrollRun, Payslip, User,
)
from payroll import STEPS, current_run, item_out, payment_status, run_out, run_totals
from settings import get_config
from utils import holidays_between, log_audit, mask_tail, month_label, parse_period, today_local

router = APIRouter(tags=["Dashboard & Reports"])
D = lambda v: Decimal(str(v or 0))


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
def next_payday(db: Session, today: date, company_id: Optional[int] = None) -> date:
    cfg = get_config(db, company_id=company_id)

    def payday_in(year: int, month: int) -> date:
        last = monthrange(year, month)[1]
        return date(year, month, last if cfg.payday_day == 0 else min(cfg.payday_day, last))

    this = payday_in(today.year, today.month)
    if this >= today:
        return this
    return payday_in(today.year + (today.month == 12), 1 if today.month == 12 else today.month + 1)


def _banner(run: Optional[PayrollRun], today: date) -> dict:
    """The 'Action Required' banner at the top of the dashboard."""
    label = month_label(run.year, run.month) if run else month_label(today.year, today.month)
    if run is None:
        return {"title": f"{label} Payroll Cycle", "message": "No payroll run has been started for this month yet.",
                "action": "start_run", "action_label": "Start Payroll Run"}
    text = {
        "DRAFT": ("Calculations are ready for review.", "review", "Review Draft"),
        "REVIEWED": ("Reviewed - waiting for admin approval.", "finalize", "Approve & Finalize"),
        "FINALIZED": ("Approved - ready to be marked as paid.", "mark_paid", "Mark as Paid"),
        "PAID": ("Salaries have been paid.", None, None),
    }[run.status]
    return {"title": f"{label} Payroll Cycle", "message": text[0], "action": text[1], "action_label": text[2],
            "run_id": run.id}


@router.get("/dashboard")
def dashboard(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    today = today_local()
    run = current_run(db, company_id=user.company_id)
    totals = run_totals(db, run.id) if run else None
    zero = Decimal("0")

    previous = None
    if run:
        prev_stmt = select(PayrollRun).where(
            (PayrollRun.year * 12 + PayrollRun.month) < (run.year * 12 + run.month)
        )
        if user.company_id:
            prev_stmt = prev_stmt.where(PayrollRun.company_id == user.company_id)
        previous = db.scalars(prev_stmt.order_by(PayrollRun.year.desc(), PayrollRun.month.desc())).first()
    change = None
    if previous:
        prev_gross = run_totals(db, previous.id)["total_gross"]
        if prev_gross > 0:
            change = round(float((totals["total_gross"] - prev_gross) / prev_gross * 100), 1)

    payday = next_payday(db, today, company_id=user.company_id)
    emp_stmt = select(Employee).options(selectinload(Employee.department)).where(Employee.status == EMP_ACTIVE)
    if user.company_id:
        emp_stmt = emp_stmt.where(Employee.company_id == user.company_id)
    employees = db.scalars(emp_stmt).all()
    by_dept: dict = {}
    for e in employees:
        name = e.department.name if e.department else "Unassigned"
        by_dept[name] = by_dept.get(name, 0) + 1

    rows = []
    if run:
        rows = [item_out(i, run.status) for i in run.items[:8]]

    leave_stmt = select(func.count(LeaveRequest.id)).where(LeaveRequest.status == LEAVE_PENDING)
    if user.company_id:
        leave_stmt = leave_stmt.where(LeaveRequest.company_id == user.company_id)

    # Trends: payroll_cost (last 6 runs), attendance (last 14 working days), leave_by_type (approved this year)
    run_stmt = select(PayrollRun)
    if user.company_id:
        run_stmt = run_stmt.where(PayrollRun.company_id == user.company_id)
    recent_runs = db.scalars(
        run_stmt.order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).limit(6)
    ).all()
    recent_runs = list(reversed(recent_runs))
    payroll_cost_trend = []
    for r in recent_runs:
        r_totals = run_totals(db, r.id)
        payroll_cost_trend.append({
            "period": f"{r.year}-{r.month:02d}",
            "label": month_label(r.year, r.month),
            "gross": float(r_totals["total_gross"]),
            "net": float(r_totals["total_net"]),
            "deductions": float(r_totals["total_deductions"]),
        })

    cfg = get_config(db, company_id=user.company_id)
    working_dates = []
    curr = today
    while len(working_dates) < 14:
        is_off = curr.weekday() in cfg.weekly_off_days or bool(
            holidays_between(db, curr, curr, company_id=user.company_id)
        )
        if not is_off:
            working_dates.append(curr)
        curr -= timedelta(days=1)
    working_dates.reverse()

    attendance_trend = []
    for d in working_dates:
        d_stats = daily_log(day=d, department=None, search=None, user=user, db=db)["stats"]
        attendance_trend.append({
            "date": d.isoformat(),
            "present": d_stats["on_time"] + d_stats["half_day"],
            "late": d_stats["late"],
            "absent": d_stats["absent"] + (d_stats["not_marked"] if d < today else 0),
            "on_leave": d_stats["on_leave"],
        })

    lt_stmt = select(LeaveType).order_by(LeaveType.name)
    if user.company_id:
        lt_stmt = lt_stmt.where(LeaveType.company_id == user.company_id)
    leave_by_type = []
    for lt in db.scalars(lt_stmt):
        stmt = select(func.coalesce(func.sum(LeaveRequest.days), Decimal("0"))).where(
            LeaveRequest.leave_type_id == lt.id,
            LeaveRequest.status == LEAVE_APPROVED,
            LeaveRequest.start_date.between(date(today.year, 1, 1), date(today.year, 12, 31)),
        )
        if user.company_id:
            stmt = stmt.where(LeaveRequest.company_id == user.company_id)
        total_days = db.scalar(stmt) or Decimal("0")
        leave_by_type.append({
            "leave_type": lt.name,
            "days": float(total_days),
        })

    return {
        "next_payroll_run": {"date": payday, "days_remaining": (payday - today).days},
        "banner": _banner(run, today),
        "current_run": run_out(db, run) if run else None,
        "stats": {
            "total_gross_pay": totals["total_gross"] if totals else zero,
            "taxes_and_deductions": totals["total_deductions"] if totals else zero,
            "net_pay": totals["total_net"] if totals else zero,
            "total_cost_to_company": totals["total_cost"] if totals else zero,
            "gross_change_percent": change,
        },
        "payroll_status": {"status": run.status if run else "NOT_STARTED",
                           "label": payment_status(run.status) if run else "Not started",
                           "current_step": run_out(db, run, False)["current_step"] if run else 0, "steps": STEPS},
        "employees": {
            "total_active": len(employees),
            "new_this_month": sum(1 for e in employees if (e.joining_date.year, e.joining_date.month) == (today.year, today.month)),
            "by_department": [{"department": k, "count": v} for k, v in sorted(by_dept.items())],
        },
        "attendance_today": daily_log(day=None, department=None, search=None, user=user, db=db)["stats"],
        "pending_leave_requests": db.scalar(leave_stmt) or 0,
        "table": {"run_id": run.id if run else None, "items": rows,
                  "exceptions_count": run_out(db, run)["exceptions_count"] if run else 0},
        "trends": {
            "payroll_cost": payroll_cost_trend,
            "attendance": attendance_trend,
            "leave_by_type": leave_by_type,
        },
    }


@router.get("/dashboard/me")
def dashboard_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.employee_id:
        return {
            "linked": False,
            "message": "Your account is not linked to an employee record yet. Ask HR.",
        }
    emp = db.get(Employee, user.employee_id)
    if not emp or (user.company_id and emp.company_id != user.company_id):
        return {
            "linked": False,
            "message": "Your account is not linked to an employee record yet. Ask HR.",
        }

    today = today_local()
    cfg = get_config(db, company_id=user.company_id)

    att = db.scalar(
        select(Attendance).where(
            Attendance.employee_id == emp.id, Attendance.work_date == today
        )
    )
    is_off = today.weekday() in cfg.weekly_off_days or bool(
        holidays_between(db, today, today, company_id=user.company_id)
    )
    on_leave = db.scalar(
        select(LeaveRequest.id).where(
            LeaveRequest.employee_id == emp.id,
            LeaveRequest.status == LEAVE_APPROVED,
            LeaveRequest.start_date <= today,
            LeaveRequest.end_date >= today,
        )
    )
    if att:
        today_status = att.status
        clock_in = att.clock_in.strftime("%I:%M %p") if att.clock_in else None
        clock_out = att.clock_out.strftime("%I:%M %p") if att.clock_out else None
    elif on_leave:
        today_status = "On Leave"
        clock_in = None
        clock_out = None
    elif is_off:
        today_status = "Day Off"
        clock_in = None
        clock_out = None
    else:
        today_status = "Not Marked"
        clock_in = None
        clock_out = None

    lt_stmt = select(LeaveType).order_by(LeaveType.name)
    if user.company_id:
        lt_stmt = lt_stmt.where(LeaveType.company_id == user.company_id)
    leave_balances = []
    for lt in db.scalars(lt_stmt):
        bal = get_balance(db, emp.id, lt, today.year, company_id=user.company_id)
        if bal is None or lt.annual_quota is None:
            allocated = None
            used = 0.0
            available = None
        else:
            pend = pending_days(db, emp.id, lt.id, today.year, company_id=user.company_id)
            allocated = float(bal.allocated)
            used = float(bal.used)
            available = float(bal.allocated - bal.used - pend)
        leave_balances.append({
            "leave_type": lt.name,
            "allocated": allocated,
            "used": used,
            "available": available,
        })

    pending_leave_count = db.scalar(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.employee_id == emp.id, LeaveRequest.status == LEAVE_PENDING
        )
    ) or 0

    ps_stmt = (
        select(Payslip)
        .options(selectinload(Payslip.item))
        .where(Payslip.employee_id == emp.id, Payslip.status == PAYSLIP_PUBLISHED)
        .order_by(Payslip.year.desc(), Payslip.month.desc())
    )
    if user.company_id:
        ps_stmt = ps_stmt.where(Payslip.company_id == user.company_id)

    latest_slip = db.scalars(ps_stmt).first()
    latest_payslip = None
    if latest_slip:
        latest_payslip = {
            "id": latest_slip.id,
            "period_label": month_label(latest_slip.year, latest_slip.month),
            "net": float(latest_slip.item.net) if latest_slip.item else 0.0,
            "status": latest_slip.status,
        }

    slips_6 = db.scalars(ps_stmt.limit(6)).all()
    slips_6 = list(reversed(slips_6))
    net_pay_trend = [
        {
            "period": f"{p.year}-{p.month:02d}",
            "label": month_label(p.year, p.month),
            "net": float(p.item.net) if p.item else 0.0,
        }
        for p in slips_6
    ]

    hol_stmt = select(Holiday).where(Holiday.holiday_date >= today).order_by(Holiday.holiday_date)
    if user.company_id:
        hol_stmt = hol_stmt.where(Holiday.company_id == user.company_id)
    upcoming_holidays = [
        {"date": h.holiday_date.isoformat(), "name": h.name}
        for h in db.scalars(hol_stmt.limit(3)).all()
    ]

    return {
        "linked": True,
        "employee": {
            "name": emp.full_name,
            "emp_code": emp.emp_code,
            "designation": emp.designation,
            "department": emp.department.name if emp.department else None,
        },
        "today": {
            "status": today_status,
            "clock_in": clock_in,
            "clock_out": clock_out,
        },
        "leave_balances": leave_balances,
        "pending_leave_requests": pending_leave_count,
        "latest_payslip": latest_payslip,
        "net_pay_trend": net_pay_trend,
        "upcoming_holidays": upcoming_holidays,
    }


# --------------------------------------------------------------------------- #
# Report builders: (title, columns, rows, summary)
# --------------------------------------------------------------------------- #
def _run_for_period(db: Session, period: Optional[str], company_id: Optional[int] = None) -> PayrollRun:
    if period:
        year, month = parse_period(period)
        stmt = select(PayrollRun).options(selectinload(PayrollRun.items)).where(PayrollRun.year == year, PayrollRun.month == month)
        if company_id is not None:
            stmt = stmt.where(PayrollRun.company_id == company_id)
        run = db.scalar(stmt)
        if not run:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No payroll run exists for {month_label(year, month)}")
        return run
    run = current_run(db, company_id=company_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No payroll runs exist yet")
    return run


def _sum(rows, key) -> Decimal:
    return sum((D(r[key]) for r in rows), Decimal("0"))


def _build_payroll_summary(db, period, company_id: Optional[int] = None):
    run = _run_for_period(db, period, company_id=company_id)
    groups: dict = {}
    for i in run.items:
        g = groups.setdefault(i.department or "Unassigned", {"department": i.department or "Unassigned", "headcount": 0,
                              "gross": 0, "pf": 0, "tax": 0, "other_deductions": 0, "net": 0, "employer_pf": 0})
        g["headcount"] += 1
        for k in ("gross", "pf", "tax", "other_deductions", "net", "employer_pf"):
            g[k] += D(getattr(i, k))
    rows = sorted(groups.values(), key=lambda r: r["department"])
    cols = [("department", "Department", "text"), ("headcount", "Headcount", "number"), ("gross", "Gross (₹)", "money"),
            ("pf", "PF (₹)", "money"), ("tax", "Income Tax (₹)", "money"),
            ("other_deductions", "Other Deductions (₹)", "money"), ("net", "Net Pay (₹)", "money"),
            ("employer_pf", "Employer PF (₹)", "money")]
    summary = {"department": "Total", "headcount": sum(r["headcount"] for r in rows),
               **{k: _sum(rows, k) for k in ("gross", "pf", "tax", "other_deductions", "net", "employer_pf")}}
    return f"Payroll Summary - {month_label(run.year, run.month)}", cols, rows, summary, run


def _build_payroll_register(db, period, company_id: Optional[int] = None):
    run = _run_for_period(db, period, company_id=company_id)
    rows = [{"emp_code": i.emp_code, "name": i.employee_name, "department": i.department, "designation": i.designation,
             "active_days": i.active_days, "lop_days": i.lop_days, **{k: getattr(i, k) for k in (
                 "basic", "hra", "allowances", "overtime_pay", "bonus", "gross", "pf", "tax", "other_deductions", "net")}}
            for i in run.items]
    cols = [("emp_code", "Employee ID", "text"), ("name", "Name", "text"), ("department", "Department", "text"),
            ("designation", "Designation", "text"), ("active_days", "Days Paid", "number"),
            ("lop_days", "LOP Days", "number"), ("basic", "Basic (₹)", "money"), ("hra", "HRA (₹)", "money"),
            ("allowances", "Allowances (₹)", "money"), ("overtime_pay", "Overtime (₹)", "money"),
            ("bonus", "Bonus (₹)", "money"), ("gross", "Gross (₹)", "money"), ("pf", "PF (₹)", "money"),
            ("tax", "Income Tax (₹)", "money"), ("other_deductions", "Other Deductions (₹)", "money"),
            ("net", "Net Pay (₹)", "money")]
    summary = {"emp_code": "Total", **{k: _sum(rows, k) for k in (
        "basic", "hra", "allowances", "overtime_pay", "bonus", "gross", "pf", "tax", "other_deductions", "net")}}
    return f"Payroll Register - {month_label(run.year, run.month)}", cols, rows, summary, run


def _build_tax_liabilities(db, period, company_id: Optional[int] = None):
    run = _run_for_period(db, period, company_id=company_id)
    pans = {e.id: e.pan_number for e in db.scalars(select(Employee).where(
        Employee.id.in_([i.employee_id for i in run.items] or [-1])))}
    rows = [{"emp_code": i.emp_code, "name": i.employee_name, "pan": mask_tail(pans.get(i.employee_id)) or "-",
             "gross": i.gross, "tds": i.tax, "pf_employee": i.pf, "pf_employer": i.employer_pf,
             "professional_tax": i.professional_tax} for i in run.items]
    cols = [("emp_code", "Employee ID", "text"), ("name", "Name", "text"), ("pan", "PAN (masked)", "text"),
            ("gross", "Gross (₹)", "money"), ("tds", "Income Tax / TDS (₹)", "money"),
            ("pf_employee", "PF - Employee (₹)", "money"), ("pf_employer", "PF - Employer (₹)", "money"),
            ("professional_tax", "Professional Tax (₹)", "money")]
    summary = {"emp_code": "Total", **{k: _sum(rows, k) for k in ("gross", "tds", "pf_employee", "pf_employer", "professional_tax")}}
    return f"Tax & Statutory Liabilities - {month_label(run.year, run.month)}", cols, rows, summary, run


def _build_attendance(db, period, company_id: Optional[int] = None):
    year, month = parse_period(period) if period else (today_local().year, today_local().month)
    rows = monthly_summary(db, year, month, company_id=company_id)
    cols = [("emp_code", "Employee ID", "text"), ("name", "Name", "text"), ("department", "Department", "text"),
            ("working_days", "Working Days", "number"), ("present", "Present", "number"), ("late", "Late", "number"),
            ("half_days", "Half Days", "number"), ("absent", "Absent", "number"),
            ("recorded_days", "Days Recorded", "number"), ("total_hours", "Total Hours", "number"),
            ("overtime_hours", "Overtime Hours", "number")]
    summary = {"emp_code": "Total", **{k: _sum(rows, k) for k in ("present", "late", "half_days", "absent", "total_hours", "overtime_hours")}}
    return f"Attendance Summary - {month_label(year, month)}", cols, rows, summary, None


def _build_headcount(db, period, company_id: Optional[int] = None):
    year = parse_period(period)[0] if period else today_local().year
    emp_stmt = select(Employee).options(selectinload(Employee.department))
    if company_id:
        emp_stmt = emp_stmt.where(Employee.company_id == company_id)
    emps = db.scalars(emp_stmt).all()
    groups: dict = {}
    for e in emps:
        g = groups.setdefault(e.department.name if e.department else "Unassigned", {
            "department": e.department.name if e.department else "Unassigned", "active": 0, "full_time": 0,
            "contract": 0, "joiners": 0, "leavers": 0})
        if e.status == EMP_ACTIVE:
            g["active"] += 1
            g["full_time"] += e.employment_type == "Full-time"
            g["contract"] += e.employment_type in ("Contract", "Intern")
        g["joiners"] += e.joining_date.year == year
        g["leavers"] += bool(e.exit_date and e.exit_date.year == year and e.status == EMP_TERMINATED)
    rows = sorted(groups.values(), key=lambda r: r["department"])
    active, leavers = sum(r["active"] for r in rows), sum(r["leavers"] for r in rows)
    cols = [("department", "Department", "text"), ("active", "Active Employees", "number"),
            ("full_time", "Full-time", "number"), ("contract", "Contract / Intern", "number"),
            ("joiners", f"Joined in {year}", "number"), ("leavers", f"Left in {year}", "number")]
    summary = {"department": "Total", "active": active, "full_time": sum(r["full_time"] for r in rows),
               "contract": sum(r["contract"] for r in rows), "joiners": sum(r["joiners"] for r in rows),
               "leavers": leavers, "attrition_rate_percent": round(leavers * 100 / (active + leavers), 1) if active + leavers else 0}
    return f"Headcount & Attrition - {year}", cols, rows, summary, None


def _build_bank_payout(db, period, company_id: Optional[int] = None):
    run = _run_for_period(db, period, company_id=company_id)
    emp_ids = [i.employee_id for i in run.items] or [-1]
    banks = {e.id: e.bank for e in db.scalars(
        select(Employee).options(selectinload(Employee.bank)).where(Employee.id.in_(emp_ids))
    )}
    rows = []
    for i in run.items:
        b = banks.get(i.employee_id)
        rows.append({
            "emp_code": i.emp_code,
            "beneficiary_name": i.employee_name,
            "bank_name": b.bank_name if b else "Pending Setup",
            "account_number": b.account_number if b else "",
            "ifsc": b.ifsc if b else "",
            "net_amount": i.net,
            "payment_reference": f"SAL-{run.year}{run.month:02d}-{i.emp_code}",
        })
    cols = [
        ("emp_code", "Employee ID", "text"),
        ("beneficiary_name", "Beneficiary Name", "text"),
        ("bank_name", "Bank Name", "text"),
        ("account_number", "Account Number", "text"),
        ("ifsc", "IFSC Code", "text"),
        ("net_amount", "Transfer Amount (₹)", "money"),
        ("payment_reference", "Payment Reference", "text"),
    ]
    summary = {
        "emp_code": "Total",
        "beneficiary_name": f"{len(rows)} Transfers",
        "net_amount": sum(D(r["net_amount"]) for r in rows),
    }
    return f"Bank Payout Batch - {month_label(run.year, run.month)}", cols, rows, summary, run


REPORTS = {
    "payroll-summary": ("Payroll Summary", "Monthly cost by department", _build_payroll_summary),
    "payroll-register": ("Payroll Register", "Every employee's earnings and deductions", _build_payroll_register),
    "tax-liabilities": ("Tax Liabilities", "TDS, PF and professional tax to deposit", _build_tax_liabilities),
    "attendance-summary": ("Attendance Trends", "Present, late, absent and overtime per employee", _build_attendance),
    "headcount": ("Headcount & Attrition", "Employees by department, joiners and leavers", _build_headcount),
    "bank-payout": ("Bank Transfer Payout", "Ready-to-upload NEFT/RTGS batch file", _build_bank_payout),
}


def _build(db: Session, name: str, period: Optional[str], company_id: Optional[int] = None):
    if name not in REPORTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown report '{name}'. Available: {', '.join(REPORTS)}")
    return REPORTS[name][2](db, period, company_id=company_id)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.get("/reports")
def available_reports(_: User = Depends(require_staff)):
    return [{"name": k, "title": v[0], "description": v[1]} for k, v in REPORTS.items()]


@router.get("/reports/recent")
def recent_exports(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Your last 10 exports."""
    stmt = select(AuditLog).where(AuditLog.action == "report.export", AuditLog.user_id == user.id)
    if user.company_id:
        stmt = stmt.where(AuditLog.company_id == user.company_id)
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).limit(10)).all()
    out = []
    for r in rows:
        d = r.detail or {}
        qs = f"?format={d.get('format', 'xlsx')}" + (f"&period={d['period']}" if d.get("period") else "")
        out.append({"name": d.get("name"), "title": REPORTS.get(d.get("name"), (d.get("name"),))[0],
                    "period": d.get("period"), "format": d.get("format"), "generated_at": r.created_at,
                    "download_url": f"/reports/{d.get('name')}/export{qs}"})
    return out


@router.get("/reports/{name}")
def get_report(name: str, period: Optional[str] = Query(default=None, description="YYYY-MM"),
               user: User = Depends(require_staff), db: Session = Depends(get_db)):
    title, columns, rows, summary, run = _build(db, name, period, company_id=user.company_id)
    return {"name": name, "title": title, "run_status": run.status if run else None,
            "columns": [{"key": k, "label": l, "type": t} for k, l, t in columns], "rows": rows, "summary": summary}


@router.get("/reports/{name}/export")
def export_report(name: str, period: Optional[str] = Query(default=None, description="YYYY-MM"),
                  format: str = Query(default="xlsx", pattern="^(xlsx|csv)$"),
                  user: User = Depends(require_staff), db: Session = Depends(get_db)):
    title, columns, rows, summary, run = _build(db, name, period, company_id=user.company_id)
    if run and run.status in ("DRAFT", "REVIEWED"):
        subtitle = f"DRAFT - run is {run.status}; figures may still change"
    else:
        subtitle = f"Generated {today_local().isoformat()} - {get_config(db, company_id=user.company_id).company_name}"
    content = (build_xlsx(title, columns, rows, summary, subtitle) if format == "xlsx"
               else build_csv(columns, rows, summary))
    log_audit(db, user, "report.export", "report", name, {"name": name, "period": period, "format": format})
    db.commit()
    filename = f"{name}-{period or 'latest'}.{format}"
    return Response(content=content, media_type=XLSX_MIME if format == "xlsx" else CSV_MIME,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
