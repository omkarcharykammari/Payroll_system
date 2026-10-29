"""Payroll rules, tax slabs, holidays, company profile and the audit-log viewer.

Nothing statutory is hardcoded: PF rates, slabs, cess, ceilings, professional
tax and overtime multipliers all live in the database and are edited here.
All data is scoped per company.
"""
import json
from datetime import date, time
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user, require_admin, require_staff
from database import get_db
from models import AuditLog, Company, Holiday, Setting, TaxSlab, User
from payroll_engine import Rules
from schemas import CompanyCreateIn, CompanyOut, CompanyUpdate, HolidayIn, PayrollConfig, TaxSlabIn
from utils import assert_period_unlocked, log_audit, paginate

router = APIRouter(prefix="/settings", tags=["Settings"])


# --------------------------- config load / save --------------------------- #
def _to_storable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return value


def get_config(db: Session, company_id: Optional[int] = None) -> PayrollConfig:
    known = PayrollConfig.model_fields
    data = {}
    stmt = select(Setting)
    if company_id is not None:
        stmt = stmt.where(Setting.company_id == company_id)
    for row in db.scalars(stmt):
        if row.key in known:
            try:
                data[row.key] = json.loads(row.value)
            except ValueError:
                continue
    return PayrollConfig(**data)  # missing keys fall back to defaults


def save_config(db: Session, cfg: PayrollConfig, company_id: Optional[int] = None) -> None:
    stmt = select(Setting)
    if company_id is not None:
        stmt = stmt.where(Setting.company_id == company_id)
    existing = {s.key: s for s in db.scalars(stmt)}
    for key, value in cfg.model_dump().items():
        encoded = json.dumps(_to_storable(value))
        if key in existing:
            existing[key].value = encoded
        else:
            db.add(Setting(company_id=company_id, key=key, value=encoded))


def get_slabs(db: Session, company_id: Optional[int] = None) -> list[TaxSlab]:
    stmt = select(TaxSlab).order_by(TaxSlab.lower)
    if company_id is not None:
        stmt = stmt.where(TaxSlab.company_id == company_id)
    return list(db.scalars(stmt))


def load_rules(db: Session, company_id: Optional[int] = None) -> tuple[PayrollConfig, Rules]:
    """Everything the payroll engine needs, read fresh from the database for the given company."""
    cfg = get_config(db, company_id=company_id)
    slabs = get_slabs(db, company_id=company_id)
    # If no company-specific slabs found, fallback to unassigned slabs (for backwards compat)
    if not slabs:
        slabs = get_slabs(db, company_id=None)
    rules = Rules(
        pf_rate=cfg.pf_rate, pf_wage_ceiling=cfg.pf_wage_ceiling,
        employer_pf_rate=cfg.employer_pf_rate, standard_deduction=cfg.standard_deduction,
        cess_percent=cfg.cess_percent, rebate_limit=cfg.rebate_limit,
        overtime_multiplier=cfg.overtime_multiplier,
        standard_hours_per_day=cfg.standard_hours_per_day,
        professional_tax_amount=cfg.professional_tax_amount,
        professional_tax_threshold=cfg.professional_tax_threshold,
        slabs=tuple((s.lower, s.upper, s.rate_percent) for s in slabs),
    )
    return cfg, rules


def validate_slabs(slabs: list[TaxSlabIn]) -> list[TaxSlabIn]:
    def bad(msg):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, msg)

    if not slabs:
        bad("At least one slab is required")
    slabs = sorted(slabs, key=lambda s: s.lower)
    if slabs[0].lower != 0:
        bad("The first slab must start at 0")
    for i, slab in enumerate(slabs):
        last = i == len(slabs) - 1
        if last and slab.upper is not None:
            bad("The last slab must have no upper limit")
        if not last:
            if slab.upper is None:
                bad("Only the last slab can be open-ended")
            if slab.upper <= slab.lower:
                bad(f"Slab {i + 1}: upper must be greater than lower")
            if slabs[i + 1].lower != slab.upper:
                bad(f"Slab {i + 1} and {i + 2} must be contiguous (no gaps or overlaps)")
    return slabs


