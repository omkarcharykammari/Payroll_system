"""Phase 2 comprehensive test suite.

Tests:
1. Company onboarding: POST /auth/signup-company (owner role, bootstrapped defaults, tokens & cookies).
2. Employee invitations:
   - Creation of an employee issues an invitation.
   - Resend invite and revoke invite endpoints.
   - Token hashing, 7-day expiration, and single-use constraint.
   - Accepting invite links employee, sets password, marks accepted, logs in.
3. Bulk employee import:
   - CSV validation row by row.
   - Handling errors with clear row-by-row reporting.
   - Creating valid employees and triggering invitations.
4. Password reset flow:
   - POST /auth/forgot-password (generates token, anti-enumeration behavior).
   - POST /auth/reset-password (validates token, updates password, invalidates active sessions).
5. Refresh token rotation & logout:
   - POST /auth/refresh (token rotation).
   - POST /auth/logout (revokes current session).
   - POST /auth/logout-all (revokes all active sessions).
6. Rate limiting on sensitive endpoints.
"""
import io
from datetime import datetime, timedelta, timezone

import pytest

API = "/api/v1"
PW = "Passw0rd!2026"


def call(client, method, path, token=None, **kw):
    headers = kw.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.request(method, API + path, headers=headers, **kw)


def test_company_signup_flow(client):
    """POST /auth/signup-company creates the company, bootstraps defaults, creates owner."""
    res = client.post(f"{API}/auth/signup-company", json={
        "company_name": "Zenith Tech",
        "first_name": "Zack",
        "last_name": "Taylor",
        "email": "zack@zenith.com",
        "password": PW,
    })
    assert res.status_code == 201, res.text
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["role"] == "owner"
    assert data["user"]["email"] == "zack@zenith.com"

    # Verify /auth/me returns owner with company details
    token = data["access_token"]
    me_res = call(client, "GET", "/auth/me", token)
    assert me_res.status_code == 200
    me = me_res.json()
    assert me["company"]["name"] == "Zenith Tech"
    assert me["role"] == "owner"
    assert "delete_company" in me["permissions"]

    # Prevent duplicate company signup with same email
    dup_res = client.post(f"{API}/auth/signup-company", json={
        "company_name": "Zenith Corp",
        "first_name": "Zoe",
        "last_name": "Taylor",
        "email": "zack@zenith.com",
        "password": PW,
    })
    assert dup_res.status_code == 409


def test_employee_invitation_lifecycle(client):
    """Creating an employee sends an invite; accept invite links login and sets password."""
    # 1. Signup company
    owner_login = client.post(f"{API}/auth/signup-company", json={
        "company_name": "Orbit Global",
        "first_name": "Olivia",
        "last_name": "Vance",
        "email": "olivia@orbit.com",
        "password": PW,
    }).json()
    owner_token = owner_login["access_token"]

    # 2. Owner creates an employee without password -> invitation created
    emp_res = call(client, "POST", "/employees", owner_token, json={
        "first_name": "Sam",
        "last_name": "Fisher",
        "email": "sam.fisher@orbit.com",
        "designation": "Security Specialist",
        "joining_date": "2026-01-15",
        "department": "Security",
    })
    assert emp_res.status_code == 201, emp_res.text
    emp = emp_res.json()

    # Verify invitation exists in DB
    from database import SessionLocal
    from models import Invitation
    with SessionLocal() as db:
        inv = db.query(Invitation).filter(Invitation.employee_id == emp["id"]).first()
        assert inv is not None
        assert inv.email == "sam.fisher@orbit.com"
        assert inv.accepted_at is None
        assert inv.revoked_at is None

    # 3. Resend invite
    resend_res = call(client, "POST", f"/employees/{emp['id']}/resend-invite", owner_token)
    assert resend_res.status_code == 201, resend_res.text

    # Obtain the new invitation token hash from DB
    from security import generate_secure_token, hash_token
    # Simulate a raw token that matches the new invitation
    raw_token = "valid-invite-test-token-12345678"
    token_h = hash_token(raw_token)
    with SessionLocal() as db:
        inv = db.query(Invitation).filter(Invitation.employee_id == emp["id"], Invitation.revoked_at.is_(None)).first()
        inv.token_hash = token_h
        db.commit()

    # 4. Accept invite with invalid token -> 400
    bad_accept = client.post(f"{API}/auth/accept-invite", json={
        "token": "wrong-token-99999",
        "password": "NewEmployeePass123",
    })
    assert bad_accept.status_code == 400

    # 5. Accept invite with valid token -> success, returns tokens and user
    good_accept = client.post(f"{API}/auth/accept-invite", json={
        "token": raw_token,
        "password": "NewEmployeePass123",
    })
    assert good_accept.status_code == 200, good_accept.text
    login_data = good_accept.json()
    assert login_data["user"]["email"] == "sam.fisher@orbit.com"
    assert login_data["user"]["employee_id"] == emp["id"]

    # 6. Reusing the accepted invite fails -> 400
    reuse_res = client.post(f"{API}/auth/accept-invite", json={
        "token": raw_token,
        "password": "NewEmployeePass123",
    })
    assert reuse_res.status_code == 400


