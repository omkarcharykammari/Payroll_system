"""Employees, departments, salary structures and bank details.

Access rules
------------
* Admin / HR: full access to everyone in their company.
* Employee: read-only access to their *own* record (salary, masked bank).
* All operations strictly scoped by tenant Company.
* Bank account numbers are masked everywhere except ``/bank/reveal`` (staff
  only), and every reveal / salary change / bank change is written to the audit log.
"""
import csv
import io
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from auth import (
    assert_self_or_staff, get_current_user, hash_password, is_staff, require_admin, require_staff,
)
from database import get_db
from email_service import send_invitation_email
from models import (
    EMP_ACTIVE, EMP_TERMINATED, ROLE_EMPLOYEE, BankDetail, Department, Employee,
    EmployeeDocument, Invitation, PayrollItem, ProfileChangeRequest, SalaryStructure, User,
)
from schemas import (
    BankFull, BankIn, BankMasked, BulkImportResult, BulkImportRowError, DepartmentIn,
    DepartmentOut, EmployeeCreate, EmployeeDocumentOut, EmployeeListItem, EmployeeOut,
    EmployeeUpdate, InviteOut, Message, Page, ProfileChangeRequestOut, SalaryIn,
    SalaryOut, SensitiveChangeRequestIn, SensitiveChangeReviewIn,
)
from security import generate_secure_token, hash_token
from utils import log_audit, mask_tail, paginate, today_local

router = APIRouter(tags=["Employees"])


# ------------------------------- converters -------------------------------- #
def salary_out(s: Optional[SalaryStructure]) -> Optional[SalaryOut]:
    if s is None:
        return None
    gross = s.basic + s.hra + s.allowances
    return SalaryOut(basic=s.basic, hra=s.hra, allowances=s.allowances, pf_enabled=s.pf_enabled,
                     monthly_gross=gross, annual_gross=gross * 12)


def bank_masked(b: Optional[BankDetail]) -> Optional[BankMasked]:
    if b is None:
        return None
    return BankMasked(account_holder=b.account_holder, bank_name=b.bank_name,
                      account_number_masked=mask_tail(b.account_number), ifsc=b.ifsc, branch=b.branch)


def employee_out(e: Employee) -> EmployeeOut:
    return EmployeeOut(
        id=e.id, emp_code=e.emp_code, first_name=e.first_name, last_name=e.last_name, name=e.full_name,
        email=e.email, phone=e.phone, date_of_birth=e.date_of_birth, gender=e.gender, address=e.address,
        pan_number=e.pan_number, uan_number=e.uan_number, department_id=e.department_id,
        department=e.department.name if e.department else None, designation=e.designation,
        employment_type=e.employment_type, status=e.status, joining_date=e.joining_date,
        exit_date=e.exit_date, salary=salary_out(e.salary), bank=bank_masked(e.bank),
        has_login=e.user is not None,
    )


def list_item(e: Employee) -> EmployeeListItem:
    return EmployeeListItem(
        id=e.id, emp_code=e.emp_code, name=e.full_name, email=e.email,
        department=e.department.name if e.department else None, designation=e.designation,
        employment_type=e.employment_type, status=e.status, joining_date=e.joining_date,
        monthly_gross=(e.salary.basic + e.salary.hra + e.salary.allowances) if e.salary else None,
    )


# --------------------------------- helpers --------------------------------- #
def get_employee_or_404(db: Session, employee_id: int, company_id: Optional[int] = None) -> Employee:
    stmt = select(Employee).where(Employee.id == employee_id)
    if company_id is not None:
        stmt = stmt.where(Employee.company_id == company_id)
    emp = db.scalar(stmt)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    return emp


def resolve_department(db: Session, department_id: Optional[int], name: Optional[str], company_id: Optional[int] = None) -> Optional[int]:
    if department_id is not None:
        stmt = select(Department).where(Department.id == department_id)
        if company_id is not None:
            stmt = stmt.where(Department.company_id == company_id)
        if not db.scalar(stmt):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
        return department_id
    if name:
        name = name.strip()
        stmt = select(Department).where(func.lower(Department.name) == name.lower())
        if company_id is not None:
            stmt = stmt.where(Department.company_id == company_id)
        dept = db.scalar(stmt)
        if not dept:
            dept = Department(company_id=company_id, name=name)
            db.add(dept)
            db.flush()
        return dept.id
    return None


