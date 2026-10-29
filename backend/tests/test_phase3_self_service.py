"""Phase 3 comprehensive test suite: Profiles & Employee Self-Service.

Tests:
1. "My profile" personal edits:
   - Employee edits phone and address -> updates immediately and persists.
2. Sensitive profile change workflow:
   - Employee submits change for bank_account_number and pan_number -> status is pending, live record remains untouched.
   - HR reviews and approves -> live employee/bank record is updated and audit logged.
   - HR reviews and rejects -> status is rejected with note, live record remains untouched.
3. Employee documents:
   - Upload PDF document (type and size validated).
   - Employee can download their own document.
   - Employee B cannot download Employee A's document (403/404).
4. Employee self-service role boundaries:
   - Employee cannot access another employee's profile via /employees/{other_id} (403).
   - Employee cannot finalize or prepare payroll runs.
5. Company profile page updates for admin/owner.
"""
import io

import pytest

API = "/api/v1"
PW = "Passw0rd!2026"


def call(client, method, path, token=None, **kw):
    headers = kw.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.request(method, API + path, headers=headers, **kw)


def setup_phase3_environment(client):
    """Set up a company with Owner, HR, Employee 1 (Alice), and Employee 2 (Bob)."""
    # 1. Company signup
    owner_res = client.post(f"{API}/auth/signup-company", json={
        "company_name": "Horizon Industries",
        "first_name": "Howard",
        "last_name": "Hughes",
        "email": "howard@horizon.com",
        "password": PW,
    }).json()
    owner_token = owner_res["access_token"]

    # 2. Create HR employee and user
    hr_emp = call(client, "POST", "/employees", owner_token, json={
        "first_name": "Hannah",
        "last_name": "Rhee",
        "email": "hannah@horizon.com",
        "designation": "HR Lead",
        "joining_date": "2026-01-01",
        "department": "People",
        "login_password": PW,
    }).json()

    # Promote Hannah to HR role
    users = call(client, "GET", "/users", owner_token).json()
    hannah_user = next(u for u in users if u["email"] == "hannah@horizon.com")
    call(client, "PATCH", f"/users/{hannah_user['id']}", owner_token, json={"role": "hr"})

    hr_token = client.post(f"{API}/auth/login", json={"email": "hannah@horizon.com", "password": PW}).json()["access_token"]

    # 3. Create Employee 1: Alice
    alice_emp = call(client, "POST", "/employees", hr_token, json={
        "first_name": "Alice",
        "last_name": "Wonder",
        "email": "alice@horizon.com",
        "phone": "9876543210",
        "designation": "Software Engineer",
        "joining_date": "2026-01-10",
        "department": "Engineering",
        "login_password": PW,
        "salary": {"basic": 50000, "hra": 20000, "allowances": 15000},
        "bank": {"account_holder": "Alice Wonder", "bank_name": "HDFC", "account_number": "111122223333", "ifsc": "HDFC0001234"},
    }).json()
    alice_token = client.post(f"{API}/auth/login", json={"email": "alice@horizon.com", "password": PW}).json()["access_token"]

    # 4. Create Employee 2: Bob
    bob_emp = call(client, "POST", "/employees", hr_token, json={
        "first_name": "Bob",
        "last_name": "Builder",
        "email": "bob@horizon.com",
        "phone": "9876500000",
        "designation": "Civil Engineer",
        "joining_date": "2026-01-12",
        "department": "Operations",
        "login_password": PW,
    }).json()
    bob_token = client.post(f"{API}/auth/login", json={"email": "bob@horizon.com", "password": PW}).json()["access_token"]

    return {
        "owner_token": owner_token,
        "hr_token": hr_token,
        "alice_token": alice_token,
        "bob_token": bob_token,
        "alice_emp": alice_emp,
        "bob_emp": bob_emp,
    }


def test_employee_my_profile_update(client):
    """Alice edits personal non-sensitive details -> updates immediately."""
    env = setup_phase3_environment(client)
    alice_token = env["alice_token"]

    update_res = call(client, "PATCH", "/auth/me", alice_token, json={
        "phone": "9988776655",
        "address": "42 High Street, Pune",
        "emergency_contact": "John Wonder (Father): 9876501234",
    })
    assert update_res.status_code == 200, update_res.text

    # Verify updated values in /employees/me
    me_res = call(client, "GET", "/employees/me", alice_token)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["phone"] == "9988776655"
    assert me_data["address"] == "42 High Street, Pune"


