"""Pydantic request/response models.

Money leaves the API as a JSON *number* (the frontend's formatCurrency expects
numbers) but is always handled as ``Decimal`` inside Python and PostgreSQL.
"""
import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Generic, Literal, Optional, TypeVar

from pydantic import (
    AfterValidator, BaseModel, ConfigDict, EmailStr, Field, PlainSerializer,
    field_validator, model_validator,
)

# --------------------------------------------------------------------------- #
# Shared types
# --------------------------------------------------------------------------- #
_as_number = PlainSerializer(lambda v: float(v), return_type=float, when_used="json")
Money = Annotated[Decimal, _as_number]                                          # output
MoneyIn = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2), _as_number]  # input

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


_PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def _norm_phone(v):
    if v is None or v == "":
        return None
    v = v.replace(" ", "").replace("-", "")
    if not re.fullmatch(r"\+?\d{10,15}", v):
        raise ValueError("phone must be 10-15 digits (optional leading +)")
    return v


def _norm_pan(v):
    if not v:
        return None
    v = v.strip().upper()
    if not _PAN.match(v):
        raise ValueError("pan_number must look like ABCDE1234F")
    return v


def _norm_uan(v):
    if not v:
        return None
    if not re.fullmatch(r"\d{12}", v.strip()):
        raise ValueError("uan_number must be 12 digits")
    return v.strip()


def _check_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(value.encode()) > 72:
        raise ValueError("Password must be at most 72 bytes (bcrypt limit)")
    if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
        raise ValueError("Password must contain at least one letter and one digit")
    return value


Password = Annotated[str, AfterValidator(_check_password)]
Email = Annotated[EmailStr, AfterValidator(lambda v: v.lower())]
Phone = Annotated[Optional[str], AfterValidator(_norm_phone)]
Pan = Annotated[Optional[str], AfterValidator(_norm_pan)]
Uan = Annotated[Optional[str], AfterValidator(_norm_uan)]
Num = Annotated[Decimal, _as_number]


# --------------------------------------------------------------------------- #
# Company & Tenancy
# --------------------------------------------------------------------------- #
class CompanyOut(ORM):
    id: int
    name: str
    slug: str
    legal_name: Optional[str] = None
    state: Optional[str] = None
    pan: Optional[str] = None
    tan: Optional[str] = None
    gstin: Optional[str] = None
    pf_establishment_code: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None
    status: str = "active"


class CompanyCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    legal_name: Optional[str] = Field(default=None, max_length=160)
    state: Optional[str] = Field(default=None, max_length=80)
    pan: Optional[str] = None
    tan: Optional[str] = None
    gstin: Optional[str] = None
    pf_establishment_code: Optional[str] = None
    address: Optional[str] = None


# --------------------------------------------------------------------------- #
# Auth & users
# --------------------------------------------------------------------------- #
class RegisterIn(BaseModel):
    email: Email
    password: Password
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(default="", max_length=80)
    company_name: Optional[str] = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=200)


class UserOut(ORM):
    id: int
    company_id: Optional[int] = None
    email: str
    first_name: str
    last_name: str
    full_name: str
    job_title: Optional[str] = None
    role: str
    is_active: bool
    employee_id: Optional[int] = None


class MeOut(BaseModel):
    user: UserOut
    id: int
    email: str
    first_name: str
    last_name: str
    full_name: str
    role: str
    permissions: list[str]
    company: Optional[CompanyOut] = None
    employee: Optional[dict] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserOut
    refresh_token: Optional[str] = None
    csrf_token: Optional[str] = None


class CompanySignupIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(default="", max_length=80)
    email: Email
    password: Password


class InviteAcceptIn(BaseModel):
    token: str = Field(min_length=10, max_length=128)
    password: Password


class InviteOut(ORM):
    id: int
    company_id: int
    employee_id: int
    email: str
    role: str
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime


class ForgotPasswordIn(BaseModel):
    email: Email


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=128)
    password: Password


class RefreshTokenIn(BaseModel):
    refresh_token: Optional[str] = None


class BulkImportRowError(BaseModel):
    row_number: int
    email: Optional[str] = None
    emp_code: Optional[str] = None
    field: Optional[str] = None
    message: str


class BulkImportResult(BaseModel):
    total_rows: int
    success_count: int
    failure_count: int
    created_employees: list[dict] = Field(default_factory=list)
    errors: list[BulkImportRowError] = Field(default_factory=list)



class ProfileUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    last_name: Optional[str] = Field(default=None, max_length=80)
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    notification_preferences: Optional[dict] = None


class SensitiveChangeRequestIn(BaseModel):
    field_name: Literal["bank_account_number", "bank_ifsc", "bank_name", "pan_number", "uan_number", "legal_name"]
    new_value: str = Field(min_length=1, max_length=255)
    reason: Optional[str] = None


class SensitiveChangeReviewIn(BaseModel):
    status: Literal["approved", "rejected"]
    review_note: Optional[str] = None


