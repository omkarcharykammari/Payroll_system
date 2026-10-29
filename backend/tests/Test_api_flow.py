"""End-to-end API tests: auth, access control, the full payroll lifecycle, locking, exports."""
from datetime import date, timedelta

import pytest   

API = "/api/v1"
PW = "Passw0rd!x"

TODAY = date.today()
PREV_END = TODAY.replace(day=1) - timedelta(days=1)
PREV_START = PREV_END.replace(day=1)
PERIOD = f"{PREV_START.year}-{PREV_START.month:02d}"
MONDAY = PREV_START + timedelta(days=(0 - PREV_START.weekday()) % 7)     # first Monday of last month


# ------------------------------- helpers ------------------------------------ #
def call(client, method, path, token=None, **kw):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.request(method, API + path, headers=headers, **kw)


def register(client, email, first="Test"):
    r = client.post(f"{API}/auth/register", json={"email": email, "password": PW, "first_name": first})
    assert r.status_code == 201, r.text
    return r.json()


def login(client, email, password=PW):
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def employee_payload(first, email, with_salary=True, **extra):
    body = {"first_name": first, "last_name": "Rao", "email": email, "department": "Engineering",
            "designation": "Engineer", "joining_date": (PREV_START - timedelta(days=60)).isoformat()}
    if with_salary:
        body["salary"] = {"basic": 50000, "hra": 20000, "allowances": 30000}
    body.update(extra)
    return body


def world(client):
    """admin + hr + two employees (Asha has a login and bank details, Bela has no salary yet)."""
    register(client, "admin@test.com", "Admin")            # first account is the admin
    admin = login(client, "admin@test.com")
    hr_user = register(client, "hr@test.com", "Hira")
    assert call(client, "PATCH", f"/users/{hr_user['id']}", admin, json={"role": "hr"}).status_code == 200
    hr = login(client, "hr@test.com")

    asha = call(client, "POST", "/employees", admin, json=employee_payload(
        "Asha", "asha@test.com", pan_number="ABCDE1234F", login_password=PW,
        bank={"account_holder": "Asha Rao", "bank_name": "HDFC Bank", "account_number": "123456789012",
              "ifsc": "HDFC0001234"}))
    assert asha.status_code == 201, asha.text
    bela = call(client, "POST", "/employees", admin, json=employee_payload("Bela", "bela@test.com", with_salary=False))
    assert bela.status_code == 201, bela.text
    return {"admin": admin, "hr": hr, "asha": asha.json(), "bela": bela.json(), "asha_token": login(client, "asha@test.com")}


def record_attendance(client, w):
    r = call(client, "POST", "/attendance", w["admin"], json={
        "employee_id": w["asha"]["id"], "work_date": MONDAY.isoformat(), "status": "Absent"})
    assert r.status_code == 200, r.text
    r = call(client, "POST", "/attendance", w["admin"], json={
        "employee_id": w["asha"]["id"], "work_date": (MONDAY + timedelta(days=1)).isoformat(),
        "clock_in": "09:00:00", "clock_out": "18:00:00"})
    assert r.status_code == 200, r.text
    return r.json()


def finalized_run(client, w):
    """Create -> fix Bela's missing salary -> review (hr) -> finalize (admin)."""
    run = call(client, "POST", "/payroll/runs", w["admin"], json={"month": PREV_START.month, "year": PREV_START.year})
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    assert call(client, "PUT", f"/employees/{w['bela']['id']}/salary", w["hr"],
                json={"basic": 30000, "hra": 12000, "allowances": 18000}).status_code == 200
    assert call(client, "POST", f"/payroll/runs/{run_id}/recalculate", w["hr"]).status_code == 200
    assert call(client, "POST", f"/payroll/runs/{run_id}/review", w["hr"]).status_code == 200
    assert call(client, "POST", f"/payroll/runs/{run_id}/finalize", w["admin"]).status_code == 200
    return run_id


# --------------------------------- tests ------------------------------------ #
def test_registration_login_and_protected_routes(client):
    first = register(client, "admin@test.com")
    second = register(client, "someone@test.com")
    assert first["role"] == "admin" and second["role"] == "employee"
    assert client.post(f"{API}/auth/register", json={"email": "admin@test.com", "password": PW, "first_name": "X"}).status_code == 409
    assert client.post(f"{API}/auth/login", json={"email": "admin@test.com", "password": "wrong-pass1"}).status_code == 401
    assert client.get(f"{API}/employees").status_code == 401                       # no token
    assert call(client, "GET", "/employees", "garbage.token.value").status_code == 401
    token = login(client, "someone@test.com")
    assert call(client, "GET", "/auth/me", token).json()["email"] == "someone@test.com"
    assert call(client, "GET", "/employees", token).status_code == 403             # plain user, not staff