def next_emp_code(db: Session, company_id: Optional[int] = None) -> str:
    highest = 0
    stmt = select(Employee.emp_code)
    if company_id is not None:
        stmt = stmt.where(Employee.company_id == company_id)
    for code in db.scalars(stmt):
        m = re.fullmatch(r"EMP-(\d+)", code)
        if m:
            highest = max(highest, int(m.group(1)))
    return f"EMP-{highest + 1:03d}"


def _email_taken(db: Session, email: str, ignore_employee_id: Optional[int] = None) -> bool:
    stmt = select(Employee.id).where(Employee.email == email)
    if ignore_employee_id:
        stmt = stmt.where(Employee.id != ignore_employee_id)
    return db.scalar(stmt) is not None


def _salary_snapshot(s: Optional[SalaryStructure]) -> Optional[dict]:
    return None if s is None else {
        "basic": str(s.basic), "hra": str(s.hra), "allowances": str(s.allowances), "pf_enabled": s.pf_enabled,
    }


# ------------------------------- departments ------------------------------- #
@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dept_stmt = select(Department).order_by(Department.name)
    count_stmt = select(Employee.department_id, func.count(Employee.id)).where(Employee.status == EMP_ACTIVE)
    if user.company_id:
        dept_stmt = dept_stmt.where(Department.company_id == user.company_id)
        count_stmt = count_stmt.where(Employee.company_id == user.company_id)
    count_stmt = count_stmt.group_by(Employee.department_id)
    counts = dict(db.execute(count_stmt).all())
    return [DepartmentOut(id=d.id, name=d.name, employee_count=counts.get(d.id, 0))
            for d in db.scalars(dept_stmt)]


