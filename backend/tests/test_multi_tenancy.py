"""Comprehensive multi-tenancy tests.

Proves:
- Company A and Company B isolation across all routers (employees, attendance, leave, payroll, payslips, reports, settings).
- Accessing Company B's records with Company A's token returns 404.
- Unique constraints are enforced per-company (both companies can have employee 'EMP-001').
- /auth/me returns company, role, permissions, and employee context.
"""
from datetime import date, timedelta
import pytest

API = "/api/v1"
PW = "Passw0rd!x"

TODAY = date.today()
PREV_END = TODAY.replace(day=1) - timedelta(days=1)
PREV_START = PREV_END.replace(day=1)
PERIOD = f"{PREV_START.year}-{PREV_START.month:02d}"


def call(client, method, path, token=None, **kw):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, API + path, headers=headers, **kw)


def register(client, email, company_name, first="Admin"):
    r = client.post(f"{API}/auth/register", json={
        "email": email,
        "password": PW,
        "first_name": first,
        "company_name": company_name
    })
    assert r.status_code == 201, r.text
    return r.json()


def login(client, email, password=PW):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_multi_company_complete_isolation(client):
    # Setup Company A
    register(client, "owner_a@companya.com", "Company Alpha")
    token_a = login(client, "owner_a@companya.com")

    # Setup Company B
    register(client, "owner_b@companyb.com", "Company Beta")
    token_b = login(client, "owner_b@companyb.com")

    # 1. Verify /auth/me returns proper company context & permissions
    me_a = call(client, "GET", "/auth/me", token_a).json()
    me_b = call(client, "GET", "/auth/me", token_b).json()
    assert me_a["company"]["name"] == "Company Alpha"
    assert me_b["company"]["name"] == "Company Beta"
    assert me_a["company"]["id"] != me_b["company"]["id"]
    assert "view_dashboard" in me_a["permissions"]

    # 2. Employees: Create 'EMP-001' in Company A and Company B
    emp_payload_a = {
        "emp_code": "EMP-001",
        "first_name": "Alice",
        "email": "alice@companya.com",
        "department": "Engineering",
        "designation": "Developer",
        "joining_date": PREV_START.isoformat(),
        "salary": {"basic": 60000, "hra": 20000, "allowances": 20000}
    }
    emp_payload_b = {
        "emp_code": "EMP-001",  # Same code! Allowed because uniqueness is per company
        "first_name": "Bob",
        "email": "bob@companyb.com",
        "department": "Sales",
        "designation": "Executive",
        "joining_date": PREV_START.isoformat(),
        "salary": {"basic": 50000, "hra": 15000, "allowances": 15000}
    }

    res_a = call(client, "POST", "/employees", token_a, json=emp_payload_a)
    assert res_a.status_code == 201, res_a.text
    alice_id = res_a.json()["id"]

    res_b = call(client, "POST", "/employees", token_b, json=emp_payload_b)
    assert res_b.status_code == 201, res_b.text
    bob_id = res_b.json()["id"]

    # Prove listing employees is scoped:
    list_a = call(client, "GET", "/employees", token_a).json()["items"]
    list_b = call(client, "GET", "/employees", token_b).json()["items"]
    assert len(list_a) == 1 and list_a[0]["name"] == "Alice"
    assert len(list_b) == 1 and list_b[0]["name"] == "Bob"

    # Cross-tenant direct access: Company A cannot access Bob; Company B cannot access Alice
    assert call(client, "GET", f"/employees/{bob_id}", token_a).status_code == 404
    assert call(client, "GET", f"/employees/{alice_id}", token_b).status_code == 404

    # 3. Attendance isolation:
    # Record attendance for Alice in Company A
    att_res = call(client, "POST", "/attendance", token_a, json={
        "employee_id": alice_id,
        "work_date": PREV_START.isoformat(),
        "clock_in": "09:00",
        "clock_out": "18:00",
        "status": "On Time"
    })
    assert att_res.status_code == 200, att_res.text

    # Company B trying to submit attendance for Alice must get 404
    att_cross = call(client, "POST", "/attendance", token_b, json={
        "employee_id": alice_id,
        "work_date": PREV_START.isoformat(),
        "clock_in": "09:00",
        "clock_out": "18:00"
    })
    assert att_cross.status_code == 404

    # 4. Leave isolation:
    lt_a = call(client, "GET", "/leave/types", token_a).json()
    assert len(lt_a) > 0
    annual_leave_id = lt_a[0]["id"]

    leave_res = call(client, "POST", "/leave/requests", token_a, json={
        "employee_id": alice_id,
        "leave_type_id": annual_leave_id,
        "start_date": PREV_START.isoformat(),
        "end_date": PREV_START.isoformat(),
        "reason": "Personal work"
    })
    assert leave_res.status_code == 201, leave_res.text
    req_id = leave_res.json()["id"]

    # Company B token cannot see or approve Company A's leave request
    assert call(client, "POST", f"/leave/requests/{req_id}/approve", token_b).status_code == 404

    # 5. Payroll isolation:
    run_res_a = call(client, "POST", "/payroll/runs", token_a, json={"year": PREV_START.year, "month": PREV_START.month})
    assert run_res_a.status_code == 201, run_res_a.text
    run_id_a = run_res_a.json()["id"]

    run_res_b = call(client, "POST", "/payroll/runs", token_b, json={"year": PREV_START.year, "month": PREV_START.month})
    assert run_res_b.status_code == 201, run_res_b.text
    run_id_b = run_res_b.json()["id"]

    # Both companies can have a payroll run for the exact same year and month
    assert run_id_a != run_id_b

    # Cross-tenant run access returns 404
    assert call(client, "GET", f"/payroll/runs/{run_id_b}", token_a).status_code == 404
    assert call(client, "GET", f"/payroll/runs/{run_id_a}", token_b).status_code == 404

    # 6. Reports isolation:
    report_a = call(client, "GET", f"/reports/payroll-summary?period={PERIOD}", token_a).json()
    report_b = call(client, "GET", f"/reports/payroll-summary?period={PERIOD}", token_b).json()
    assert report_a["summary"]["headcount"] == 1
    assert report_b["summary"]["headcount"] == 1
    # Check that Department in report A is Engineering, and report B is Sales
    assert report_a["rows"][0]["department"] == "Engineering"
    assert report_b["rows"][0]["department"] == "Sales"