def test_validation_errors_are_clear(client):
    register(client, "admin@test.com")
    admin = login(client, "admin@test.com")
    bad = employee_payload("Zed", "zed@test.com", pan_number="123")
    r = call(client, "POST", "/employees", admin, json=bad)
    assert r.status_code == 422 and r.json()["errors"][0]["field"] == "pan_number"
    weak = client.post(f"{API}/auth/register", json={"email": "w@test.com", "password": "short", "first_name": "W"})
    assert weak.status_code == 422


def test_employees_search_filter_and_delete(client):
    w = world(client)
    r = call(client, "GET", "/employees?search=asha&department=engineering", w["admin"])
    assert r.status_code == 200 and r.json()["total"] == 1
    assert call(client, "GET", "/employees?status=Terminated", w["admin"]).json()["total"] == 0
    assert call(client, "POST", "/employees", w["admin"], json=employee_payload("Dup", "asha@test.com")).status_code == 409
    assert call(client, "DELETE", f"/employees/{w['bela']['id']}", w["hr"]).status_code == 403   # admin only
    assert call(client, "DELETE", f"/employees/{w['bela']['id']}", w["admin"]).status_code == 204


def test_salary_and_bank_access_control(client):
    w = world(client)
    asha_id, bela_id = w["asha"]["id"], w["bela"]["id"]
    me = call(client, "GET", "/employees/me", w["asha_token"])
    assert me.status_code == 200 and me.json()["salary"]["monthly_gross"] == 100000
    assert "123456789012" not in me.text and me.json()["bank"]["account_number_masked"].endswith("9012")
    assert call(client, "GET", f"/employees/{bela_id}", w["asha_token"]).status_code == 403
    assert call(client, "GET", f"/employees/{asha_id}/bank/reveal", w["asha_token"]).status_code == 403
    revealed = call(client, "GET", f"/employees/{asha_id}/bank/reveal", w["hr"])
    assert revealed.status_code == 200 and revealed.json()["account_number"] == "123456789012"
    logs = call(client, "GET", "/settings/audit-logs?action=bank.", w["admin"]).json()
    assert logs["total"] >= 1                                                       # every reveal is audited


def test_attendance_rules(client):
    w = world(client)
    on_time = record_attendance(client, w)
    assert on_time["status"] == "On Time" and on_time["total_hours"] == 9.0 and on_time["overtime_hours"] == 1.0
    assert call(client, "POST", "/attendance", w["admin"], json={
        "employee_id": w["asha"]["id"], "work_date": (MONDAY + timedelta(days=2)).isoformat(),
        "clock_in": "09:45:00", "clock_out": "18:00:00"}).json()["status"] == "Late"
    future = (TODAY + timedelta(days=3)).isoformat()
    assert call(client, "POST", "/attendance", w["admin"], json={
        "employee_id": w["asha"]["id"], "work_date": future, "clock_in": "09:00:00"}).status_code == 422
    log = call(client, "GET", f"/attendance?date={MONDAY.isoformat()}", w["admin"]).json()
    assert log["stats"]["absent"] == 1


