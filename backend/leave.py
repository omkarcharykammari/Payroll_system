"""Leave: apply, approve / deny, cancel, balances.
All scoped strictly by tenant Company.
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from auth import get_current_user, is_staff, require_staff
from database import get_db
from models import (
    EMP_ACTIVE, LEAVE_APPROVED, LEAVE_CANCELLED, LEAVE_DENIED, LEAVE_PENDING, Employee, LeaveBalance,
    LeaveRequest, LeaveType, User, utcnow,
)
from schemas import LeaveBalanceSet, LeaveRequestIn, ReviewIn
from settings import get_config
from utils import (
    assert_period_unlocked, fmt_range, holidays_between, log_audit, paginate, today_local, working_days,
)

router = APIRouter(prefix="/leave", tags=["Leave"])


# -------------------------------- converters -------------------------------- #
def request_dict(r: LeaveRequest) -> dict:
    emp = r.employee
    return {
        "id": r.id, "employee_id": r.employee_id, "emp_code": emp.emp_code, "employee_name": emp.full_name,
        "department": emp.department.name if emp.department else None,
        "leave_type_id": r.leave_type_id, "leave_type": r.leave_type.name, "is_paid": r.leave_type.is_paid,
        "start_date": r.start_date, "end_date": r.end_date, "dates": fmt_range(r.start_date, r.end_date),
        "days": r.days, "reason": r.reason, "status": r.status, "review_note": r.review_note,
        "reviewed_at": r.reviewed_at, "created_at": r.created_at,
    }


def _load_options():
    return (selectinload(LeaveRequest.employee).selectinload(Employee.department),
            selectinload(LeaveRequest.leave_type))


def _get_request(db: Session, request_id: int, company_id: Optional[int] = None) -> LeaveRequest:
    stmt = select(LeaveRequest).options(*_load_options()).where(LeaveRequest.id == request_id)
    if company_id is not None:
        stmt = stmt.where(LeaveRequest.company_id == company_id)
    req = db.scalar(stmt)
    if not req:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave request not found")
    return req


# --------------------------------- balances -------------------------------- #
def get_balance(db: Session, employee_id: int, lt: LeaveType, year: int, company_id: Optional[int] = None) -> Optional[LeaveBalance]:
    if lt.annual_quota is None:
        return None
    stmt = select(LeaveBalance).where(
        LeaveBalance.employee_id == employee_id, LeaveBalance.leave_type_id == lt.id, LeaveBalance.year == year)
    if company_id is not None:
        stmt = stmt.where(LeaveBalance.company_id == company_id)
    bal = db.scalar(stmt)
    if not bal:
        bal = LeaveBalance(company_id=company_id, employee_id=employee_id, leave_type_id=lt.id, year=year,
                           allocated=lt.annual_quota, used=Decimal("0"))
        db.add(bal)
        db.flush()
    return bal


def pending_days(db: Session, employee_id: int, leave_type_id: int, year: int, company_id: Optional[int] = None) -> Decimal:
    stmt = select(func.coalesce(func.sum(LeaveRequest.days), 0)).where(
        LeaveRequest.employee_id == employee_id, LeaveRequest.leave_type_id == leave_type_id,
        LeaveRequest.status == LEAVE_PENDING,
        LeaveRequest.start_date.between(date(year, 1, 1), date(year, 12, 31)))
    if company_id is not None:
        stmt = stmt.where(LeaveRequest.company_id == company_id)
    total = db.scalar(stmt)
    return Decimal(total or 0)


def _acting_employee_id(user: User, requested: Optional[int], db: Session) -> int:
    if is_staff(user):
        target = requested or user.employee_id
        if not target:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "employee_id is required")
        emp = db.get(Employee, target)
        if not emp or (user.company_id and emp.company_id != user.company_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
        return target
    if not user.employee_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your login is not linked to an employee record")
    if requested and requested != user.employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only apply for your own leave")
    return user.employee_id


def _assert_unlocked(db: Session, start: date, end: date, what: str, company_id: Optional[int] = None) -> None:
    assert_period_unlocked(db, start, what, company_id=company_id)
    if (end.year, end.month) != (start.year, start.month):
        assert_period_unlocked(db, end, what, company_id=company_id)


# ---------------------------------- reads ----------------------------------- #
@router.get("/types")
def leave_types(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = select(LeaveType).order_by(LeaveType.id)
    if user.company_id:
        stmt = stmt.where(LeaveType.company_id == user.company_id)
    return [{"id": t.id, "name": t.name, "is_paid": t.is_paid, "annual_quota": t.annual_quota}
            for t in db.scalars(stmt)]


@router.get("/balances")
def balances(employee_id: Optional[int] = None, year: Optional[int] = Query(default=None, ge=2000, le=2100),
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    target = employee_id or user.employee_id
    if not target:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "employee_id is required")
    if not is_staff(user) and target != user.employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only view your own balances")
    emp = db.get(Employee, target)
    if not emp or (user.company_id and emp.company_id != user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    year = year or today_local().year
    out = []
    lt_stmt = select(LeaveType).order_by(LeaveType.id)
    if user.company_id:
        lt_stmt = lt_stmt.where(LeaveType.company_id == user.company_id)
    for lt in db.scalars(lt_stmt):
        bal = get_balance(db, target, lt, year, company_id=user.company_id)
        if bal is None:
            out.append({"leave_type_id": lt.id, "leave_type": lt.name, "is_paid": lt.is_paid, "unlimited": True,
                        "allocated": None, "used": None, "pending": pending_days(db, target, lt.id, year, company_id=user.company_id),
                        "available": None})
            continue
        pend = pending_days(db, target, lt.id, year, company_id=user.company_id)
        out.append({"leave_type_id": lt.id, "leave_type": lt.name, "is_paid": lt.is_paid, "unlimited": False,
                    "allocated": bal.allocated, "used": bal.used, "pending": pend,
                    "available": bal.allocated - bal.used - pend})
    db.commit()
    return {"employee_id": target, "year": year, "items": out}


@router.put("/balances/{employee_id}")
def set_balance(employee_id: int, body: LeaveBalanceSet, user: User = Depends(require_staff),
                db: Session = Depends(get_db)):
    emp = db.get(Employee, employee_id)
    if not emp or (user.company_id and emp.company_id != user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    lt = db.get(LeaveType, body.leave_type_id)
    if not lt or (user.company_id and lt.company_id != user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave type not found")
    if lt.annual_quota is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{lt.name} has no quota to adjust")
    bal = get_balance(db, employee_id, lt, body.year, company_id=user.company_id)
    if body.allocated < bal.used:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{bal.used} days are already used; allocation cannot be lower")
    log_audit(db, user, "leave.balance.set", "employee", employee_id,
              {"type": lt.name, "year": body.year, "from": str(bal.allocated), "to": str(body.allocated)})
    bal.allocated = body.allocated
    db.commit()
    return {"employee_id": employee_id, "leave_type": lt.name, "year": body.year,
            "allocated": bal.allocated, "used": bal.used}


@router.get("/requests")
def list_requests(
    tab: str = Query(default="all", pattern="^(all|pending|upcoming|history)$"),
    employee_id: Optional[int] = None,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    today = today_local()
    scope = []
    if user.company_id:
        scope.append(LeaveRequest.company_id == user.company_id)
    if is_staff(user):
        if employee_id:
            scope.append(LeaveRequest.employee_id == employee_id)
    else:
        if employee_id and employee_id != user.employee_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only view your own requests")
        scope.append(LeaveRequest.employee_id == (user.employee_id or -1))

    pending_c = and_(LeaveRequest.status == LEAVE_PENDING)
    upcoming_c = and_(LeaveRequest.status == LEAVE_APPROVED, LeaveRequest.end_date >= today)
    history_c = or_(and_(LeaveRequest.status == LEAVE_APPROVED, LeaveRequest.end_date < today),
                    LeaveRequest.status.in_([LEAVE_DENIED, LEAVE_CANCELLED]))

    def count(cond):
        return db.scalar(select(func.count(LeaveRequest.id)).where(*scope, cond)) or 0

    counts = {"pending": count(pending_c), "upcoming": count(upcoming_c), "history": count(history_c)}
    stmt = select(LeaveRequest).options(*_load_options()).where(*scope)
    if tab == "pending":
        stmt = stmt.where(pending_c).order_by(LeaveRequest.created_at)
    elif tab == "upcoming":
        stmt = stmt.where(upcoming_c).order_by(LeaveRequest.start_date)
    elif tab == "history":
        stmt = stmt.where(history_c).order_by(LeaveRequest.start_date.desc())
    else:
        stmt = stmt.order_by(LeaveRequest.created_at.desc())
    rows, total = paginate(db, stmt, page, page_size)
    return {"counts": counts, "items": [request_dict(r) for r in rows],
            "total": total, "page": page, "page_size": page_size}


# --------------------------------- actions ---------------------------------- #
@router.post("/requests", status_code=status.HTTP_201_CREATED)
def create_request(body: LeaveRequestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    emp_id = _acting_employee_id(user, body.employee_id, db)
    emp = db.get(Employee, emp_id)
    if not emp or (user.company_id and emp.company_id != user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    if emp.status != EMP_ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only active employees can apply for leave")
    lt = db.get(LeaveType, body.leave_type_id)
    if not lt or (user.company_id and lt.company_id != user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Leave type not found")
    if body.start_date.year != body.end_date.year:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "A request cannot span two calendar years - please split it")
    if body.start_date < emp.joining_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Leave cannot start before the joining date")
    _assert_unlocked(db, body.start_date, body.end_date, "leave", company_id=user.company_id)

    overlap = db.scalar(select(LeaveRequest.id).where(
        LeaveRequest.employee_id == emp_id, LeaveRequest.status.in_([LEAVE_PENDING, LEAVE_APPROVED]),
        LeaveRequest.start_date <= body.end_date, LeaveRequest.end_date >= body.start_date))
    if overlap:
        raise HTTPException(status.HTTP_409_CONFLICT, "These dates overlap with another pending or approved request")

    cfg = get_config(db, company_id=user.company_id)
    days = len(working_days(body.start_date, body.end_date, cfg.weekly_off_days,
                            holidays_between(db, body.start_date, body.end_date, company_id=user.company_id)))
    if days == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The selected dates contain no working days")

    bal = get_balance(db, emp_id, lt, body.start_date.year, company_id=user.company_id)
    if bal is not None:
        available = bal.allocated - bal.used - pending_days(db, emp_id, lt.id, body.start_date.year, company_id=user.company_id)
        if Decimal(days) > available:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Insufficient {lt.name} balance: {available} day(s) available, {days} requested")

    req = LeaveRequest(
        company_id=user.company_id,
        employee_id=emp_id, leave_type_id=lt.id, start_date=body.start_date,
        end_date=body.end_date, days=Decimal(days), reason=body.reason, status=LEAVE_PENDING
    )
    db.add(req)
    log_audit(db, user, "leave.apply", "leave_request", None, {"employee_id": emp_id, "days": days})
    db.commit()
    return request_dict(_get_request(db, req.id, company_id=user.company_id))


def _review(db: Session, user: User, request_id: int, approve: bool, note: Optional[str]) -> dict:
    req = _get_request(db, request_id, company_id=user.company_id)
    if req.status != LEAVE_PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request is already {req.status.lower()}")
    if user.employee_id and user.employee_id == req.employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot review your own leave request")
    _assert_unlocked(db, req.start_date, req.end_date, "leave", company_id=user.company_id)

    if approve:
        bal = get_balance(db, req.employee_id, req.leave_type, req.start_date.year, company_id=user.company_id)
        if bal is not None:
            if req.days > bal.allocated - bal.used:
                raise HTTPException(status.HTTP_409_CONFLICT, "Not enough leave balance left to approve this request")
            bal.used += req.days
        req.status = LEAVE_APPROVED
    else:
        req.status = LEAVE_DENIED
    req.reviewed_by, req.reviewed_at, req.review_note = user.id, utcnow(), note
    log_audit(db, user, "leave.approve" if approve else "leave.deny", "leave_request", req.id)
    db.commit()
    return request_dict(req)


@router.post("/requests/{request_id}/approve")
def approve_request(request_id: int, body: ReviewIn = ReviewIn(), user: User = Depends(require_staff),
                    db: Session = Depends(get_db)):
    return _review(db, user, request_id, True, body.note)


@router.post("/requests/{request_id}/deny")
def deny_request(request_id: int, body: ReviewIn = ReviewIn(), user: User = Depends(require_staff),
                 db: Session = Depends(get_db)):
    return _review(db, user, request_id, False, body.note)


@router.post("/requests/{request_id}/cancel")
def cancel_request(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = _get_request(db, request_id, company_id=user.company_id)
    if not is_staff(user) and req.employee_id != user.employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only cancel your own requests")
    if req.status == LEAVE_PENDING:
        req.status = LEAVE_CANCELLED
    elif req.status == LEAVE_APPROVED:
        if req.start_date <= today_local():
            raise HTTPException(status.HTTP_409_CONFLICT, "Leave that has already started cannot be cancelled")
        _assert_unlocked(db, req.start_date, req.end_date, "leave", company_id=user.company_id)
        bal = get_balance(db, req.employee_id, req.leave_type, req.start_date.year, company_id=user.company_id)
        if bal is not None:
            bal.used = max(Decimal("0"), bal.used - req.days)
        req.status = LEAVE_CANCELLED
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A {req.status.lower()} request cannot be cancelled")
    log_audit(db, user, "leave.cancel", "leave_request", req.id)
    db.commit()
    return request_dict(req)