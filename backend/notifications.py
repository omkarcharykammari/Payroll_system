"""Notifications & Global Omni-Search API.
Strictly scoped by company and user role.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import (
    Company, Employee, Notification, PayrollRun, Payslip, User,
    ROLE_EMPLOYEE, STAFF_ROLES, EMP_ACTIVE
)

router = APIRouter(tags=["Notifications & Search"])


class NotificationOut(BaseModel):
    id: int
    title: str
    message: str
    type: str
    link: Optional[str] = None
    is_read: bool
    created_at: str

    class Config:
        from_attributes = True


class SearchResultItem(BaseModel):
    category: str  # "employee", "payslip", "page"
    title: str
    subtitle: Optional[str] = None
    link: str


# --------------------------------------------------------------------------- #
# Notifications Endpoints
# --------------------------------------------------------------------------- #
@router.get("/notifications", response_model=List[NotificationOut])
def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Notification)
        .where(
            Notification.company_id == user.company_id,
            or_(Notification.user_id == user.id, Notification.user_id == None),
        )
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    rows = db.scalars(stmt).all()
    return [
        NotificationOut(
            id=n.id,
            title=n.title,
            message=n.message,
            type=n.type,
            link=n.link,
            is_read=n.is_read,
            created_at=n.created_at.isoformat() if n.created_at else "",
        )
        for n in rows
    ]


@router.post("/notifications/{notif_id}/read")
def mark_notification_read(
    notif_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notif = db.get(Notification, notif_id)
    if not notif or notif.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notif.user_id is not None and notif.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    notif.is_read = True
    db.commit()
    return {"status": "ok"}


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Notification).where(
        Notification.company_id == user.company_id,
        or_(Notification.user_id == user.id, Notification.user_id == None),
        Notification.is_read == False,
    )
    rows = db.scalars(stmt).all()
    for n in rows:
        n.is_read = True
    db.commit()
    return {"status": "ok", "updated": len(rows)}


# Helper to emit notification
def create_notification(
    db: Session,
    company_id: int,
    title: str,
    message: str,
    notif_type: str,
    link: Optional[str] = None,
    user_id: Optional[int] = None,
):
    notif = Notification(
        company_id=company_id,
        user_id=user_id,
        title=title,
        message=message,
        type=notif_type,
        link=link,
        is_read=False,
    )
    db.add(notif)
    db.commit()
    return notif


# --------------------------------------------------------------------------- #
# Global ⌘K Omni-Search Endpoint
# --------------------------------------------------------------------------- #
@router.get("/search", response_model=List[SearchResultItem])
def omni_search(
    q: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query_str = q.strip().lower()
    results: List[SearchResultItem] = []

    # 1. Quick Navigation Pages (Role-aware)
    pages = [
        {"name": "Dashboard", "link": "/dashboard", "roles": STAFF_ROLES},
        {"name": "Employee Directory", "link": "/employees", "roles": STAFF_ROLES},
        {"name": "Attendance", "link": "/attendance", "roles": STAFF_ROLES + (ROLE_EMPLOYEE,)},
        {"name": "Leave Management", "link": "/leave", "roles": STAFF_ROLES + (ROLE_EMPLOYEE,)},
        {"name": "Payroll Runs", "link": "/payroll", "roles": STAFF_ROLES},
        {"name": "Payslips", "link": "/payslips", "roles": STAFF_ROLES + (ROLE_EMPLOYEE,)},
        {"name": "Reports & Analytics", "link": "/reports", "roles": STAFF_ROLES},
        {"name": "Settings & Profile", "link": "/settings", "roles": STAFF_ROLES + (ROLE_EMPLOYEE,)},
    ]
    for p in pages:
        if user.role in p["roles"] and query_str in p["name"].lower():
            results.append(SearchResultItem(
                category="page",
                title=p["name"],
                subtitle="Page Navigation",
                link=p["link"]
            ))

    # 2. Employees (Staff can search any active employee; Employee can only search their own profile)
    emp_stmt = select(Employee).where(
        Employee.company_id == user.company_id,
        Employee.status == EMP_ACTIVE,
    )
    if user.role == ROLE_EMPLOYEE:
        if user.employee_id:
            emp_stmt = emp_stmt.where(Employee.id == user.employee_id)
        else:
            emp_stmt = emp_stmt.where(Employee.id == -1)

    matching_pattern = f"%{query_str}%"
    emp_stmt = emp_stmt.where(
        or_(
            Employee.first_name.ilike(matching_pattern),
            Employee.last_name.ilike(matching_pattern),
            Employee.emp_code.ilike(matching_pattern),
            Employee.email.ilike(matching_pattern),
            Employee.designation.ilike(matching_pattern),
        )
    ).limit(8)

    employees = db.scalars(emp_stmt).all()
    for e in employees:
        full_name = f"{e.first_name} {e.last_name}".strip()
        results.append(SearchResultItem(
            category="employee",
            title=f"{full_name} ({e.emp_code})",
            subtitle=f"{e.designation or 'Employee'} • {e.email or ''}",
            link=f"/employees?id={e.id}" if user.role in STAFF_ROLES else "/settings"
        ))

    # 3. Payslips
    payslip_stmt = (
        select(Payslip, Employee)
        .join(Employee, Payslip.employee_id == Employee.id)
        .where(Payslip.company_id == user.company_id)
    )
    if user.role == ROLE_EMPLOYEE:
        if user.employee_id:
            payslip_stmt = payslip_stmt.where(Payslip.employee_id == user.employee_id)
        else:
            payslip_stmt = payslip_stmt.where(Payslip.employee_id == -1)

    payslip_stmt = payslip_stmt.where(
        or_(
            Payslip.payslip_no.ilike(matching_pattern),
            Employee.first_name.ilike(matching_pattern),
            Employee.last_name.ilike(matching_pattern),
        )
    ).limit(5)

    slips = db.execute(payslip_stmt).all()
    for slip, emp in slips:
        results.append(SearchResultItem(
            category="payslip",
            title=f"Payslip {slip.payslip_no or f'#{slip.id}'} - {slip.year}/{slip.month:02d}",
            subtitle=f"{emp.first_name} {emp.last_name} • Status: {slip.status}",
            link="/payslips"
        ))

    return results
