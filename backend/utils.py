"""Small shared helpers: dates, pagination, masking, audit log, period locks."""
from calendar import monthrange, month_name
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import APP_TIMEZONE
from models import RUN_LOCKED, AuditLog, Holiday, PayrollRun, User


# ----------------------------- time & dates ------------------------------- #
def now_local() -> datetime:
    return datetime.now(ZoneInfo(APP_TIMEZONE))


def today_local() -> date:
    return now_local().date()


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def parse_period(value: str) -> tuple[int, int]:
    """'2026-09' -> (2026, 9). Raises a 422 for anything else."""
    try:
        year_s, month_s = value.split("-")
        year, month = int(year_s), int(month_s)
        if not (2000 <= year <= 2100 and 1 <= month <= 12):
            raise ValueError
        return year, month
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "period must look like 2026-09")


def month_label(year: int, month: int) -> str:
    return f"{month_name[month]} {year}"          # "September 2026"


def fmt_range(start: date, end: date) -> str:
    return f"{start.strftime('%b %d')} - {end.strftime('%b %d')}"   # "Oct 12 - Oct 16"


def daterange(start: date, end: date) -> Iterable[date]:
    for i in range((end - start).days + 1):
        yield start + timedelta(days=i)


def holidays_between(db: Session, start: date, end: date, company_id: Optional[int] = None) -> set[date]:
    stmt = select(Holiday.holiday_date).where(Holiday.holiday_date.between(start, end))
    if company_id is not None:
        stmt = stmt.where(Holiday.company_id == company_id)
    rows = db.scalars(stmt)
    return set(rows)


def working_days(start: date, end: date, weekly_off: Iterable[int], holidays: set[date]) -> list[date]:
    """Days in [start, end] that are neither a weekly off (0=Mon .. 6=Sun) nor a holiday."""
    off = set(weekly_off)
    return [d for d in daterange(start, end) if d.weekday() not in off and d not in holidays]


# ------------------------------ money / text ------------------------------ #
def mask_tail(value: Optional[str], keep: int = 4) -> Optional[str]:
    if not value:
        return value
    return "X" * max(len(value) - keep, 0) + value[-keep:]


def money(value) -> Decimal:
    return Decimal(value or 0)


# ------------------------------- pagination ------------------------------- #
def paginate(db: Session, stmt, page: int, page_size: int):
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).all()
    return rows, total


# ------------------------------ audit & locks ----------------------------- #
def log_audit(db: Session, user: Optional[User], action: str, entity: str,
              entity_id=None, detail: Optional[dict] = None) -> None:
    """Adds an audit row to the current transaction (caller commits)."""
    db.add(AuditLog(
        company_id=user.company_id if user else None,
        user_id=user.id if user else None,
        user_email=user.email if user else None,
        action=action, entity=entity,
        entity_id=None if entity_id is None else str(entity_id),
        detail=detail,
    ))


def is_period_locked(db: Session, day: date, company_id: Optional[int] = None) -> bool:
    """True when the payroll run covering ``day`` is finalized or paid."""
    stmt = select(PayrollRun.id).where(
        PayrollRun.year == day.year, PayrollRun.month == day.month,
        PayrollRun.status.in_(RUN_LOCKED),
    )
    if company_id is not None:
        stmt = stmt.where(PayrollRun.company_id == company_id)
    return db.scalar(stmt) is not None


def assert_period_unlocked(db: Session, day: date, what: str = "this record", company_id: Optional[int] = None) -> None:
    if is_period_locked(db, day, company_id=company_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Payroll for {month_label(day.year, day.month)} is finalized, so {what} "
            "can no longer be changed. Ask an admin to reopen the payroll run first.",
        )