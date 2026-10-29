"""SQLAlchemy models for Vertex HR & Payroll.

Design notes
------------
* Multi-tenant foundation: Every business model belongs to a `Company` via indexed `company_id`.
* Money is always ``Numeric(12, 2)`` (exact decimals, never floats).
* ``PayrollItem`` stores a *snapshot* of every amount used in a payroll run, so
  editing an employee's salary later never changes a finalized payslip.
* Attendance uses ``work_date`` (not ``date``) so the column name never shadows
  the ``datetime.date`` type inside the class body.
"""
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
    Text, Time, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

# --------------------------------------------------------------------------- #
# Constants (string values match the wording used by the frontend)
# --------------------------------------------------------------------------- #
ROLE_OWNER, ROLE_ADMIN, ROLE_HR, ROLE_EMPLOYEE = "owner", "admin", "hr", "employee"
STAFF_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_HR)
ADMIN_ROLES = (ROLE_OWNER, ROLE_ADMIN)

EMP_ACTIVE, EMP_INACTIVE, EMP_TERMINATED = "Active", "Inactive", "Terminated"
EMPLOYMENT_TYPES = ("Full-time", "Part-time", "Contract", "Intern")

ATT_ON_TIME, ATT_LATE, ATT_ABSENT = "On Time", "Late", "Absent"
ATT_HALF_DAY, ATT_ON_LEAVE, ATT_NOT_MARKED = "Half Day", "On Leave", "Not Marked"

LEAVE_PENDING, LEAVE_APPROVED = "Pending", "Approved"
LEAVE_DENIED, LEAVE_CANCELLED = "Denied", "Cancelled"

RUN_DRAFT, RUN_REVIEWED, RUN_FINALIZED, RUN_PAID = "DRAFT", "REVIEWED", "FINALIZED", "PAID"
RUN_LOCKED = (RUN_FINALIZED, RUN_PAID)
RUN_EDITABLE = (RUN_DRAFT, RUN_REVIEWED)

PAYSLIP_DRAFT, PAYSLIP_PUBLISHED = "Draft", "Published"

