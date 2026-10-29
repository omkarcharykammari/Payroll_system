"""Seed realistic demo data for Vertex.

    cd backend
    python ../database/seed.py            # seeds an empty database
    python ../database/seed.py --reset    # DROPS every table first, then seeds

Everything is generated relative to *today*: two closed payroll months, the
current month's attendance up to yesterday, approved / pending / upcoming leave.
The seed drives the real route functions (leave approval, payroll create ->
review -> finalize -> paid, publishing), so the demo data obeys the same rules
as live data. Passwords are for LOCAL DEMO ONLY.
"""
import argparse
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

import attendance as attendance_mod  # noqa: E402
import leave as leave_mod  # noqa: E402
import payroll as payroll_mod  # noqa: E402
import payslips as payslips_mod  # noqa: E402
from auth import hash_password  # noqa: E402
from bootstrap import ensure_defaults  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
from models import (  # noqa: E402
    ATT_ABSENT, ATT_HALF_DAY, BankDetail, Attendance, Company, Department, Employee, Holiday, LeaveRequest,
    LeaveType, PayrollItem, Payslip, ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_HR, SalaryStructure, User,
)
from schemas import ItemUpdate, LeaveRequestIn, PublishIn, ReviewIn, RunCreate  # noqa: E402
from settings import get_config  # noqa: E402
from utils import today_local  # noqa: E402

PASSWORD = os.getenv("SEED_PASSWORD", "Vertex@2026")
FEMALE = {"Priya", "Ananya", "Neha", "Meera", "Aditi", "Pooja", "Sneha", "Ishita", "Tanvi"}
BANKS = [("HDFC Bank", "HDFC0001234"), ("ICICI Bank", "ICIC0000456"), ("State Bank of India", "SBIN0001122"),
         ("Axis Bank", "UTIB0000789")]

# first, last, department, designation, type, basic, hra, allowances, has_bank, pf_enabled
EMPLOYEES = [
    ("Arjun", "Desai", "Engineering", "Senior Software Engineer", "Full-time", 80000, 32000, 48000, True, True),
    ("Priya", "Nair", "Engineering", "Software Engineer", "Full-time", 50000, 20000, 30000, True, True),
    ("Rohan", "Mehta", "Engineering", "Backend Developer", "Full-time", 60000, 24000, 36000, True, True),
    ("Ananya", "Iyer", "Engineering", "QA Engineer", "Full-time", 38000, 15200, 22800, True, True),
    ("Karthik", "Reddy", "Engineering", "DevOps Engineer", "Full-time", 70000, 28000, 42000, True, True),
    ("Neha", "Kapoor", "Human Resources", "HR Manager", "Full-time", 55000, 22000, 33000, True, True),
    ("Sanjay", "Gupta", "Human Resources", "Recruiter", "Full-time", 32000, 12800, 19200, True, True),
    ("Meera", "Joshi", "Design", "Lead Designer", "Full-time", 65000, 26000, 39000, True, True),
    ("Vikram", "Singh", "Design", "UI Designer", "Full-time", 40000, 16000, 24000, True, True),
    ("Aditi", "Sharma", "Sales", "Sales Manager", "Full-time", 60000, 24000, 36000, True, True),
    ("Rahul", "Verma", "Sales", "Account Executive", "Full-time", 35000, 14000, 21000, True, True),
    ("Pooja", "Patel", "Sales", "Sales Associate", "Full-time", 25000, 10000, 15000, True, True),
    ("Manish", "Kulkarni", "Product", "Product Manager", "Full-time", 90000, 36000, 54000, True, True),
    ("Sneha", "Bose", "Product", "Business Analyst", "Full-time", 48000, 19200, 28800, True, True),
    ("Deepak", "Chauhan", "Marketing", "Marketing Manager", "Full-time", 58000, 23200, 34800, True, True),
    ("Ishita", "Malhotra", "Marketing", "Content Strategist", "Part-time", 22000, 8800, 13200, True, True),
    ("Farhan", "Qureshi", "Engineering", "Contract Developer", "Contract", 45000, 0, 15000, False, False),
    ("Tanvi", "Deshmukh", "Design", "Design Intern", "Intern", 15000, 0, 0, True, False),
    ("Kabir", "Saxena", "Engineering", "Junior Developer", "Full-time", 30000, 12000, 18000, True, True),  # joins mid-month
]