def test_leave_balance_and_approval_rules(client):
    w = world(client)
    types = {t["name"]: t["id"] for t in call(client, "GET", "/leave/types", w["asha_token"]).json()}
    wed = MONDAY + timedelta(days=2)
    body = {"leave_type_id": types["Annual Vacation"], "start_date": wed.isoformat(),
            "end_date": (wed + timedelta(days=1)).isoformat(), "reason": "Trip"}
    req = call(client, "POST", "/leave/requests", w["asha_token"], json=body)
    assert req.status_code == 201 and req.json()["days"] == 2 and req.json()["status"] == "Pending"
    assert call(client, "POST", "/leave/requests", w["asha_token"], json=body).status_code == 409   # overlap
    rid = req.json()["id"]
    assert call(client, "POST", f"/leave/requests/{rid}/approve", w["asha_token"]).status_code == 403
    assert call(client, "POST", f"/leave/requests/{rid}/approve", w["hr"]).status_code == 200
    bal = call(client, "GET", "/leave/balances", w["asha_token"], params={"year": wed.year}).json()
    vacation = next(b for b in bal["items"] if b["leave_type"] == "Annual Vacation")
    assert vacation["used"] == 2 and vacation["available"] == 16
    # shrink the quota to 3 days (2 already used), then ask for 2 more -> only 1 left
    assert call(client, "PUT", f"/leave/balances/{w['asha']['id']}", w["hr"], json={
        "leave_type_id": types["Annual Vacation"], "year": wed.year, "allocated": 3}).status_code == 200
    next_monday = MONDAY + timedelta(days=7)
    over = {**body, "start_date": next_monday.isoformat(), "end_date": (next_monday + timedelta(days=1)).isoformat()}
    r = call(client, "POST", "/leave/requests", w["asha_token"], json=over)
    assert r.status_code == 409 and "Insufficient" in r.json()["detail"]


def test_payroll_lifecycle_calculation_and_locking(client):
    w = world(client)
    record_attendance(client, w)                       # Asha: 1 absent day (loss of pay)
    run = call(client, "POST", "/payroll/runs", w["admin"], json={"month": PREV_START.month, "year": PREV_START.year})
    assert run.status_code == 201, run.text
    run = run.json()
    assert run["status"] == "DRAFT" and run["current_step"] == 2 and run["employee_count"] == 2
    run_id = run["id"]

    # one run per period
    assert call(client, "POST", "/payroll/runs", w["admin"], json={"month": PREV_START.month, "year": PREV_START.year}).status_code == 409

    # Bela has no salary structure -> blocking error -> cannot be reviewed
    exceptions = call(client, "GET", f"/payroll/runs/{run_id}/exceptions", w["hr"]).json()
    assert any(e["code"] == "NO_SALARY_STRUCTURE" for e in exceptions["items"])
    assert call(client, "POST", f"/payroll/runs/{run_id}/review", w["hr"]).status_code == 409

    assert call(client, "PUT", f"/employees/{w['bela']['id']}/salary", w["hr"],
                json={"basic": 30000, "hra": 12000, "allowances": 18000}).status_code == 200
    assert call(client, "POST", f"/payroll/runs/{run_id}/recalculate", w["hr"]).status_code == 200

    items = call(client, "GET", f"/payroll/runs/{run_id}/items", w["hr"]).json()["items"]
    asha = next(i for i in items if i["emp_code"] == w["asha"]["emp_code"])
    assert asha["lop_days"] == 1
    assert asha["overtime_hours"] == 1                                # the 9-hour Tuesday
    assert asha["gross"] == pytest.approx(100000 + asha["overtime_pay"], abs=0.01)   # basic+hra+allowances+overtime
    assert asha["net"] == pytest.approx(asha["gross"] - asha["pf"] - asha["tax"] - asha["other_deductions"], abs=0.01)
    assert asha["lop_deduction"] > 0 and asha["pf"] == 6000           # 12% of 50,000 basic
    totals = call(client, "GET", f"/payroll/runs/{run_id}", w["hr"]).json()
    assert totals["total_net"] == pytest.approx(sum(i["net"] for i in items), abs=0.01)

    # bonus during review sends a reviewed run back to DRAFT
    assert call(client, "POST", f"/payroll/runs/{run_id}/review", w["hr"]).status_code == 200
    adj = call(client, "PATCH", f"/payroll/runs/{run_id}/items/{asha['id']}", w["hr"], json={"bonus": 10000})
    assert adj.status_code == 200 and adj.json()["bonus"] == 10000
    assert adj.json()["gross"] == pytest.approx(asha["gross"] + 10000, abs=0.01)
    assert call(client, "GET", f"/payroll/runs/{run_id}", w["hr"]).json()["status"] == "DRAFT"
    assert call(client, "POST", f"/payroll/runs/{run_id}/review", w["hr"]).status_code == 200

    # separation of duties: HR cannot approve
    assert call(client, "POST", f"/payroll/runs/{run_id}/finalize", w["hr"]).status_code == 403
    fin = call(client, "POST", f"/payroll/runs/{run_id}/finalize", w["admin"])
    assert fin.status_code == 200 and fin.json()["status"] == "FINALIZED" and fin.json()["current_step"] == 4

    # finalized data is locked everywhere
    assert call(client, "POST", f"/payroll/runs/{run_id}/recalculate", w["admin"]).status_code == 409
    assert call(client, "PATCH", f"/payroll/runs/{run_id}/items/{asha['id']}", w["admin"], json={"bonus": 1}).status_code == 409
    assert call(client, "DELETE", f"/payroll/runs/{run_id}", w["admin"]).status_code == 409
    assert call(client, "POST", "/attendance", w["admin"], json={
        "employee_id": w["asha"]["id"], "work_date": MONDAY.isoformat(), "status": "On Time",
        "clock_in": "09:00:00"}).status_code == 409