Money = Numeric(12, 2)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Company & Tenancy
# --------------------------------------------------------------------------- #
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    legal_name: Mapped[Optional[str]] = mapped_column(String(160))
    state: Mapped[Optional[str]] = mapped_column(String(80))  # for professional tax
    pan: Mapped[Optional[str]] = mapped_column(String(10))
    tan: Mapped[Optional[str]] = mapped_column(String(10))
    gstin: Mapped[Optional[str]] = mapped_column(String(15))
    pf_establishment_code: Mapped[Optional[str]] = mapped_column(String(30))
    address: Mapped[Optional[str]] = mapped_column(Text)
    logo_url: Mapped[Optional[str]] = mapped_column(String(255))
    pay_cycle_settings: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    employees: Mapped[list["Employee"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    departments: Mapped[list["Department"]] = relationship(back_populates="company", cascade="all, delete-orphan")


# --------------------------------------------------------------------------- #
# Users & organisation
# --------------------------------------------------------------------------- #
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80), default="")
    job_title: Mapped[Optional[str]] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_EMPLOYEE)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    employee_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Optional[Company]] = relationship(back_populates="users")
    employee: Mapped[Optional["Employee"]] = relationship(back_populates="user")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_department_company_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))

    company: Mapped[Optional[Company]] = relationship(back_populates="departments")


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("company_id", "emp_code", name="uq_employee_company_emp_code"),
        Index("ix_employees_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    emp_code: Mapped[str] = mapped_column(String(20), index=True)  # EMP-001 per company
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80), default="")
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    gender: Mapped[Optional[str]] = mapped_column(String(20))
    address: Mapped[Optional[str]] = mapped_column(Text)
    pan_number: Mapped[Optional[str]] = mapped_column(String(10))
    uan_number: Mapped[Optional[str]] = mapped_column(String(12))

    department_id: Mapped[Optional[int]] = mapped_column(ForeignKey("departments.id"))
    designation: Mapped[str] = mapped_column(String(120))
    employment_type: Mapped[str] = mapped_column(String(20), default="Full-time")
    status: Mapped[str] = mapped_column(String(20), default=EMP_ACTIVE, index=True)
    joining_date: Mapped[date] = mapped_column(Date)
    exit_date: Mapped[Optional[date]] = mapped_column(Date)

    avatar_url: Mapped[Optional[str]] = mapped_column(String(255))
    emergency_contact: Mapped[Optional[str]] = mapped_column(String(255))
    notification_preferences: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    company: Mapped[Optional[Company]] = relationship(back_populates="employees")
    department: Mapped[Optional[Department]] = relationship()
    user: Mapped[Optional[User]] = relationship(back_populates="employee", uselist=False)
    salary: Mapped[Optional["SalaryStructure"]] = relationship(
        back_populates="employee", uselist=False, cascade="all, delete-orphan"
    )
    bank: Mapped[Optional["BankDetail"]] = relationship(
        back_populates="employee", uselist=False, cascade="all, delete-orphan"
    )
    attendance: Mapped[list["Attendance"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    leave_balances: Mapped[list["LeaveBalance"]] = relationship(cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class SalaryStructure(Base):
    """Monthly, full-month amounts. One current structure per employee."""
    __tablename__ = "salary_structures"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), unique=True)
    basic: Mapped[Decimal] = mapped_column(Money)
    hra: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    allowances: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    pf_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    employee: Mapped[Employee] = relationship(back_populates="salary")


class BankDetail(Base):
    __tablename__ = "bank_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), unique=True)
    account_holder: Mapped[str] = mapped_column(String(160))
    bank_name: Mapped[str] = mapped_column(String(120))
    account_number: Mapped[str] = mapped_column(String(24))
    ifsc: Mapped[str] = mapped_column(String(11))
    branch: Mapped[Optional[str]] = mapped_column(String(120))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    employee: Mapped[Employee] = relationship(back_populates="bank")


# --------------------------------------------------------------------------- #
# Attendance & leave
# --------------------------------------------------------------------------- #
class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_attendance_employee_day"),
        Index("ix_attendance_work_date", "work_date"),
        Index("ix_attendance_company_date", "company_id", "work_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date)
    clock_in: Mapped[Optional[time]] = mapped_column(Time)
    clock_out: Mapped[Optional[time]] = mapped_column(Time)
    working_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(20))

    employee: Mapped[Employee] = relationship(back_populates="attendance")


class LeaveType(Base):
    __tablename__ = "leave_types"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_leave_type_company_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True)
    annual_quota: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1))  # None = unlimited


class LeaveBalance(Base):
    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint("employee_id", "leave_type_id", "year", name="uq_leave_balance"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"))
    year: Mapped[int] = mapped_column(Integer)
    allocated: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("0"))
    used: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("0"))

    leave_type: Mapped[LeaveType] = relationship()


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    days: Mapped[Decimal] = mapped_column(Numeric(5, 1))  # working days only
    reason: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=LEAVE_PENDING, index=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    employee: Mapped[Employee] = relationship(back_populates="leave_requests")
    leave_type: Mapped[LeaveType] = relationship()


