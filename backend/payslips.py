"""Payslips: list, view, publish and download as PDF.
All data strictly scoped by tenant Company.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from auth import get_current_user, is_staff, require_staff
from database import get_db
from models import (
    PAYSLIP_DRAFT, PAYSLIP_PUBLISHED, RUN_LOCKED, Company, Employee, PayrollRun, Payslip, User, utcnow,
)
from payroll_engine import amount_in_words
from payslip_pdf import build_payslip_pdf
from schemas import PublishIn
from settings import get_config
from utils import log_audit, mask_tail, month_label, paginate, parse_period

router = APIRouter(prefix="/payslips", tags=["Payslips"])


def _options():
    return (selectinload(Payslip.item), selectinload(Payslip.run),
            selectinload(Payslip.employee).selectinload(Employee.department),
            selectinload(Payslip.employee).selectinload(Employee.bank))


def _get_visible(db: Session, user: User, payslip_id: int) -> Payslip:
    stmt = select(Payslip).options(*_options()).where(Payslip.id == payslip_id)
    if user.company_id:
        stmt = stmt.where(Payslip.company_id == user.company_id)
    p = db.scalar(stmt)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payslip not found")
    if not is_staff(user) and (p.employee_id != user.employee_id or p.status != PAYSLIP_PUBLISHED):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payslip not found")
    return p


def list_row(p: Payslip) -> dict:
    i = p.item
    return {
        "id": p.id, "payslip_no": p.payslip_no, "employee_id": p.employee_id, "emp_code": i.emp_code,
        "name": i.employee_name, "department": i.department, "designation": i.designation,
        "gross": i.gross, "net": i.net, "status": p.status, "published_at": p.published_at,
        "period": f"{p.year}-{p.month:02d}", "period_label": month_label(p.year, p.month),
        "run_status": p.run.status,
    }


def payslip_detail(db: Session, p: Payslip) -> dict:
    i, emp = p.item, p.employee
    bank = emp.bank
    comp = db.get(Company, p.company_id) if p.company_id else None
    cfg = get_config(db, company_id=p.company_id)
    c_name = (comp.legal_name or comp.name) if comp else cfg.company_name
    return {
        **list_row(p),
        "company_name": c_name,
        "company_address": comp.address if comp and comp.address else getattr(cfg, "address", None),
        "company_pan": comp.pan if comp else None,
        "company_tan": comp.tan if comp else None,
        "company_gstin": comp.gstin if comp else None,
        "employee": {
            "name": i.employee_name, "emp_code": i.emp_code, "designation": i.designation,
            "department": i.department, "joining_date": emp.joining_date.isoformat(),
            "pan_masked": mask_tail(emp.pan_number), "uan_number": emp.uan_number,
            "bank_name": bank.bank_name if bank else None,
            "account_masked": mask_tail(bank.account_number) if bank else None,
        },
        "days": {"days_in_month": i.days_in_month, "active_days": i.active_days,
                 "working_days": i.working_days, "lop_days": i.lop_days},
        "overtime_hours": i.overtime_hours,
        "earnings": [
            {"label": "Basic", "amount": i.basic}, {"label": "House Rent Allowance (HRA)", "amount": i.hra},
            {"label": "Allowances", "amount": i.allowances}, {"label": "Overtime", "amount": i.overtime_pay},
            {"label": "Bonus", "amount": i.bonus},
        ],
        "deductions": [
            {"label": "Provident Fund (PF)", "amount": i.pf}, {"label": "Income Tax (TDS)", "amount": i.tax},
            {"label": "Loss of Pay", "amount": i.lop_deduction},
            {"label": "Professional Tax", "amount": i.professional_tax},
            {"label": "Other Deductions", "amount": i.manual_deduction},
        ],
        "total_deductions": i.pf + i.tax + i.other_deductions,
        "net_words": amount_in_words(i.net),
        "employer_pf": i.employer_pf,
    }


# ---------------------------------- lists ----------------------------------- #
@router.get("/periods")
def periods(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Options for the month dropdown."""
    stmt = (select(Payslip.year, Payslip.month, func.count(Payslip.id),
                   func.sum(case((Payslip.status == PAYSLIP_PUBLISHED, 1), else_=0)))
            .group_by(Payslip.year, Payslip.month).order_by(Payslip.year.desc(), Payslip.month.desc()))
    if user.company_id:
        stmt = stmt.where(Payslip.company_id == user.company_id)
    if not is_staff(user):
        stmt = stmt.where(Payslip.employee_id == (user.employee_id or -1), Payslip.status == PAYSLIP_PUBLISHED)
    return [{"period": f"{y}-{m:02d}", "label": month_label(y, m), "payslips": n, "published": int(pub or 0)}
            for y, m, n, pub in db.execute(stmt).all()]