# --------------------------------- routes --------------------------------- #
@router.get("/payroll", response_model=PayrollConfig)
def read_payroll_config(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    return get_config(db, company_id=user.company_id)


@router.put("/payroll", response_model=PayrollConfig)
def update_payroll_config(body: PayrollConfig, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Changes apply to *new calculations*. Finalized payroll keeps its snapshot."""
    save_config(db, body, company_id=admin.company_id)
    log_audit(db, admin, "settings.payroll.update", "settings", None,
              {"values": json.loads(json.dumps(body.model_dump(), default=_to_storable))})
    db.commit()
    return get_config(db, company_id=admin.company_id)


@router.get("/company")
def read_company(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.company_id:
        c = db.get(Company, user.company_id)
        if c:
            return {
                "id": c.id, "name": c.name, "slug": c.slug, "legal_name": c.legal_name,
                "state": c.state, "pan": c.pan, "tan": c.tan, "gstin": c.gstin,
                "pf_establishment_code": c.pf_establishment_code, "address": c.address,
                "logo_url": c.logo_url, "company_name": c.name
            }
    return {"company_name": get_config(db, company_id=user.company_id).company_name}


@router.put("/company")
def update_company(body: CompanyUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cfg = get_config(db, company_id=admin.company_id)
    cfg.company_name = body.company_name.strip()
    save_config(db, cfg, company_id=admin.company_id)
    if admin.company_id:
        c = db.get(Company, admin.company_id)
        if c:
            c.name = body.company_name.strip()
            if body.legal_name is not None:
                c.legal_name = body.legal_name.strip()
            if body.state is not None:
                c.state = body.state.strip()
            if body.pan is not None:
                c.pan = body.pan.strip()
            if body.tan is not None:
                c.tan = body.tan.strip()
            if body.gstin is not None:
                c.gstin = body.gstin.strip()
            if body.pf_establishment_code is not None:
                c.pf_establishment_code = body.pf_establishment_code.strip()
            if body.address is not None:
                c.address = body.address.strip()
            if body.logo_url is not None:
                c.logo_url = body.logo_url.strip()

    log_audit(db, admin, "settings.company.update", "settings", None, {"company_name": cfg.company_name})
    db.commit()
    return read_company(admin, db)


@router.get("/tax-slabs", response_model=list[TaxSlabIn])
def read_tax_slabs(user: User = Depends(require_staff), db: Session = Depends(get_db)):
    slabs = get_slabs(db, company_id=user.company_id)
    if not slabs and user.company_id:
        slabs = get_slabs(db, company_id=None)
    return [TaxSlabIn(lower=s.lower, upper=s.upper, rate_percent=s.rate_percent) for s in slabs]


@router.put("/tax-slabs", response_model=list[TaxSlabIn])
def replace_tax_slabs(body: list[TaxSlabIn], admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    slabs = validate_slabs(body)
    old_slabs = get_slabs(db, company_id=admin.company_id)
    for old in old_slabs:
        db.delete(old)
    db.flush()
    for s in slabs:
        db.add(TaxSlab(company_id=admin.company_id, lower=s.lower, upper=s.upper, rate_percent=s.rate_percent))
    log_audit(db, admin, "settings.tax_slabs.update", "settings", None,
              {"slabs": [[str(s.lower), None if s.upper is None else str(s.upper), str(s.rate_percent)] for s in slabs]})
    db.commit()
    return slabs


@router.get("/holidays")
def list_holidays(year: int = Query(default=None, ge=2000, le=2100), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    stmt = select(Holiday).order_by(Holiday.holiday_date)
    if user.company_id:
        stmt = stmt.where(Holiday.company_id == user.company_id)
    if year:
        stmt = stmt.where(Holiday.holiday_date.between(date(year, 1, 1), date(year, 12, 31)))
    return [{"id": h.id, "holiday_date": h.holiday_date, "name": h.name} for h in db.scalars(stmt)]


@router.post("/holidays", status_code=status.HTTP_201_CREATED)
def add_holiday(body: HolidayIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    assert_period_unlocked(db, body.holiday_date, "its holidays")
    chk = select(Holiday.id).where(Holiday.holiday_date == body.holiday_date)
    if admin.company_id:
        chk = chk.where(Holiday.company_id == admin.company_id)
    if db.scalar(chk):
        raise HTTPException(status.HTTP_409_CONFLICT, "A holiday already exists on that date")
    holiday = Holiday(company_id=admin.company_id, holiday_date=body.holiday_date, name=body.name.strip())
    db.add(holiday)
    log_audit(db, admin, "holiday.add", "holiday", None, {"date": str(body.holiday_date), "name": body.name})
    db.commit()
    return {"id": holiday.id, "holiday_date": holiday.holiday_date, "name": holiday.name}


@router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holiday(holiday_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    holiday = db.get(Holiday, holiday_id)
    if not holiday or (admin.company_id and holiday.company_id != admin.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Holiday not found")
    assert_period_unlocked(db, holiday.holiday_date, "its holidays")
    log_audit(db, admin, "holiday.delete", "holiday", holiday_id, {"date": str(holiday.holiday_date)})
    db.delete(holiday)
    db.commit()


@router.get("/audit-logs")
def audit_logs(
    action: str = Query(default=None, description="Prefix match, e.g. 'payroll.'"),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100),
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if admin.company_id:
        stmt = stmt.where(AuditLog.company_id == admin.company_id)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    rows, total = paginate(db, stmt, page, page_size)
    items = [{
        "id": r.id, "created_at": r.created_at, "user_email": r.user_email, "action": r.action,
        "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail,
    } for r in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}