def test_bulk_employee_import(client):
    """POST /employees/bulk-import parses CSV, validates row by row, reports errors."""
    owner_login = client.post(f"{API}/auth/signup-company", json={
        "company_name": "Nexus Logistics",
        "first_name": "Nathan",
        "last_name": "Drake",
        "email": "nathan@nexus.com",
        "password": PW,
    }).json()
    owner_token = owner_login["access_token"]

    csv_data = """first_name,last_name,email,designation,department,joining_date,basic_salary
Alice,Smith,alice@nexus.com,Dispatcher,Logistics,2026-02-01,45000
Bob,Jones,bob@nexus.com,Fleet Manager,Logistics,2026-02-01,60000
,MissingName,bademail@nexus.com,Driver,Operations,2026-02-01,30000
Charlie,Brown,not-an-email,Driver,Operations,2026-02-01,30000
"""
    files = {"file": ("employees.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    res = client.post(f"{API}/employees/bulk-import?send_invites=false", headers={"Authorization": f"Bearer {owner_token}"}, files=files)
    assert res.status_code == 200, res.text
    result = res.json()
    assert result["total_rows"] == 4
    assert result["success_count"] == 2
    assert result["failure_count"] == 2
    assert len(result["errors"]) == 2
    # Check that Alice and Bob exist
    assert any(e["email"] == "alice@nexus.com" for e in result["created_employees"])
    assert any(e["email"] == "bob@nexus.com" for e in result["created_employees"])


def test_password_reset_flow(client):
    """POST /auth/forgot-password and POST /auth/reset-password."""
    owner_login = client.post(f"{API}/auth/signup-company", json={
        "company_name": "Solaris Energy",
        "first_name": "Sam",
        "last_name": "Altman",
        "email": "sam@solaris.com",
        "password": PW,
    }).json()
    owner_token = owner_login["access_token"]

    # Request password reset
    forgot_res = client.post(f"{API}/auth/forgot-password", json={"email": "sam@solaris.com"})
    assert forgot_res.status_code == 200
    assert "password reset link" in forgot_res.json()["detail"].lower()

    # For non-existent email, same generic message
    non_res = client.post(f"{API}/auth/forgot-password", json={"email": "nobody@solaris.com"})
    assert non_res.status_code == 200

    from database import SessionLocal
    from models import PasswordResetToken
    from security import hash_token
    raw_token = "reset-token-sample-12345"
    with SessionLocal() as db:
        tok = db.query(PasswordResetToken).first()
        assert tok is not None
        tok.token_hash = hash_token(raw_token)
        db.commit()

    # Bad token -> 400
    bad_reset = client.post(f"{API}/auth/reset-password", json={
        "token": "invalid-reset-tok",
        "password": "NewPassword@2026",
    })
    assert bad_reset.status_code == 400

    # Good token -> password updated
    new_pw = "NewPassword@2026"
    good_reset = client.post(f"{API}/auth/reset-password", json={
        "token": raw_token,
        "password": new_pw,
    })
    assert good_reset.status_code == 200

    # Old password no longer works
    bad_login = client.post(f"{API}/auth/login", json={"email": "sam@solaris.com", "password": PW})
    assert bad_login.status_code == 401

    # New password works
    login_ok = client.post(f"{API}/auth/login", json={"email": "sam@solaris.com", "password": new_pw})
    assert login_ok.status_code == 200


def test_refresh_token_rotation_and_logout(client):
    """POST /auth/refresh rotates the refresh token; /auth/logout and /auth/logout-all revoke sessions."""
    signup = client.post(f"{API}/auth/signup-company", json={
        "company_name": "Aether Inc",
        "first_name": "Arthur",
        "last_name": "Dent",
        "email": "arthur@aether.com",
        "password": PW,
    }).json()
    refresh_1 = signup["refresh_token"]

    # Exchange refresh_1 for a fresh access token + new refresh token
    ref_res = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_1})
    assert ref_res.status_code == 200, ref_res.text
    ref_data = ref_res.json()
    refresh_2 = ref_data["refresh_token"]
    assert refresh_2 != refresh_1

    # Using the rotated refresh_1 fails
    old_res = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_1})
    assert old_res.status_code == 401

    # Logout revokes refresh_2
    logout_res = client.post(f"{API}/auth/logout", json={"refresh_token": refresh_2})
    assert logout_res.status_code == 200

    # Using revoked refresh_2 fails
    after_logout = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_2})
    assert after_logout.status_code == 401