class ProfileChangeRequestOut(ORM):
    id: int
    company_id: int
    employee_id: int
    user_id: int
    field_name: str
    old_value: Optional[str] = None
    new_value: str
    reason: Optional[str] = None
    status: str
    review_note: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None


class EmployeeDocumentOut(ORM):
    id: int
    company_id: int
    employee_id: int
    document_type: str
    filename: str
    file_size: int
    mime_type: str
    created_at: datetime



class PasswordChange(BaseModel):
    current_password: str
    new_password: Password


class UserAdminUpdate(BaseModel):
    role: Optional[Literal["owner", "admin", "hr", "employee"]] = None
    is_active: Optional[bool] = None
    employee_id: Optional[int] = None


# --------------------------------------------------------------------------- #
# Employees
# --------------------------------------------------------------------------- #
class DepartmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class DepartmentOut(ORM):
    id: int
    name: str
    employee_count: int = 0


class SalaryIn(BaseModel):
    basic: MoneyIn
    hra: MoneyIn = Decimal("0")
    allowances: MoneyIn = Decimal("0")
    pf_enabled: bool = True

    @model_validator(mode="after")
    def _basic_positive(self):
        if self.basic <= 0:
            raise ValueError("basic must be greater than 0")
        return self


class SalaryOut(ORM):
    basic: Money
    hra: Money
    allowances: Money
    pf_enabled: bool
    monthly_gross: Money
    annual_gross: Money = Decimal("0")


class BankIn(BaseModel):
    account_holder: str = Field(min_length=2, max_length=160)
    bank_name: str = Field(min_length=2, max_length=120)
    account_number: str
    ifsc: str
    branch: Optional[str] = Field(default=None, max_length=120)

    @field_validator("account_number")
    @classmethod
    def _acct(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"\d{9,18}", v):
            raise ValueError("account_number must be 9-18 digits")
        return v

    @field_validator("ifsc")
    @classmethod
    def _ifsc(cls, v: str) -> str:
        v = v.strip().upper()
        if not _IFSC.match(v):
            raise ValueError("ifsc must look like HDFC0001234")
        return v


class BankMasked(BaseModel):
    account_holder: str
    bank_name: str
    account_number_masked: str
    ifsc: str
    branch: Optional[str] = None


class BankFull(BankMasked):
    account_number: str


class _EmployeeFields(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(default="", max_length=80)
    email: Email
    phone: Phone = None
    date_of_birth: Optional[date] = None
    gender: Optional[Literal["Male", "Female", "Other"]] = None
    address: Optional[str] = Field(default=None, max_length=500)
    pan_number: Pan = None
    uan_number: Uan = None
    department_id: Optional[int] = None
    department: Optional[str] = Field(default=None, max_length=80, description="Department name (created if new)")
    designation: str = Field(min_length=2, max_length=120)
    employment_type: Literal["Full-time", "Part-time", "Contract", "Intern"] = "Full-time"
    joining_date: date


class EmployeeCreate(_EmployeeFields):
    emp_code: Optional[str] = Field(default=None, pattern=r"^[A-Z]{2,5}-\d{1,6}$")
    status: Literal["Active", "Inactive"] = "Active"
    salary: Optional[SalaryIn] = None
    bank: Optional[BankIn] = None
    login_password: Optional[Password] = Field(default=None, description="If set, also creates an employee login")


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    last_name: Optional[str] = Field(default=None, max_length=80)
    email: Optional[Email] = None
    phone: Phone = None
    date_of_birth: Optional[date] = None
    gender: Optional[Literal["Male", "Female", "Other"]] = None
    address: Optional[str] = Field(default=None, max_length=500)
    pan_number: Pan = None
    uan_number: Uan = None
    department_id: Optional[int] = None
    department: Optional[str] = Field(default=None, max_length=80)
    designation: Optional[str] = Field(default=None, min_length=2, max_length=120)
    employment_type: Optional[Literal["Full-time", "Part-time", "Contract", "Intern"]] = None
    status: Optional[Literal["Active", "Inactive", "Terminated"]] = None
    joining_date: Optional[date] = None
    exit_date: Optional[date] = None


class EmployeeListItem(BaseModel):
    """Row shape for the Directory / dashboard tables (frontend field names)."""
    id: int
    emp_code: str
    name: str
    email: str
    department: Optional[str]
    designation: str          # frontend calls this "role"
    employment_type: str      # frontend calls this "type"
    status: str
    joining_date: date
    monthly_gross: Optional[Money] = None


class EmployeeOut(BaseModel):
    id: int
    emp_code: str
    first_name: str
    last_name: str
    name: str
    email: str
    phone: Optional[str]
    date_of_birth: Optional[date]
    gender: Optional[str]
    address: Optional[str]
    pan_number: Optional[str]
    uan_number: Optional[str]
    department_id: Optional[int]
    department: Optional[str]
    designation: str
    employment_type: str
    status: str
    joining_date: date
    exit_date: Optional[date]
    salary: Optional[SalaryOut] = None
    bank: Optional[BankMasked] = None
    has_login: bool = False


# --------------------------------------------------------------------------- #
# Attendance
# --------------------------------------------------------------------------- #
class AttendanceIn(BaseModel):
    employee_id: int
    work_date: date
    clock_in: Optional[time] = None
    clock_out: Optional[time] = None
    status: Optional[Literal["On Time", "Late", "Absent", "Half Day"]] = Field(
        default=None, description="Leave empty to derive from the clock times"
    )

    @model_validator(mode="after")
    def _times(self):
        if self.clock_out and not self.clock_in:
            raise ValueError("clock_out needs a clock_in")
        if self.clock_in and self.clock_out and self.clock_out <= self.clock_in:
            raise ValueError("clock_out must be after clock_in")
        if self.status == "Absent" and self.clock_in:
            raise ValueError("An Absent day cannot have a clock_in")
        return self


# --------------------------------------------------------------------------- #
# Leave
# --------------------------------------------------------------------------- #
class LeaveRequestIn(BaseModel):
    employee_id: Optional[int] = Field(default=None, description="Staff only; employees always apply for themselves")
    leave_type_id: int
    start_date: date
    end_date: date
    reason: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _order(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class ReviewIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


# --------------------------------------------------------------------------- #
# Payroll
# --------------------------------------------------------------------------- #
class RunCreate(BaseModel):
    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)


class ItemUpdate(BaseModel):
    bonus: Optional[MoneyIn] = None
    manual_deduction: Optional[MoneyIn] = None
    adjustment_note: Optional[str] = Field(default=None, max_length=500)


class ReopenIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)