@router.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(body: DepartmentIn, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    name = body.name.strip()
    chk = select(Department.id).where(func.lower(Department.name) == name.lower())
    if user.company_id:
        chk = chk.where(Department.company_id == user.company_id)
    if db.scalar(chk):
        raise HTTPException(status.HTTP_409_CONFLICT, "Department already exists")
    dept = Department(company_id=user.company_id, name=name)
    db.add(dept)
    log_audit(db, user, "department.create", "department", None, {"name": name})
    db.commit()
    return DepartmentOut(id=dept.id, name=dept.name, employee_count=0)


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(department_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    dept = db.get(Department, department_id)
    if not dept or (user.company_id and dept.company_id != user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    if db.scalar(select(func.count(Employee.id)).where(Employee.department_id == department_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Move or remove the employees in this department first")
    log_audit(db, user, "department.delete", "department", department_id, {"name": dept.name})
    db.delete(dept)
    db.commit()


# -------------------------------- employees -------------------------------- #
@router.get("/employees", response_model=Page[EmployeeListItem])
def list_employees(
    search: Optional[str] = Query(default=None, max_length=100, description="Name, email, code or designation"),
    department: Optional[str] = Query(default=None, description="Department name"),
    status_: Optional[str] = Query(default=None, alias="status"),
    employment_type: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    stmt = (select(Employee).outerjoin(Department)
            .options(selectinload(Employee.salary), selectinload(Employee.department))
            .order_by(Employee.emp_code))
    if user.company_id:
        stmt = stmt.where(Employee.company_id == user.company_id)
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(
            (Employee.first_name + " " + Employee.last_name).ilike(like),
            Employee.email.ilike(like), Employee.emp_code.ilike(like), Employee.designation.ilike(like),
        ))
    if department:
        stmt = stmt.where(func.lower(Department.name) == department.lower())
    if status_:
        stmt = stmt.where(Employee.status == status_)
    if employment_type:
        stmt = stmt.where(Employee.employment_type == employment_type)
    rows, total = paginate(db, stmt, page, page_size)
    return Page(items=[list_item(e) for e in rows], total=total, page=page, page_size=page_size)


@router.post("/employees", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(body: EmployeeCreate, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    if _email_taken(db, body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "An employee with this email already exists")
    if body.login_password and db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A login with this email already exists")
    code = body.emp_code or next_emp_code(db, company_id=user.company_id)
    
    code_chk = select(Employee.id).where(Employee.emp_code == code)
    if user.company_id:
        code_chk = code_chk.where(Employee.company_id == user.company_id)
    if db.scalar(code_chk):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Employee code {code} is already in use")

    emp = Employee(
        company_id=user.company_id,
        emp_code=code, first_name=body.first_name.strip(), last_name=body.last_name.strip(),
        email=body.email, phone=body.phone, date_of_birth=body.date_of_birth, gender=body.gender,
        address=body.address, pan_number=body.pan_number, uan_number=body.uan_number,
        department_id=resolve_department(db, body.department_id, body.department, company_id=user.company_id),
        designation=body.designation.strip(), employment_type=body.employment_type,
        status=body.status, joining_date=body.joining_date,
    )
    if body.salary:
        emp.salary = SalaryStructure(company_id=user.company_id, **body.salary.model_dump())
    if body.bank:
        emp.bank = BankDetail(company_id=user.company_id, **body.bank.model_dump())
    db.add(emp)
    try:
        db.flush()
        if body.login_password:
            db.add(User(
                company_id=user.company_id,
                email=emp.email, hashed_password=hash_password(body.login_password),
                first_name=emp.first_name, last_name=emp.last_name, job_title=emp.designation,
                role=ROLE_EMPLOYEE, employee_id=emp.id
            ))
        elif user.company_id:
            # Issue invitation token and send invitation email
            raw_token = generate_secure_token()
            token_h = hash_token(raw_token)
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            inv = Invitation(
                company_id=user.company_id,
                employee_id=emp.id,
                email=emp.email,
                role=ROLE_EMPLOYEE,
                token_hash=token_h,
                expires_at=expires_at,
                created_by_user_id=user.id,
            )
            db.add(inv)
            company_name = user.company.name if user.company else "Vertex Enterprise"
            send_invitation_email(emp.email, emp.full_name, company_name, raw_token)

        log_audit(db, user, "employee.create", "employee", emp.id, {"emp_code": code})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate email or employee code")
    db.refresh(emp)
    return employee_out(emp)


@router.get("/employees/me", response_model=EmployeeOut)
def my_employee_record(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.employee_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Your login is not linked to an employee record yet")
    return employee_out(get_employee_or_404(db, user.employee_id, company_id=user.company_id))


@router.get("/employees/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_self_or_staff(user, employee_id)
    return employee_out(get_employee_or_404(db, employee_id, company_id=user.company_id))


@router.patch("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(employee_id: int, body: EmployeeUpdate, user: User = Depends(require_staff),
                    db: Session = Depends(get_db)):
    emp = get_employee_or_404(db, employee_id, company_id=user.company_id)
    data = body.model_dump(exclude_unset=True)

    if "email" in data and data["email"] and _email_taken(db, data["email"], emp.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Another employee already uses this email")
    if "department" in data or "department_id" in data:
        emp.department_id = resolve_department(db, data.pop("department_id", None), data.pop("department", None), company_id=user.company_id)
    for field in ("first_name", "last_name", "designation"):
        if field in data and data[field] is not None:
            data[field] = data[field].strip()
    for field in ("email", "status", "joining_date", "designation", "first_name", "employment_type"):
        if field in data and data[field] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} cannot be empty")

    before = {k: str(getattr(emp, k)) for k in data if hasattr(emp, k)}
    for field, value in data.items():
        setattr(emp, field, value)

    if emp.status == EMP_TERMINATED and emp.exit_date is None:
        emp.exit_date = today_local()
    if emp.exit_date and emp.exit_date < emp.joining_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "exit_date cannot be before joining_date")
    if emp.status == EMP_TERMINATED and emp.user:
        emp.user.is_active = False            # a leaver must not keep access

    log_audit(db, user, "employee.update", "employee", emp.id, {"before": before, "fields": sorted(data)})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate value for a unique field")
    db.refresh(emp)
    return employee_out(emp)


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(employee_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    emp = get_employee_or_404(db, employee_id, company_id=user.company_id)
    if db.scalar(select(func.count(PayrollItem.id)).where(PayrollItem.employee_id == employee_id)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This employee has payroll history and cannot be deleted. "
            "Set their status to Terminated (PATCH status + exit_date) instead.",
        )
    if emp.user:
        emp.user.is_active = False
        emp.user.employee_id = None
        db.flush()
    log_audit(db, user, "employee.delete", "employee", emp.id, {"emp_code": emp.emp_code, "name": emp.full_name})
    db.delete(emp)
    db.commit()


# ---------------------------------- salary ---------------------------------- #
@router.get("/employees/{employee_id}/salary", response_model=SalaryOut)
def get_salary(employee_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_self_or_staff(user, employee_id)
    emp = get_employee_or_404(db, employee_id, company_id=user.company_id)
    if not emp.salary:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No salary structure set for this employee")
    return salary_out(emp.salary)


@router.put("/employees/{employee_id}/salary", response_model=SalaryOut)
def set_salary(employee_id: int, body: SalaryIn, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    emp = get_employee_or_404(db, employee_id, company_id=user.company_id)
    before = _salary_snapshot(emp.salary)
    if emp.salary:
        for field, value in body.model_dump().items():
            setattr(emp.salary, field, value)
    else:
        emp.salary = SalaryStructure(company_id=user.company_id, **body.model_dump())
    db.flush()
    log_audit(db, user, "salary.update", "employee", emp.id, {"before": before, "after": _salary_snapshot(emp.salary)})
    db.commit()
    return salary_out(emp.salary)


# ------------------------------------ bank ---------------------------------- #
@router.get("/employees/{employee_id}/bank", response_model=BankMasked)
def get_bank(employee_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_self_or_staff(user, employee_id)
    emp = get_employee_or_404(db, employee_id, company_id=user.company_id)
    if not emp.bank:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No bank details on file")
    return bank_masked(emp.bank)


@router.get("/employees/{employee_id}/bank/reveal", response_model=BankFull)
def reveal_bank(employee_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    emp = get_employee_or_404(db, employee_id, company_id=user.company_id)
    if not emp.bank:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No bank details on file")
    log_audit(db, user, "bank.reveal", "employee", emp.id)
    db.commit()
    masked = bank_masked(emp.bank)
    return BankFull(**masked.model_dump(), account_number=emp.bank.account_number)


@router.put("/employees/{employee_id}/bank", response_model=BankMasked)
def set_bank(employee_id: int, body: BankIn, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    emp = get_employee_or_404(db, employee_id, company_id=user.company_id)
    if emp.bank:
        for field, value in body.model_dump().items():
            setattr(emp.bank, field, value)
    else:
        emp.bank = BankDetail(company_id=user.company_id, **body.model_dump())
    db.flush()
    log_audit(db, user, "bank.update", "employee", emp.id, {"bank_name": body.bank_name, "ifsc": body.ifsc})
    db.commit()
    return bank_masked(emp.bank)


# ---------------------------- invitations ---------------------------------- #
@router.post("/employees/{employee_id}/invite", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def invite_employee(employee_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Manually send or re-issue an invitation link to an employee."""
    emp = get_employee_or_404(db, employee_id, company_id=user.company_id)
    # Check if a User account already exists
    if db.scalar(select(User.id).where(User.employee_id == emp.id)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This employee already has an active login")

    # Revoke any prior pending invites
    for prev in db.scalars(
        select(Invitation).where(
            Invitation.employee_id == emp.id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    ):
        prev.revoked_at = datetime.now(timezone.utc)

    raw_token = generate_secure_token()
    token_h = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    inv = Invitation(
        company_id=emp.company_id,
        employee_id=emp.id,
        email=emp.email,
        role=ROLE_EMPLOYEE,
        token_hash=token_h,
        expires_at=expires_at,
        created_by_user_id=user.id,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)

    company_name = user.company.name if user.company else "Vertex Enterprise"
    send_invitation_email(emp.email, emp.full_name, company_name, raw_token)
    log_audit(db, user, "invite.send", "employee", emp.id, {"email": emp.email})
    return inv


@router.post("/employees/{employee_id}/resend-invite", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def resend_invite(employee_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Resend a fresh invitation token to an employee."""
    return invite_employee(employee_id, user, db)


@router.delete("/employees/{employee_id}/revoke-invite", response_model=Message)
def revoke_invite(employee_id: int, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Revoke any pending invitations for this employee."""
    emp = get_employee_or_404(db, employee_id, company_id=user.company_id)
    now = datetime.now(timezone.utc)
    invs = db.scalars(
        select(Invitation).where(
            Invitation.employee_id == emp.id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    ).all()
    if not invs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active invitation found to revoke")
    for inv in invs:
        inv.revoked_at = now
    db.commit()
    log_audit(db, user, "invite.revoke", "employee", emp.id)
    return Message(detail="Invitation revoked successfully")


# ---------------------------- bulk import ---------------------------------- #
@router.post("/employees/bulk-import", response_model=BulkImportResult)
async def bulk_import_employees(
    file: UploadFile = File(...),
    send_invites: bool = Query(default=True, description="Automatically email invitation links"),
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """Bulk import employees from a CSV file.
    Validates row by row, returns a structured error report for bad rows,
    and creates employees for valid rows.
    """
    contents = await file.read()
    try:
        decoded = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File must be valid UTF-8 encoded CSV")

    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV file is empty or missing headers")

    required_headers = {"first_name", "last_name", "email", "designation"}
    missing = required_headers - {h.strip().lower() for h in reader.fieldnames if h}
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Missing required CSV column(s): {', '.join(sorted(missing))}"
        )

    rows = list(reader)
    if not rows:
        return BulkImportResult(total_rows=0, success_count=0, failure_count=0)

    errors: list[BulkImportRowError] = []
    created_list = []
    seen_emails: set[str] = set()
    seen_codes: set[str] = set()

    for idx, row in enumerate(rows, start=2):  # row 1 is header
        clean_row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items() if k}
        email = clean_row.get("email", "").lower()
        first_name = clean_row.get("first_name", "")
        last_name = clean_row.get("last_name", "")
        emp_code = clean_row.get("emp_code", "")
        dept_name = clean_row.get("department", "General")
        designation = clean_row.get("designation", "")
        joining_str = clean_row.get("joining_date", "")

        # Row validations
        if not first_name:
            errors.append(BulkImportRowError(row_number=idx, email=email, emp_code=emp_code, field="first_name", message="First name is required"))
            continue
        if not email or "@" not in email:
            errors.append(BulkImportRowError(row_number=idx, email=email, emp_code=emp_code, field="email", message="Valid email is required"))
            continue
        if email in seen_emails or _email_taken(db, email):
            errors.append(BulkImportRowError(row_number=idx, email=email, emp_code=emp_code, field="email", message="Email is already registered"))
            continue
        if not designation:
            errors.append(BulkImportRowError(row_number=idx, email=email, emp_code=emp_code, field="designation", message="Designation is required"))
            continue

        # Joining date validation
        joining_dt = today_local()
        if joining_str:
            try:
                joining_dt = datetime.strptime(joining_str, "%Y-%m-%d").date()
            except ValueError:
                errors.append(BulkImportRowError(row_number=idx, email=email, emp_code=emp_code, field="joining_date", message="Date must be YYYY-MM-DD"))
                continue

        # Employee code resolution & check
        if not emp_code:
            emp_code = next_emp_code(db, company_id=user.company_id)
        if emp_code in seen_codes:
            errors.append(BulkImportRowError(row_number=idx, email=email, emp_code=emp_code, field="emp_code", message="Duplicate employee code in CSV"))
            continue

        code_chk = select(Employee.id).where(Employee.emp_code == emp_code)
        if user.company_id:
            code_chk = code_chk.where(Employee.company_id == user.company_id)
        if db.scalar(code_chk):
            errors.append(BulkImportRowError(row_number=idx, email=email, emp_code=emp_code, field="emp_code", message="Employee code is already in use"))
            continue

        dept_id = resolve_department(db, None, dept_name, company_id=user.company_id)

        # Basic salary figures if provided
        salary_obj = None
        basic_val = clean_row.get("basic_salary") or clean_row.get("basic")
        if basic_val:
            try:
                basic_dec = Decimal(basic_val)
                hra_dec = Decimal(clean_row.get("hra") or "0")
                allow_dec = Decimal(clean_row.get("allowances") or "0")
                salary_obj = SalaryStructure(
                    company_id=user.company_id,
                    basic=basic_dec,
                    hra=hra_dec,
                    allowances=allow_dec,
                    pf_enabled=clean_row.get("pf_enabled", "true").lower() in ("true", "1", "yes"),
                )
            except Exception:
                pass

        emp = Employee(
            company_id=user.company_id,
            emp_code=emp_code,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=clean_row.get("phone") or None,
            department_id=dept_id,
            designation=designation,
            employment_type=clean_row.get("employment_type") or "Full-time",
            status="Active",
            joining_date=joining_dt,
        )
        if salary_obj:
            emp.salary = salary_obj

        # Bank details if provided
        acct_no = clean_row.get("bank_account_number") or clean_row.get("account_number")
        if acct_no:
            emp.bank = BankDetail(
                company_id=user.company_id,
                account_holder=f"{first_name} {last_name}".strip(),
                bank_name=clean_row.get("bank_name", "Main Bank"),
                account_number=acct_no,
                ifsc=clean_row.get("ifsc", "IFSC0000000"),
                branch=clean_row.get("branch", "Main Branch"),
            )

        db.add(emp)
        db.flush()

        seen_emails.add(email)
        seen_codes.add(emp_code)

        if send_invites and user.company_id:
            raw_token = generate_secure_token()
            token_h = hash_token(raw_token)
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            inv = Invitation(
                company_id=user.company_id,
                employee_id=emp.id,
                email=emp.email,
                role=ROLE_EMPLOYEE,
                token_hash=token_h,
                expires_at=expires_at,
                created_by_user_id=user.id,
            )
            db.add(inv)
            company_name = user.company.name if user.company else "Vertex Enterprise"
            send_invitation_email(emp.email, emp.full_name, company_name, raw_token)

        created_list.append({"id": emp.id, "emp_code": emp.emp_code, "email": emp.email, "name": emp.full_name})

    if created_list:
        db.commit()
        log_audit(db, user, "employees.bulk_import", "employee", None, {"imported_count": len(created_list)})
    else:
        db.rollback()

    return BulkImportResult(
        total_rows=len(rows),
        success_count=len(created_list),
        failure_count=len(errors),
        created_employees=created_list,
        errors=errors,
    )


# ---------------------- sensitive profile change requests ------------------- #
@router.post("/employees/me/change-requests", response_model=ProfileChangeRequestOut, status_code=status.HTTP_201_CREATED)
def submit_sensitive_change_request(
    body: SensitiveChangeRequestIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Employee submits a request to update sensitive info (bank, PAN, UAN, legal name)."""
    if not user.employee_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No linked employee record")
    emp = db.get(Employee, user.employee_id)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee record not found")

    old_val = None
    if body.field_name == "bank_account_number" and emp.bank:
        old_val = emp.bank.account_number
    elif body.field_name == "bank_ifsc" and emp.bank:
        old_val = emp.bank.ifsc
    elif body.field_name == "bank_name" and emp.bank:
        old_val = emp.bank.bank_name
    elif body.field_name == "pan_number":
        old_val = emp.pan_number
    elif body.field_name == "uan_number":
        old_val = emp.uan_number
    elif body.field_name == "legal_name":
        old_val = emp.full_name

    cr = ProfileChangeRequest(
        company_id=emp.company_id,
        employee_id=emp.id,
        user_id=user.id,
        field_name=body.field_name,
        old_value=old_val,
        new_value=body.new_value.strip(),
        reason=body.reason,
        status="pending",
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    log_audit(db, user, "profile.change_request.submit", "change_request", cr.id, {"field": body.field_name})
    return cr


@router.get("/employees/me/change-requests", response_model=list[ProfileChangeRequestOut])
def list_my_change_requests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List change requests submitted by current user."""
    if not user.employee_id:
        return []
    return db.scalars(
        select(ProfileChangeRequest)
        .where(ProfileChangeRequest.employee_id == user.employee_id)
        .order_by(ProfileChangeRequest.id.desc())
    ).all()


@router.get("/change-requests", response_model=list[ProfileChangeRequestOut])
def list_all_change_requests(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """HR and Admin: list all change requests for their company."""
    stmt = select(ProfileChangeRequest).order_by(ProfileChangeRequest.id.desc())
    if user.company_id:
        stmt = stmt.where(ProfileChangeRequest.company_id == user.company_id)
    if status_filter:
        stmt = stmt.where(ProfileChangeRequest.status == status_filter)
    return db.scalars(stmt).all()


@router.post("/change-requests/{request_id}/review", response_model=ProfileChangeRequestOut)
def review_change_request(
    request_id: int,
    body: SensitiveChangeReviewIn,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    """HR and Admin: Approve or reject a sensitive profile change request."""
    cr = db.get(ProfileChangeRequest, request_id)
    if not cr or (user.company_id and cr.company_id != user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change request not found")
    if cr.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Change request is already {cr.status}")

    now = datetime.now(timezone.utc)
    cr.status = body.status
    cr.review_note = body.review_note
    cr.reviewed_by_user_id = user.id
    cr.reviewed_at = now

    emp = db.get(Employee, cr.employee_id)
    if emp and body.status == "approved":
        # Apply approved change to live record
        if cr.field_name == "bank_account_number":
            if not emp.bank:
                emp.bank = BankDetail(company_id=emp.company_id, account_holder=emp.full_name, bank_name="Primary", account_number=cr.new_value, ifsc="IFSC0000000", branch="Main")
            else:
                emp.bank.account_number = cr.new_value
        elif cr.field_name == "bank_ifsc" and emp.bank:
            emp.bank.ifsc = cr.new_value
        elif cr.field_name == "bank_name" and emp.bank:
            emp.bank.bank_name = cr.new_value
        elif cr.field_name == "pan_number":
            emp.pan_number = cr.new_value
        elif cr.field_name == "uan_number":
            emp.uan_number = cr.new_value
        elif cr.field_name == "legal_name":
            parts = cr.new_value.split(" ", 1)
            emp.first_name = parts[0]
            emp.last_name = parts[1] if len(parts) > 1 else ""

    log_audit(db, user, f"profile.change_request.{body.status}", "change_request", cr.id, {
        "field": cr.field_name, "old": cr.old_value, "new": cr.new_value,
    })
    db.commit()
    db.refresh(cr)
    return cr


# ---------------------------- employee documents --------------------------- #
from pathlib import Path
DOCS_DIR = Path(__file__).resolve().parent / "uploads" / "documents"
DOCS_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/employees/{employee_id}/documents", response_model=EmployeeDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    employee_id: int,
    document_type: str = Query(default="ID Proof", description="Document category"),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload an employee document (PDF, PNG, JPG up to 5MB).
    Employees can upload to their own record; HR/Admin can upload for any employee in their company.
    """
    assert_self_or_staff(user, employee_id)
    emp = get_employee_or_404(db, employee_id, company_id=user.company_id)

    allowed_types = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}
    if file.content_type not in allowed_types:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File must be PDF, PNG, or JPEG")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File size must not exceed 5MB")

    safe_name = f"doc_{emp.id}_{int(datetime.now().timestamp())}_{re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename)}"
    dest = DOCS_DIR / safe_name
    with open(dest, "wb") as f:
        f.write(contents)

    doc = EmployeeDocument(
        company_id=emp.company_id,
        employee_id=emp.id,
        document_type=document_type,
        filename=file.filename,
        file_path=str(dest),
        file_size=len(contents),
        mime_type=file.content_type,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    log_audit(db, user, "document.upload", "document", doc.id, {"filename": file.filename})
    return doc


@router.get("/employees/{employee_id}/documents", response_model=list[EmployeeDocumentOut])
def list_documents(employee_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """List documents for an employee. Employees see only their own."""
    assert_self_or_staff(user, employee_id)
    emp = get_employee_or_404(db, employee_id, company_id=user.company_id)
    return db.scalars(
        select(EmployeeDocument)
        .where(EmployeeDocument.employee_id == emp.id)
        .order_by(EmployeeDocument.id.desc())
    ).all()


@router.get("/documents/{document_id}/download")
def download_document(document_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Download an employee document with permission check."""
    doc = db.get(EmployeeDocument, document_id)
    if not doc or (user.company_id and doc.company_id != user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    assert_self_or_staff(user, doc.employee_id)

    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document file not found on disk")

    from fastapi.responses import FileResponse
    return FileResponse(path=file_path, media_type=doc.mime_type, filename=doc.filename)


