"""First-run defaults, shared by the app start-up, seed script, and company creation.

Seeds sample tax slabs, leave types, and payroll configuration for a specific company.
All numbers are SAMPLE values - review them in Settings before real use.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Company, LeaveType, Setting, TaxSlab
from schemas import PayrollConfig
from settings import save_config

# lower, upper, rate %  (annual taxable income, sample slabs modelled on a recent new-regime layout)
SAMPLE_SLABS = [
    (0, 400000, 0), (400000, 800000, 5), (800000, 1200000, 10), (1200000, 1600000, 15),
    (1600000, 2000000, 20), (2000000, 2400000, 25), (2400000, None, 30),
]
LEAVE_TYPES = [
    ("Annual Vacation", True, Decimal("18")),
    ("Sick Leave", True, Decimal("12")),
    ("Unpaid Leave", False, None),
]


def ensure_defaults(db: Session, company_id: Optional[int] = None) -> None:
    """Ensure that defaults exist for the given company_id.
    
    If company_id is None, finds or creates a default company first.
    """
    if company_id is None:
        default_company = db.scalar(select(Company).order_by(Company.id))
        if not default_company:
            default_company = Company(
                name="Vertex Enterprise",
                slug="vertex-enterprise",
                legal_name="Vertex Enterprise Pvt Ltd",
                state="Maharashtra",
                status="active"
            )
            db.add(default_company)
            db.flush()
        company_id = default_company.id

    # Check settings for this company
    has_settings = db.scalar(
        select(func.count(Setting.id)).where(Setting.company_id == company_id)
    )
    if not has_settings:
        save_config(db, PayrollConfig(), company_id=company_id)

    # Check tax slabs for this company
    has_slabs = db.scalar(
        select(func.count(TaxSlab.id)).where(TaxSlab.company_id == company_id)
    )
    if not has_slabs:
        for lower, upper, rate in SAMPLE_SLABS:
            db.add(TaxSlab(
                company_id=company_id,
                lower=Decimal(lower),
                upper=None if upper is None else Decimal(upper),
                rate_percent=Decimal(rate),
            ))

    # Check leave types for this company
    has_leaves = db.scalar(
        select(func.count(LeaveType.id)).where(LeaveType.company_id == company_id)
    )
    if not has_leaves:
        for name, paid, quota in LEAVE_TYPES:
            db.add(LeaveType(
                company_id=company_id,
                name=name,
                is_paid=paid,
                annual_quota=quota,
            ))

    db.commit()