class PublishIn(BaseModel):
    run_id: Optional[int] = None
    month: Optional[int] = Field(default=None, ge=1, le=12)
    year: Optional[int] = Field(default=None, ge=2000, le=2100)

    @model_validator(mode="after")
    def _one(self):
        if self.run_id is None and not (self.month and self.year):
            raise ValueError("Provide run_id, or both month and year")
        return self


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class PayrollConfig(BaseModel):
    """Every statutory / policy number the payroll engine uses.

    The defaults are SAMPLE values so the demo works out of the box. Verify
    them against current Indian rules (and your state's professional tax)
    before using this for real money.
    """
    company_name: str = "Vertex Enterprise"

    # attendance & calendar
    weekly_off_days: list[int] = Field(default=[5, 6], description="0=Mon ... 6=Sun")
    shift_start: time = time(9, 0)
    late_grace_minutes: int = Field(default=10, ge=0, le=180)
    standard_hours_per_day: Num = Field(default=Decimal("8"), gt=0, le=24)
    half_day_hours: Num = Field(default=Decimal("4.5"), ge=0, le=24, description="Fewer worked hours than this = Half Day")

    # earnings & deductions
    overtime_multiplier: Num = Field(default=Decimal("1.5"), ge=0, le=5)
    pf_rate: Num = Field(default=Decimal("12"), ge=0, le=100)
    employer_pf_rate: Num = Field(default=Decimal("12"), ge=0, le=100)
    pf_wage_ceiling: Optional[Num] = Field(default=None, ge=0, description="Monthly cap on PF wage; null = no cap")
    standard_deduction: Num = Field(default=Decimal("75000"), ge=0, description="Annual, before slabs")
    cess_percent: Num = Field(default=Decimal("4"), ge=0, le=100)
    rebate_limit: Num = Field(default=Decimal("1200000"), ge=0, description="Annual taxable income at/below which tax is nil; 0 = off")
    professional_tax_amount: Num = Field(default=Decimal("200"), ge=0, description="Flat monthly amount; 0 = off")
    professional_tax_threshold: Num = Field(default=Decimal("25000"), ge=0)

    payday_day: int = Field(default=0, ge=0, le=28, description="Day of month salaries are paid; 0 = last day")

    @field_validator("weekly_off_days")
    @classmethod
    def _days(cls, v):
        if any(d < 0 or d > 6 for d in v) or len(set(v)) != len(v) or len(v) > 6:
            raise ValueError("weekly_off_days must be unique numbers 0-6 and leave at least one working day")
        return sorted(v)


class TaxSlabIn(BaseModel):
    lower: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2), _as_number]
    upper: Optional[Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2), _as_number]] = None
    rate_percent: Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2), _as_number]


class HolidayIn(BaseModel):
    holiday_date: date
    name: str = Field(min_length=2, max_length=120)


class CompanyUpdate(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    legal_name: Optional[str] = Field(default=None, max_length=160)
    state: Optional[str] = Field(default=None, max_length=80)
    pan: Optional[str] = None
    tan: Optional[str] = None
    gstin: Optional[str] = None
    pf_establishment_code: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None



class LeaveBalanceSet(BaseModel):
    leave_type_id: int
    year: int = Field(ge=2000, le=2100)
    allocated: Annotated[Decimal, Field(ge=0, le=365, max_digits=5, decimal_places=1), _as_number] 