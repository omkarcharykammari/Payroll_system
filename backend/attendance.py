"""Daily attendance: clock-in/out, manual entries, the daily log and monthly summaries.
All data scoped by tenant Company.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from auth import get_current_user, is_staff, require_staff
from database import get_db
from models import (
    ATT_ABSENT, ATT_HALF_DAY, ATT_LATE, ATT_NOT_MARKED, ATT_ON_LEAVE, ATT_ON_TIME, EMP_ACTIVE, EMP_INACTIVE,
    LEAVE_APPROVED, Attendance, Department, Employee, LeaveRequest, User,
)
from payroll_engine import q2
from schemas import AttendanceIn, PayrollConfig
from settings import get_config
from utils import (
    assert_period_unlocked, holidays_between, log_audit, now_local, parse_period, month_bounds,
    today_local, working_days,
)

router = APIRouter(prefix="/attendance", tags=["Attendance"])

PRESENT_STATUSES = (ATT_ON_TIME, ATT_LATE, ATT_HALF_DAY)


# --------------------------------- rules ----------------------------------- #
def derive_status(clock_in: Optional[time], hours: Decimal, cfg: PayrollConfig, clock_out: Optional[time]) -> str:
    if clock_in is None:
        return ATT_ABSENT
    cutoff = (datetime.combine(date.min, cfg.shift_start) + timedelta(minutes=cfg.late_grace_minutes)).time()
    if clock_out is not None and hours < cfg.half_day_hours:
        return ATT_HALF_DAY
    return ATT_LATE if clock_in > cutoff else ATT_ON_TIME


def worked_hours(clock_in: Optional[time], clock_out: Optional[time], work_date: date) -> Decimal:
    if not (clock_in and clock_out):
        return Decimal("0")
    delta = datetime.combine(work_date, clock_out) - datetime.combine(work_date, clock_in)
    return q2(Decimal(delta.total_seconds()) / Decimal(3600))


def overtime_for(hours: Decimal, cfg: PayrollConfig) -> Decimal:
    return max(Decimal("0"), q2(hours - cfg.standard_hours_per_day))


def _fmt_time(t: Optional[time]) -> str:
    return t.strftime("%I:%M %p") if t else "--:--"


def row_dict(emp: Employee, rec: Optional[Attendance], work_date: date, virtual_status: Optional[str] = None) -> dict:
    return {
        "attendance_id": rec.id if rec else None,
        "employee_id": emp.id, "emp_code": emp.emp_code, "name": emp.full_name,
        "department": emp.department.name if emp.department else None,
        "work_date": work_date,
        "clock_in": rec.clock_in if rec else None, "clock_out": rec.clock_out if rec else None,
        "clock_in_display": _fmt_time(rec.clock_in if rec else None),
        "clock_out_display": _fmt_time(rec.clock_out if rec else None),
        "total_hours": rec.working_hours if rec else Decimal("0"),
        "overtime_hours": rec.overtime_hours if rec else Decimal("0"),
        "status": rec.status if rec else virtual_status,
    }


# ------------------------------- self service ------------------------------ #
def _my_employee(user: User) -> int:
    if not user.employee_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your login is not linked to an employee record")
    return user.employee_id


@router.post("/clock-in", status_code=status.HTTP_201_CREATED)
def clock_in(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    emp = db.get(Employee, _my_employee(user))
    if not emp or (user.company_id and emp.company_id != user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    now = now_local()
    today = now.date()
    assert_period_unlocked(db, today, "attendance", company_id=user.company_id)
    if db.scalar(select(Attendance.id).where(Attendance.employee_id == emp.id, Attendance.work_date == today)):
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already clocked in today")
    cfg = get_config(db, company_id=user.company_id)
    t = now.time().replace(microsecond=0, tzinfo=None)
    rec = Attendance(
        company_id=user.company_id,
        employee_id=emp.id,
        work_date=today,
        clock_in=t,
        status=derive_status(t, Decimal(0), cfg, None)
    )
    db.add(rec)
    db.commit()
    return row_dict(emp, rec, today)


@router.post("/clock-out")
def clock_out(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    emp = db.get(Employee, _my_employee(user))
    if not emp or (user.company_id and emp.company_id != user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    now = now_local()
    today = now.date()
    rec = db.scalar(select(Attendance).where(Attendance.employee_id == emp.id, Attendance.work_date == today))
    if not rec or not rec.clock_in:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have not clocked in today")
    if rec.clock_out:
        raise HTTPException(status.HTTP_409_CONFLICT, "You have already clocked out today")
    t = now.time().replace(microsecond=0, tzinfo=None)
    if t <= rec.clock_in:
        raise HTTPException(status.HTTP_409_CONFLICT, "Clock-out must be after clock-in")
    cfg = get_config(db, company_id=user.company_id)
    rec.clock_out = t
    rec.working_hours = worked_hours(rec.clock_in, t, today)
    rec.overtime_hours = overtime_for(rec.working_hours, cfg)
    rec.status = derive_status(rec.clock_in, rec.working_hours, cfg, t)
    db.commit()
    return row_dict(emp, rec, today)


# ------------------------------- staff entry -------------------------------- #
@router.post("", summary="Create or correct one employee's attendance for a day")
def upsert_attendance(body: AttendanceIn, user: User = Depends(require_staff), db: Session = Depends(get_db)):
    emp = db.get(Employee, body.employee_id)
    if not emp or (user.company_id and emp.company_id != user.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    if body.work_date > today_local():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cannot record attendance for a future date")
    if body.work_date < emp.joining_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Date is before the employee's joining date")
    assert_period_unlocked(db, body.work_date, "attendance", company_id=user.company_id)

    cfg = get_config(db, company_id=user.company_id)
    hours = worked_hours(body.clock_in, body.clock_out, body.work_date)
    final_status = body.status or derive_status(body.clock_in, hours, cfg, body.clock_out)
    if final_status != ATT_ABSENT and body.clock_in is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"A '{final_status}' day needs a clock_in time")
    if final_status == ATT_ABSENT:
        clock_in = clock_out = None
        hours = Decimal("0")
    else:
        clock_in, clock_out = body.clock_in, body.clock_out

    rec = db.scalar(select(Attendance).where(Attendance.employee_id == emp.id, Attendance.work_date == body.work_date))
    created = rec is None
    if created:
        rec = Attendance(company_id=user.company_id, employee_id=emp.id, work_date=body.work_date)
        db.add(rec)
    rec.clock_in, rec.clock_out = clock_in, clock_out
    rec.working_hours = hours
    rec.overtime_hours = overtime_for(hours, cfg) if clock_out else Decimal("0")
    rec.status = final_status
    log_audit(db, user, "attendance.upsert", "attendance", None,
              {"employee_id": emp.id, "date": str(body.work_date), "status": final_status})
    db.commit()
    return row_dict(emp, rec, body.work_date)


# --------------------------------- daily log -------------------------------- #
@router.get("")
def daily_log(
    day: Optional[date] = Query(default=None, alias="date", description="Defaults to today"),
    department: Optional[str] = Query(default=None, description="Department name"),
    search: Optional[str] = Query(default=None, max_length=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    day = day or today_local()
    stmt = (select(Employee).outerjoin(Department).options(selectinload(Employee.department))
            .where(Employee.status == EMP_ACTIVE, Employee.joining_date <= day).order_by(Employee.emp_code))
    if user.company_id:
        stmt = stmt.where(Employee.company_id == user.company_id)
    if not is_staff(user):
        stmt = stmt.where(Employee.id == (user.employee_id or -1))
    if department:
        stmt = stmt.where(Department.name.ilike(department))
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where((Employee.first_name + " " + Employee.last_name).ilike(like))
    employees = db.scalars(stmt).all()
    ids = [e.id for e in employees]

    records = {r.employee_id: r for r in db.scalars(
        select(Attendance).where(Attendance.work_date == day, Attendance.employee_id.in_(ids or [-1])))}
    on_leave_ids = set(db.scalars(
        select(LeaveRequest.employee_id).where(
            LeaveRequest.status == LEAVE_APPROVED, LeaveRequest.start_date <= day, LeaveRequest.end_date >= day,
            LeaveRequest.employee_id.in_(ids or [-1]))))
    cfg = get_config(db, company_id=user.company_id)
    non_working = day.weekday() in cfg.weekly_off_days or bool(holidays_between(db, day, day, company_id=user.company_id))

    items, counts = [], {ATT_ON_TIME: 0, ATT_LATE: 0, ATT_HALF_DAY: 0, ATT_ON_LEAVE: 0, ATT_ABSENT: 0, ATT_NOT_MARKED: 0}
    for emp in employees:
        rec = records.get(emp.id)
        if rec:
            counts[rec.status] = counts.get(rec.status, 0) + 1
            items.append(row_dict(emp, rec, day))
        elif emp.id in on_leave_ids:
            counts[ATT_ON_LEAVE] += 1
            items.append(row_dict(emp, None, day, ATT_ON_LEAVE))
        elif non_working:
            items.append(row_dict(emp, None, day, "Day Off"))
        else:
            counts[ATT_NOT_MARKED] += 1
            items.append(row_dict(emp, None, day, ATT_NOT_MARKED))

    total = len(employees)
    present = counts[ATT_ON_TIME] + counts[ATT_LATE] + counts[ATT_HALF_DAY]
    return {
        "date": day, "is_working_day": not non_working,
        "stats": {
            "total": total, "present": present, "on_time": counts[ATT_ON_TIME], "late": counts[ATT_LATE],
            "half_day": counts[ATT_HALF_DAY], "on_leave": counts[ATT_ON_LEAVE],
            "absent": counts[ATT_ABSENT], "not_marked": counts[ATT_NOT_MARKED],
            "present_percent": round(present * 100 / total, 1) if total else 0,
        },
        "items": items,
    }


# -------------------------------- monthly summary --------------------------- #
def monthly_summary(db: Session, year: int, month: int, department: Optional[str] = None, company_id: Optional[int] = None) -> list[dict]:
    start, end = month_bounds(year, month)
    cfg = get_config(db, company_id=company_id)
    upto = min(end, today_local())
    wdays = working_days(start, upto, cfg.weekly_off_days, holidays_between(db, start, end, company_id=company_id)) if upto >= start else []
    stmt = (select(Employee).outerjoin(Department).options(selectinload(Employee.department))
            .where(Employee.joining_date <= end, Employee.status != EMP_INACTIVE).order_by(Employee.emp_code))
    if company_id:
        stmt = stmt.where(Employee.company_id == company_id)
    if department:
        stmt = stmt.where(Department.name.ilike(department))
    employees = [e for e in db.scalars(stmt) if not (e.exit_date and e.exit_date < start)]

    att_stmt = select(Attendance).where(Attendance.work_date.between(start, end))
    if company_id:
        att_stmt = att_stmt.where(Attendance.company_id == company_id)
    recs: dict[int, list[Attendance]] = {}
    for r in db.scalars(att_stmt):
        recs.setdefault(r.employee_id, []).append(r)

    rows = []
    for emp in employees:
        mine = recs.get(emp.id, [])
        by_status = lambda s: sum(1 for r in mine if r.status == s)
        rows.append({
            "emp_code": emp.emp_code, "name": emp.full_name,
            "department": emp.department.name if emp.department else None,
            "working_days": len(wdays), "present": by_status(ATT_ON_TIME) + by_status(ATT_LATE),
            "late": by_status(ATT_LATE), "half_days": by_status(ATT_HALF_DAY), "absent": by_status(ATT_ABSENT),
            "recorded_days": len(mine),
            "total_hours": sum((r.working_hours for r in mine), Decimal("0")),
            "overtime_hours": sum((r.overtime_hours for r in mine), Decimal("0")),
        })
    return rows


@router.get("/summary")
def attendance_summary(period: str = Query(description="YYYY-MM, e.g. 2026-09"), department: Optional[str] = None,
                       user: User = Depends(require_staff), db: Session = Depends(get_db)):
    year, month = parse_period(period)
    return {"period": period, "items": monthly_summary(db, year, month, department, company_id=user.company_id)}