def test_payslips_visibility_pdf_and_reopen_rules(client):
    w = world(client)
    run_id = finalized_run(client, w)

    slips = call(client, "GET", f"/payslips?period={PERIOD}", w["hr"]).json()
    assert slips["total"] == 2 and all(s["status"] == "Draft" for s in slips["items"])
    assert call(client, "GET", f"/payslips?period={PERIOD}", w["asha_token"]).json()["total"] == 0   # not published yet
    asha_slip = next(s for s in slips["items"] if s["emp_code"] == w["asha"]["emp_code"])
    bela_slip = next(s for s in slips["items"] if s["emp_code"] == w["bela"]["emp_code"])
    assert call(client, "GET", f"/payslips/{asha_slip['id']}", w["asha_token"]).status_code == 404

    pub = call(client, "POST", "/payslips/publish", w["hr"], json={"run_id": run_id})
    assert pub.status_code == 200 and pub.json()["published"] == 2

    assert call(client, "GET", f"/payslips?period={PERIOD}", w["asha_token"]).json()["total"] == 1
    pdf = call(client, "GET", f"/payslips/{asha_slip['id']}/download", w["asha_token"])
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf" and pdf.content[:5] == b"%PDF-"
    assert call(client, "GET", f"/payslips/{bela_slip['id']}/download", w["asha_token"]).status_code == 404

    # published payslips cannot be recalled, and paid runs can never be reopened
    reopen = call(client, "POST", f"/payroll/runs/{run_id}/reopen", w["admin"], json={"reason": "Wrong bonus entered"})
    assert reopen.status_code == 409
    assert call(client, "POST", f"/payroll/runs/{run_id}/mark-paid", w["admin"]).json()["status"] == "PAID"
    assert call(client, "POST", f"/payroll/runs/{run_id}/reopen", w["admin"], json={"reason": "Trying anyway ok"}).status_code == 409


def test_reopen_workflow_before_publishing(client):
    w = world(client)
    run_id = finalized_run(client, w)
    assert call(client, "POST", f"/payroll/runs/{run_id}/reopen", w["admin"], json={"reason": "short"}).status_code == 422
    assert call(client, "POST", f"/payroll/runs/{run_id}/reopen", w["hr"], json={"reason": "Bonus was wrong"}).status_code == 403
    r = call(client, "POST", f"/payroll/runs/{run_id}/reopen", w["admin"], json={"reason": "Bonus was entered wrongly"})
    assert r.status_code == 200 and r.json()["status"] == "DRAFT"
    assert call(client, "GET", f"/payslips?period={PERIOD}", w["hr"]).json()["total"] == 0        # draft payslips removed
    audit = call(client, "GET", "/settings/audit-logs?action=payroll.run.reopen", w["admin"]).json()
    assert audit["total"] == 1 and "wrongly" in audit["items"][0]["detail"]["reason"]


def test_reports_exports_and_dashboard(client):
    w = world(client)
    run_id = finalized_run(client, w)
    reg = call(client, "GET", f"/reports/payroll-register?period={PERIOD}", w["hr"]).json()
    assert len(reg["rows"]) == 2 and reg["summary"]["emp_code"] == "Total"
    summary = call(client, "GET", f"/reports/payroll-summary?period={PERIOD}", w["hr"]).json()
    assert summary["rows"][0]["department"] == "Engineering" and summary["summary"]["headcount"] == 2

    xlsx = call(client, "GET", f"/reports/payroll-register/export?period={PERIOD}&format=xlsx", w["hr"])
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK" and "spreadsheetml" in xlsx.headers["content-type"]
    csv_resp = call(client, "GET", f"/reports/tax-liabilities/export?period={PERIOD}&format=csv", w["hr"])
    assert csv_resp.status_code == 200 and "Income Tax" in csv_resp.content.decode("utf-8-sig")
    assert call(client, "GET", "/reports/nonsense", w["hr"]).status_code == 404
    assert call(client, "GET", f"/reports/payroll-register?period={PERIOD}", w["asha_token"]).status_code == 403

    assert len(call(client, "GET", "/reports/recent", w["hr"]).json()) == 2

    dash = call(client, "GET", "/dashboard", w["admin"]).json()
    assert dash["current_run"]["id"] == run_id and dash["stats"]["net_pay"] > 0
    assert dash["employees"]["total_active"] == 2 and dash["banner"]["action"] == "mark_paid"
    assert "trends" in dash
    assert len(dash["trends"]["attendance"]) == 14
    assert len(dash["trends"]["payroll_cost"]) >= 1
    assert "leave_by_type" in dash["trends"]