@router.get("")
def list_payslips(
    period: str = Query(description="YYYY-MM, e.g. 2026-09"),
    search: Optional[str] = Query(default=None, max_length=100),
    status_: Optional[str] = Query(default=None, alias="status", pattern="^(Draft|Published)$"),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    year, month = parse_period(period)
    stmt = (select(Payslip).options(*_options()).where(Payslip.year == year, Payslip.month == month)
            .order_by(Payslip.payslip_no))
    if user.company_id:
        stmt = stmt.where(Payslip.company_id == user.company_id)
    if is_staff(user):
        if status_:
            stmt = stmt.where(Payslip.status == status_)
        if search and search.strip():
            like = f"%{search.strip()}%"
            stmt = stmt.where(Payslip.employee.has(
                (Employee.first_name + " " + Employee.last_name).ilike(like) | Employee.emp_code.ilike(like)))
    else:
        stmt = stmt.where(Payslip.employee_id == (user.employee_id or -1), Payslip.status == PAYSLIP_PUBLISHED)
    rows, total = paginate(db, stmt, page, page_size)
    run_chk = select(PayrollRun).where(PayrollRun.year == year, PayrollRun.month == month)
    if user.company_id:
        run_chk = run_chk.where(PayrollRun.company_id == user.company_id)
    run = db.scalar(run_chk)
    return {"period": period, "period_label": month_label(year, month), "run_id": run.id if run else None,
            "items": [list_row(p) for p in rows], "total": total, "page": page, "page_size": page_size}


# --------------------------------- publishing ------------------------------- #
@router.post("/publish")
def publish_all(body: PublishIn, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """'Publish All' - makes every Draft payslip of a finalized run visible to its employee."""
    stmt = select(PayrollRun).where(PayrollRun.id == body.run_id) if body.run_id else \
        select(PayrollRun).where(PayrollRun.year == body.year, PayrollRun.month == body.month)
    if user.company_id:
        stmt = stmt.where(PayrollRun.company_id == user.company_id)
    run = db.scalar(stmt)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payroll run not found")
    if run.status not in RUN_LOCKED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payslips can only be published after the run is finalized")
    drafts = db.scalars(select(Payslip).where(Payslip.run_id == run.id, Payslip.status == PAYSLIP_DRAFT)).all()
    now = utcnow()
    for p in drafts:
        p.status, p.published_at = PAYSLIP_PUBLISHED, now
    total = db.scalar(select(func.count(Payslip.id)).where(Payslip.run_id == run.id)) or 0
    log_audit(db, user, "payslip.publish_all", "payroll_run", run.id, {"published": len(drafts)})
    db.commit()
    return {"run_id": run.id, "published": len(drafts), "already_published": total - len(drafts), "total": total}


@router.post("/{payslip_id}/publish")
def publish_one(payslip_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    p = _get_visible(db, user, payslip_id)
    if p.run.status not in RUN_LOCKED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payslips can only be published after the run is finalized")
    if p.status == PAYSLIP_PUBLISHED:
        raise HTTPException(status.HTTP_409_CONFLICT, "This payslip is already published")
    p.status, p.published_at = PAYSLIP_PUBLISHED, utcnow()
    log_audit(db, user, "payslip.publish", "payslip", p.id)
    db.commit()
    return list_row(p)


# ----------------------------------- detail --------------------------------- #
@router.get("/{payslip_id}")
def get_payslip(payslip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return payslip_detail(db, _get_visible(db, user, payslip_id))


@router.get("/{payslip_id}/download")
def download_payslip(payslip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _get_visible(db, user, payslip_id)
    pdf = build_payslip_pdf(payslip_detail(db, p))
    log_audit(db, user, "payslip.download", "payslip", p.id)
    db.commit()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{p.payslip_no}.pdf"'})