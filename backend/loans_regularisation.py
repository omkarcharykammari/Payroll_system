"""Phase 6 Feature Endpoints:
1. Recurring deductions & Loans / Advances.
2. Attendance regularisation workflow (employee correction requests & HR review).
3. Leavers Full & Final (F&F) Settlement estimation.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user, require_admin, require_staff
from database import get_db
from models import (
    AttendanceRegularisation, Attendance, Company, Employee,
    Loan, User, ROLE_EMPLOYEE, STAFF_ROLES, utcnow
)

router = APIRouter(tags=["Loans & Regularisation"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class LoanCreate(BaseModel):
    employee_id: int
    loan_type: str = "Salary Advance"
    principal_amount: Decimal = Field(..., gt=0)
    monthly_installment: Decimal = Field(..., gt=0)


class LoanOut(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    loan_type: str
    principal_amount: float
    monthly_installment: float
    remaining_balance: float
    status: str
    created_at: str


class RegularisationCreate(BaseModel):
    work_date: date
    requested_status: str = "On Time"
    reason: str


class RegularisationReview(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")
    review_note: Optional[str] = None


class RegularisationOut(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    work_date: str
    requested_status: str
    reason: str
    status: str
    review_note: Optional[str] = None
    created_at: str


# --------------------------------------------------------------------------- #
# Loans & Advances Endpoints
# --------------------------------------------------------------------------- #
@router.get("/loans", response_model=List[LoanOut])
def list_loans(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Loan, Employee).join(Employee, Loan.employee_id == Employee.id).where(
        Loan.company_id == user.company_id
    )
    if user.role == ROLE_EMPLOYEE:
        if user.employee_id:
            stmt = stmt.where(Loan.employee_id == user.employee_id)
        else:
            return []

    rows = db.execute(stmt).all()
    return [
        LoanOut(
            id=loan.id,
            employee_id=loan.employee_id,
            employee_name=f"{emp.first_name} {emp.last_name}",
            loan_type=loan.loan_type,
            principal_amount=float(loan.principal_amount),
            monthly_installment=float(loan.monthly_installment),
            remaining_balance=float(loan.remaining_balance),
            status=loan.status,
            created_at=loan.created_at.isoformat() if loan.created_at else "",
        )
        for loan, emp in rows
    ]


@router.post("/loans", response_model=LoanOut, status_code=status.HTTP_201_CREATED)
def create_loan(
    payload: LoanCreate,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    emp = db.get(Employee, payload.employee_id)
    if not emp or emp.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Employee not found")

    loan = Loan(
        company_id=user.company_id,
        employee_id=payload.employee_id,
        loan_type=payload.loan_type,
        principal_amount=payload.principal_amount,
        monthly_installment=payload.monthly_installment,
        remaining_balance=payload.principal_amount,
        status="Active",
    )
    db.add(loan)
    db.commit()
    db.refresh(loan)

    return LoanOut(
        id=loan.id,
        employee_id=loan.employee_id,
        employee_name=f"{emp.first_name} {emp.last_name}",
        loan_type=loan.loan_type,
        principal_amount=float(loan.principal_amount),
        monthly_installment=float(loan.monthly_installment),
        remaining_balance=float(loan.remaining_balance),
        status=loan.status,
        created_at=loan.created_at.isoformat() if loan.created_at else "",
    )


# --------------------------------------------------------------------------- #
# Attendance Regularisation Endpoints
# --------------------------------------------------------------------------- #
@router.post("/attendance/regularisation", response_model=RegularisationOut, status_code=status.HTTP_201_CREATED)
def request_regularisation(
    payload: RegularisationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.employee_id:
        raise HTTPException(status_code=400, detail="User is not linked to an employee record")

    reg = AttendanceRegularisation(
        company_id=user.company_id,
        employee_id=user.employee_id,
        work_date=payload.work_date,
        requested_status=payload.requested_status,
        reason=payload.reason,
        status="Pending",
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)

    emp = db.get(Employee, user.employee_id)
    return RegularisationOut(
        id=reg.id,
        employee_id=reg.employee_id,
        employee_name=f"{emp.first_name} {emp.last_name}" if emp else "",
        work_date=reg.work_date.isoformat(),
        requested_status=reg.requested_status,
        reason=reg.reason,
        status=reg.status,
        review_note=reg.review_note,
        created_at=reg.created_at.isoformat() if reg.created_at else "",
    )


@router.get("/attendance/regularisations", response_model=List[RegularisationOut])
def list_regularisations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(AttendanceRegularisation, Employee)
        .join(Employee, AttendanceRegularisation.employee_id == Employee.id)
        .where(AttendanceRegularisation.company_id == user.company_id)
    )
    if user.role == ROLE_EMPLOYEE:
        if user.employee_id:
            stmt = stmt.where(AttendanceRegularisation.employee_id == user.employee_id)
        else:
            return []

    rows = db.execute(stmt.order_by(AttendanceRegularisation.created_at.desc())).all()
    return [
        RegularisationOut(
            id=r.id,
            employee_id=r.employee_id,
            employee_name=f"{emp.first_name} {emp.last_name}",
            work_date=r.work_date.isoformat(),
            requested_status=r.requested_status,
            reason=r.reason,
            status=r.status,
            review_note=r.review_note,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r, emp in rows
    ]


@router.post("/attendance/regularisations/{reg_id}/review", response_model=RegularisationOut)
def review_regularisation(
    reg_id: int,
    payload: RegularisationReview,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    reg = db.get(AttendanceRegularisation, reg_id)
    if not reg or reg.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Regularisation request not found")

    reg.status = "Approved" if payload.action == "approve" else "Rejected"
    reg.review_note = payload.review_note
    reg.reviewed_by_user_id = user.id
    reg.reviewed_at = utcnow()

    # If approved, update or insert attendance record for the day
    if reg.status == "Approved":
        att = db.scalars(
            select(Attendance).where(
                Attendance.company_id == user.company_id,
                Attendance.employee_id == reg.employee_id,
                Attendance.work_date == reg.work_date,
            )
        ).first()
        if att:
            att.status = reg.requested_status
        else:
            att = Attendance(
                company_id=user.company_id,
                employee_id=reg.employee_id,
                work_date=reg.work_date,
                status=reg.requested_status,
            )
            db.add(att)

    db.commit()
    db.refresh(reg)

    emp = db.get(Employee, reg.employee_id)
    return RegularisationOut(
        id=reg.id,
        employee_id=reg.employee_id,
        employee_name=f"{emp.first_name} {emp.last_name}" if emp else "",
        work_date=reg.work_date.isoformat(),
        requested_status=reg.requested_status,
        reason=reg.reason,
        status=reg.status,
        review_note=reg.review_note,
        created_at=reg.created_at.isoformat() if reg.created_at else "",
    )


# --------------------------------------------------------------------------- #
# Full & Final Settlement (F&F) Estimator
# --------------------------------------------------------------------------- #
@router.get("/employees/{emp_id}/full-and-final")
def calculate_full_and_final(
    emp_id: int,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    emp = db.get(Employee, emp_id)
    if not emp or emp.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Monthly gross from salary structure
    if emp.salary:
        monthly_gross = float(emp.salary.basic + emp.salary.hra + emp.salary.allowances)
    else:
        monthly_gross = 50000.0  # reasonable default base

    daily_rate = round(monthly_gross / 30, 2)


    # Active loans balance
    loans = db.scalars(
        select(Loan).where(
            Loan.company_id == user.company_id,
            Loan.employee_id == emp_id,
            Loan.status == "Active",
        )
    ).all()
    pending_loan_recovery = float(sum(l.remaining_balance for l in loans))

    # Estimated leave encashment (assume 10 unused days for estimation)
    leave_encashment_days = 10
    leave_encashment_pay = round(daily_rate * leave_encashment_days, 2)

    net_payable = round(monthly_gross + leave_encashment_pay - pending_loan_recovery, 2)

    return {
        "employee_id": emp.id,
        "employee_name": f"{emp.first_name} {emp.last_name}",
        "monthly_gross": monthly_gross,
        "leave_encashment_days": leave_encashment_days,
        "leave_encashment_pay": leave_encashment_pay,
        "pending_loan_recovery": pending_loan_recovery,
        "estimated_net_payable": net_payable,
        "settlement_status": "Ready for Processing",
    }