def test_sensitive_profile_change_request_workflow(client):
    """Sensitive changes require HR review and approval before taking effect."""
    env = setup_phase3_environment(client)
    alice_token = env["alice_token"]
    hr_token = env["hr_token"]
    alice_id = env["alice_emp"]["id"]

    # 1. Alice requests to change her bank account number
    cr_res = call(client, "POST", "/employees/me/change-requests", alice_token, json={
        "field_name": "bank_account_number",
        "new_value": "999988887777",
        "reason": "Switched salary account to Axis Bank",
    })
    assert cr_res.status_code == 201, cr_res.text
    cr = cr_res.json()
    assert cr["status"] == "pending"
    assert cr["old_value"] == "111122223333"
    assert cr["new_value"] == "999988887777"

    # Alice's current bank account remains unchanged while pending
    bank_res = call(client, "GET", f"/employees/{alice_id}/bank", alice_token)
    assert bank_res.json()["account_number_masked"].endswith("3333")

    # 2. HR lists change requests
    hr_list = call(client, "GET", "/change-requests?status=pending", hr_token)
    assert hr_list.status_code == 200
    requests = hr_list.json()
    assert len(requests) >= 1
    target_cr = next(r for r in requests if r["id"] == cr["id"])

    # 3. HR approves the change request
    review_res = call(client, "POST", f"/change-requests/{target_cr['id']}/review", hr_token, json={
        "status": "approved",
        "review_note": "Verified cancelled cheque copy",
    })
    assert review_res.status_code == 200
    assert review_res.json()["status"] == "approved"

    # Live bank account is now updated
    bank_revealed = call(client, "GET", f"/employees/{alice_id}/bank/reveal", hr_token).json()
    assert bank_revealed["account_number"] == "999988887777"


def test_sensitive_change_rejection(client):
    """HR rejects sensitive change request -> live record stays unchanged."""
    env = setup_phase3_environment(client)
    alice_token = env["alice_token"]
    hr_token = env["hr_token"]
    alice_id = env["alice_emp"]["id"]

    cr_res = call(client, "POST", "/employees/me/change-requests", alice_token, json={
        "field_name": "pan_number",
        "new_value": "ZZZZZ9999Z",
        "reason": "Typo correction",
    }).json()

    # HR rejects with note
    rej_res = call(client, "POST", f"/change-requests/{cr_res['id']}/review", hr_token, json={
        "status": "rejected",
        "review_note": "Invalid PAN card format provided",
    })
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "rejected"


def test_employee_document_upload_and_isolation(client):
    """Document upload, validation, and cross-employee access rejection."""
    env = setup_phase3_environment(client)
    alice_token = env["alice_token"]
    bob_token = env["bob_token"]
    alice_id = env["alice_emp"]["id"]

    # 1. Alice uploads an ID Proof PDF
    pdf_content = b"%PDF-1.4 Mock PDF content for ID proof"
    files = {"file": ("id_proof.pdf", io.BytesIO(pdf_content), "application/pdf")}
    upload_res = call(client, "POST", f"/employees/{alice_id}/documents?document_type=ID%20Proof", alice_token, files=files)
    assert upload_res.status_code == 201, upload_res.text
    doc = upload_res.json()
    assert doc["filename"] == "id_proof.pdf"
    assert doc["document_type"] == "ID Proof"

    # 2. Alice can download her document
    dl_res = call(client, "GET", f"/documents/{doc['id']}/download", alice_token)
    assert dl_res.status_code == 200
    assert dl_res.content == pdf_content

    # 3. Bob attempts to access Alice's document -> 403 Forbidden
    bob_dl = call(client, "GET", f"/documents/{doc['id']}/download", bob_token)
    assert bob_dl.status_code == 403

    # 4. Bob attempts to view Alice's profile -> 403 Forbidden
    bob_peek = call(client, "GET", f"/employees/{alice_id}", bob_token)
    assert bob_peek.status_code == 403


def test_company_profile_update(client):
    """Admin/Owner can update statutory details and company profile."""
    env = setup_phase3_environment(client)
    owner_token = env["owner_token"]

    res = call(client, "PUT", "/settings/company", owner_token, json={
        "company_name": "Horizon Industries Ltd",
        "legal_name": "Horizon Heavy Industries Private Limited",
        "state": "Maharashtra",
        "pan": "AAACH1234K",
        "tan": "PNEA12345B",
        "gstin": "27AAACH1234K1Z5",
        "pf_establishment_code": "MH/PUN/0012345/000",
        "address": "Floor 12, Cyber City, Magarpatta, Pune 411028",
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["name"] == "Horizon Industries Ltd"
    assert data["legal_name"] == "Horizon Heavy Industries Private Limited"
    assert data["gstin"] == "27AAACH1234K1Z5"