class Holiday(Base):
    __tablename__ = "holidays"
    __table_args__ = (
        UniqueConstraint("company_id", "holiday_date", name="uq_holiday_company_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    holiday_date: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(120))


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
class Setting(Base):
    """Key -> JSON-encoded value per company (payroll rules, shift timings, company info)."""
    __tablename__ = "settings"
    __table_args__ = (
        UniqueConstraint("company_id", "key", name="uq_setting_company_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(Text)


class TaxSlab(Base):
    """Annual income slab per company. ``upper`` is NULL for the top slab."""
    __tablename__ = "tax_slabs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    lower: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    upper: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))


# --------------------------------------------------------------------------- #
# Payroll
# --------------------------------------------------------------------------- #
class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "month", name="uq_payroll_run_company_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default=RUN_DRAFT, index=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    calculated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finalized_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["PayrollItem"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="PayrollItem.emp_code"
    )


class PayrollItem(Base):
    __tablename__ = "payroll_items"
    __table_args__ = (
        UniqueConstraint("run_id", "employee_id", name="uq_payroll_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)

    emp_code: Mapped[str] = mapped_column(String(20))
    employee_name: Mapped[str] = mapped_column(String(180))
    department: Mapped[Optional[str]] = mapped_column(String(80))
    designation: Mapped[Optional[str]] = mapped_column(String(120))
    employment_type: Mapped[Optional[str]] = mapped_column(String(20))

    days_in_month: Mapped[int] = mapped_column(Integer)
    active_days: Mapped[int] = mapped_column(Integer)
    working_days: Mapped[int] = mapped_column(Integer)
    lop_days: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal("0"))

    basic: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    hra: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    allowances: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    overtime_pay: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    bonus: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    gross: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))

    pf: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    lop_deduction: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    professional_tax: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    manual_deduction: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    other_deductions: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    net: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))

    employer_pf: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    adjustment_note: Mapped[Optional[str]] = mapped_column(Text)
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    run: Mapped[PayrollRun] = relationship(back_populates="items")
    employee: Mapped[Employee] = relationship()


class Payslip(Base):
    __tablename__ = "payslips"
    __table_args__ = (
        UniqueConstraint("company_id", "payslip_no", name="uq_payslip_company_no"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("payroll_items.id"), unique=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    payslip_no: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default=PAYSLIP_DRAFT)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    item: Mapped[PayrollItem] = relationship()
    run: Mapped[PayrollRun] = relationship()
    employee: Mapped[Employee] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    user_email: Mapped[Optional[str]] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[Optional[str]] = mapped_column(String(40))
    detail: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --------------------------------------------------------------------------- #
# Invitations, Password Resets & Session Refresh Tokens
# --------------------------------------------------------------------------- #
class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(20), default=ROLE_EMPLOYEE)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Company] = relationship()
    employee: Mapped[Employee] = relationship()


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[Optional[str]] = mapped_column(String(128))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    ip_address: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()


# --------------------------------------------------------------------------- #
# Profile Change Requests & Employee Documents
# --------------------------------------------------------------------------- #
class ProfileChangeRequest(Base):
    __tablename__ = "profile_change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(60))  # e.g., 'bank_account_number', 'pan_number', 'uan_number'
    old_value: Mapped[Optional[str]] = mapped_column(String(255))
    new_value: Mapped[str] = mapped_column(String(255))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending, approved, rejected
    review_note: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company] = relationship()
    employee: Mapped[Employee] = relationship()
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class EmployeeDocument(Base):
    __tablename__ = "employee_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    document_type: Mapped[str] = mapped_column(String(60))  # "ID Proof", "Offer Letter", "Tax Declaration", "Other"
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Company] = relationship()
    employee: Mapped[Employee] = relationship()


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )  # None if company-wide or staff-wide
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(50))  # leave_requested, leave_decided, payroll_ready, payslip_published, system
    link: Mapped[Optional[str]] = mapped_column(String(255))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Company] = relationship()
    user: Mapped[Optional[User]] = relationship()


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    loan_type: Mapped[str] = mapped_column(String(40), default="Salary Advance")  # "Salary Advance", "Personal Loan"
    principal_amount: Mapped[Decimal] = mapped_column(Money)
    monthly_installment: Mapped[Decimal] = mapped_column(Money)
    remaining_balance: Mapped[Decimal] = mapped_column(Money)
    status: Mapped[str] = mapped_column(String(20), default="Active", index=True)  # Active, Completed, Cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    company: Mapped[Company] = relationship()
    employee: Mapped[Employee] = relationship()


class AttendanceRegularisation(Base):
    __tablename__ = "attendance_regularisations"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    work_date: Mapped[date] = mapped_column(Date, index=True)
    requested_status: Mapped[str] = mapped_column(String(20))  # "On Time", "Half Day", "Present"
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="Pending", index=True)  # Pending, Approved, Rejected
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    review_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    company: Mapped[Company] = relationship()
    employee: Mapped[Employee] = relationship()