def month_start(d: date) -> date:
    return d.replace(day=1)


def working_day_on_or_after(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def reset_database() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def seed() -> None:
    today = today_local()
    m_cur = month_start(today)
    m1 = month_start(m_cur - timedelta(days=1))      # last month
    m2 = month_start(m1 - timedelta(days=1))         # the month before

    with SessionLocal() as db:
        # ---- Companies -------------------------------------------------------- #
        c1 = db.scalar(select(Company).where(Company.slug == "vertex-enterprise"))
        if not c1:
            c1 = Company(name="Vertex Enterprise", slug="vertex-enterprise", legal_name="Vertex Enterprise Pvt Ltd", address="Pune, Maharashtra")
            db.add(c1)
            db.flush()

        c2 = db.scalar(select(Company).where(Company.slug == "acme-corp"))
        if not c2:
            c2 = Company(name="Acme Corp", slug="acme-corp", legal_name="Acme Global Corporation", address="Austin, Texas")
            db.add(c2)
            db.flush()

        ensure_defaults(db, company_id=c1.id)
        ensure_defaults(db, company_id=c2.id)

        cfg = get_config(db, company_id=c1.id)
        rng = random.Random(2026)

        # ---- holidays (fixed-date national days only - scoped to c1) ----------- #
        for year in {m2.year, today.year}:
            for (m, d, name) in [(1, 26, "Republic Day"), (8, 15, "Independence Day"),
                                 (10, 2, "Gandhi Jayanti"), (12, 25, "Christmas")]:
                if not db.scalar(select(Holiday.id).where(Holiday.company_id == c1.id, Holiday.holiday_date == date(year, m, d))):
                    db.add(Holiday(company_id=c1.id, holiday_date=date(year, m, d), name=name))
        db.commit()
        holidays = {h for h in db.scalars(select(Holiday.holiday_date).where(Holiday.company_id == c1.id))}

        # ---- departments & employees (c1) ------------------------------------- #
        depts = {}
        for name in sorted({e[2] for e in EMPLOYEES}):
            depts[name] = Department(company_id=c1.id, name=name)
            db.add(depts[name])
        db.flush()

        employees = []
        for i, (first, last, dept, desig, etype, basic, hra, allow, has_bank, pf) in enumerate(EMPLOYEES, start=1):
            joined = (m1 + timedelta(days=14)) if first == "Kabir" else m2 - timedelta(days=200 + i * 37)
            bank_name, ifsc = BANKS[i % len(BANKS)]
            emp = Employee(
                company_id=c1.id,
                emp_code=f"EMP-{i:03d}", first_name=first, last_name=last, email=f"{first}.{last}@vertex.com".lower(),
                phone=f"98{20000000 + i * 1234567:08d}", date_of_birth=date(1984 + i % 14, 1 + i % 12, 3 + i % 25),
                gender="Female" if first in FEMALE else "Male", address=f"{10 + i}, MG Road, Pune",
                pan_number=f"{(last[:3] + first[:2]).upper()}{1000 + i * 37:04d}{chr(65 + i % 26)}",
                uan_number=f"1002{i:08d}", department_id=depts[dept].id, designation=desig, employment_type=etype,
                joining_date=joined, status="Active")
            emp.salary = SalaryStructure(basic=Decimal(basic), hra=Decimal(hra), allowances=Decimal(allow), pf_enabled=pf)
            if has_bank:
                emp.bank = BankDetail(account_holder=f"{first} {last}", bank_name=bank_name,
                                      account_number=str(50100000000000 + i * 7919), ifsc=ifsc, branch="Pune Main")
            db.add(emp)
            employees.append(emp)
        db.flush()
        by_code = {e.emp_code: e for e in employees}
        neha = next(e for e in employees if e.first_name == "Neha")
        arjun = employees[0]

        pw = hash_password(PASSWORD)
        admin = User(company_id=c1.id, email="admin@vertex.com", hashed_password=pw, first_name="Vertex", last_name="Admin",
                     job_title="Payroll Administrator", role=ROLE_ADMIN)
        hr = User(company_id=c1.id, email="hr@vertex.com", hashed_password=pw, first_name="Neha", last_name="Kapoor",
                  job_title="HR Manager", role=ROLE_HR, employee_id=neha.id)
        emp_user = User(company_id=c1.id, email="arjun.desai@vertex.com", hashed_password=pw, first_name="Arjun", last_name="Desai",
                        job_title=arjun.designation, role=ROLE_EMPLOYEE, employee_id=arjun.id)
        
        # User for Company 2 (Acme Corp)
        acme_admin = User(company_id=c2.id, email="admin@acme.com", hashed_password=pw, first_name="Acme", last_name="Admin",
                          job_title="Acme Administrator", role=ROLE_ADMIN)

        db.add_all([admin, hr, emp_user, acme_admin])
        db.commit()

        # ---- leave (through the real route functions) ------------------------- #
        types = {t.name: t.id for t in db.scalars(select(LeaveType).where(LeaveType.company_id == c1.id))}

        def apply(code, type_name, start, n_days, approve, reason):
            start = working_day_on_or_after(start)
            end, counted = start, 1
            while counted < n_days:
                end += timedelta(days=1)
                counted += end.weekday() < 5
            end = min(end, date(start.year, 12, 31))
            try:
                req = leave_mod.create_request(LeaveRequestIn(
                    employee_id=by_code[code].id, leave_type_id=types[type_name],
                    start_date=start, end_date=end, reason=reason), user=admin, db=db)
                if approve:
                    leave_mod.approve_request(req["id"], ReviewIn(), user=admin, db=db)
            except HTTPException as exc:                      # e.g. year-end edge cases
                print(f"  (skipped leave for {code}: {exc.detail})")

        apply("EMP-002", "Annual Vacation", m2 + timedelta(days=8), 4, True, "Family trip")
        apply("EMP-006", "Annual Vacation", m2 + timedelta(days=15), 3, True, "Personal")
        apply("EMP-003", "Sick Leave", m1 + timedelta(days=5), 2, True, "Fever")
        apply("EMP-009", "Unpaid Leave", m1 + timedelta(days=12), 2, True, "Personal work")
        apply("EMP-008", "Annual Vacation", today + timedelta(days=21), 4, True, "Holiday")        # upcoming
        apply("EMP-004", "Annual Vacation", today + timedelta(days=10), 3, False, "Wedding")         # pending
        apply("EMP-005", "Sick Leave", today + timedelta(days=4), 1, False, "Medical check-up")       # pending
        apply("EMP-010", "Annual Vacation", today + timedelta(days=30), 5, False, "Vacation")         # pending

        leave_days = {}
        for r in db.scalars(select(LeaveRequest).where(LeaveRequest.company_id == c1.id, LeaveRequest.status == "Approved")):
            leave_days.setdefault(r.employee_id, set()).update(
                r.start_date + timedelta(days=n) for n in range((r.end_date - r.start_date).days + 1))

        # ---- attendance: m2 start -> yesterday -------------------------------- #
        count, d = 0, m2
        while d < today:
            if d.weekday() not in cfg.weekly_off_days and d not in holidays:
                for emp in employees:
                    if d < emp.joining_date or d in leave_days.get(emp.id, set()):
                        continue
                    roll = rng.random()
                    if roll < 0.03:
                        rec = Attendance(company_id=c1.id, employee_id=emp.id, work_date=d, status=ATT_ABSENT)
                    else:
                        if roll < 0.05:
                            cin, hours = time(9, rng.randint(0, 20)), Decimal("4.0")
                        elif roll < 0.15:
                            cin, hours = time(9, rng.randint(12, 55)), Decimal("8.5")
                        else:
                            cin, hours = time(8, rng.randint(35, 59)), Decimal("8.0")
                        extra = rng.choice([0, 0, 0, 5, 10]) if hours >= 8 else 0
                        if hours >= 8 and rng.random() < 0.08:
                            extra = rng.choice([60, 90, 120, 150])
                        cout = (datetime.combine(d, cin) + timedelta(hours=float(hours), minutes=extra)).time()
                        worked = attendance_mod.worked_hours(cin, cout, d)
                        rec = Attendance(
                            company_id=c1.id,
                            employee_id=emp.id, work_date=d, clock_in=cin, clock_out=cout, working_hours=worked,
                            overtime_hours=attendance_mod.overtime_for(worked, cfg),
                            status=attendance_mod.derive_status(cin, worked, cfg, cout))
                    db.add(rec)
                    count += 1
            d += timedelta(days=1)
        db.commit()
        print(f"  {len(employees)} employees, {count} attendance records for {c1.name}")

        # ---- payroll: two closed months ---------------------------------------- #
        def item_id(run_id, code):
            return db.scalar(select(PayrollItem.id).where(PayrollItem.run_id == run_id, PayrollItem.emp_code == code))

        run2 = payroll_mod.create_run(RunCreate(month=m2.month, year=m2.year), user=admin, db=db)["id"]
        payroll_mod.adjust_item(run2, item_id(run2, "EMP-008"),
                                ItemUpdate(bonus=Decimal("25000"), adjustment_note="Quarterly performance bonus"),
                                user=admin, db=db)
        payroll_mod.review_run(run2, user=hr, db=db)
        payroll_mod.finalize_run(run2, user=admin, db=db)
        payroll_mod.mark_paid(run2, user=admin, db=db)
        payslips_mod.publish_all(PublishIn(run_id=run2), user=admin, db=db)

        run1 = payroll_mod.create_run(RunCreate(month=m1.month, year=m1.year), user=admin, db=db)["id"]
        payroll_mod.adjust_item(run1, item_id(run1, "EMP-015"),
                                ItemUpdate(manual_deduction=Decimal("3000"), adjustment_note="Salary advance recovery"),
                                user=admin, db=db)
        payroll_mod.review_run(run1, user=hr, db=db)
        payroll_mod.finalize_run(run1, user=admin, db=db)
        for pid in db.scalars(select(Payslip.id).where(Payslip.run_id == run1).order_by(Payslip.id).limit(3)).all():
            payslips_mod.publish_one(pid, user=admin, db=db)
        print(f"  payroll runs: {m2:%B %Y} (paid, published) and {m1:%B %Y} (finalized, 3 payslips published)")
        print(f"  {m_cur:%B %Y}: no run yet - create it from the Payroll page / POST /payroll/runs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Vertex demo data")
    parser.add_argument("--reset", action="store_true", help="DROP all tables first")
    args = parser.parse_args()

    if args.reset:
        print("Resetting database ...")
        reset_database()
    else:
        Base.metadata.create_all(engine)
        with SessionLocal() as probe:
            if probe.scalar(select(Employee.id).limit(1)) or probe.scalar(select(User.id).limit(1)):
                sys.exit("Database already has data. Use --reset to wipe and re-seed.")
    print("Seeding ...")
    seed()
    print("\nDone. Demo logins (local use only):")
    for who, email in (("Admin (Vertex)", "admin@vertex.com"),
                       ("HR (Vertex)", "hr@vertex.com"),
                       ("Employee (Vertex)", "arjun.desai@vertex.com"),
                       ("Admin (Acme)", "admin@acme.com")):
        print(f"  {who:<20} {email:<26} password: {PASSWORD}")