def test_dashboard_me_and_employee_access_control(client):
    w = world(client)
    run_id = finalized_run(client, w)

    # 1. Staff get trends on /dashboard; employee gets 403 on /dashboard
    dash = call(client, "GET", "/dashboard", w["admin"]).json()
    assert "trends" in dash
    assert len(dash["trends"]["attendance"]) == 14
    assert len(dash["trends"]["payroll_cost"]) >= 1
    assert "leave_by_type" in dash["trends"]
    assert call(client, "GET", "/dashboard", w["asha_token"]).status_code == 403

    # 2. Employee gets 200 on /dashboard/me
    me_resp = call(client, "GET", "/dashboard/me", w["asha_token"])
    assert me_resp.status_code == 200
    me_dash = me_resp.json()
    assert me_dash["linked"] is True
    assert me_dash["employee"]["name"] == "Asha Rao"
    assert me_dash["employee"]["emp_code"] == w["asha"]["emp_code"]
    assert "today" in me_dash and "status" in me_dash["today"]
    assert "leave_balances" in me_dash and isinstance(me_dash["leave_balances"], list)
    assert me_dash["pending_leave_requests"] == 0
    assert "upcoming_holidays" in me_dash

    # 3. Employee never sees Draft payslips or another employee's data
    # Before publishing, payslip is draft -> latest_payslip is None and net_pay_trend is empty
    assert me_dash["latest_payslip"] is None
    assert len(me_dash["net_pay_trend"]) == 0

    # Publish the run
    call(client, "POST", "/payslips/publish", w["hr"], json={"run_id": run_id})

    # After publishing, employee sees own published payslip and trend
    me_dash_after = call(client, "GET", "/dashboard/me", w["asha_token"]).json()
    assert me_dash_after["latest_payslip"] is not None
    assert me_dash_after["latest_payslip"]["status"] == "Published"
    assert me_dash_after["latest_payslip"]["net"] > 0
    assert len(me_dash_after["net_pay_trend"]) >= 1
    assert me_dash_after["net_pay_trend"][-1]["period"] == PERIOD

    # 4. Unlinked account returns linked=false
    register(client, "unlinked@test.com", "Unlinked")
    unlinked_tok = login(client, "unlinked@test.com")
    unlinked_dash = call(client, "GET", "/dashboard/me", unlinked_tok).json()
    assert unlinked_dash["linked"] is False
    assert "not linked to an employee" in unlinked_dash["message"]


def test_settings_slab_validation_and_effect(client):
    w = world(client)
    gap = [{"lower": 0, "upper": 400000, "rate_percent": 0}, {"lower": 500000, "upper": None, "rate_percent": 10}]
    assert call(client, "PUT", "/settings/tax-slabs", w["admin"], json=gap).status_code == 422
    assert call(client, "PUT", "/settings/tax-slabs", w["hr"], json=gap).status_code == 403
    cfg = call(client, "GET", "/settings/payroll", w["hr"]).json()
    cfg["pf_rate"] = 10
    assert call(client, "PUT", "/settings/payroll", w["admin"], json=cfg).status_code == 200
    run = call(client, "POST", "/payroll/runs", w["admin"], json={"month": PREV_START.month, "year": PREV_START.year}).json()
    items = call(client, "GET", f"/payroll/runs/{run['id']}/items", w["admin"]).json()["items"]
    asha = next(i for i in items if i["emp_code"] == w["asha"]["emp_code"])
    assert asha["pf"] == 5000                                         # 10% of 50,000 now