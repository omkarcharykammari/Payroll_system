from decimal import Decimal
from fastapi.testclient import TestClient
from database import SessionLocal
from models import Employee, User


def test_loans_and_attendance_regularisation(client: TestClient):
    # 1. Sign up new company owner
    signup_res = client.post("/api/v1/auth/signup-company", json={
        "company_name": "Loan Reg Corp",
        "first_name": "Leonard",
        "last_name": "Admin",
        "email": "leonard@loanreg.com",
        "password": "Password123!",
    })
    assert signup_res.status_code == 201, signup_res.text
    token = signup_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create an employee
    emp_res = client.post("/api/v1/employees", json={
        "emp_code": "LR-001",
        "first_name": "Dave",
        "last_name": "Miller",
        "email": "dave@loanreg.com",
        "designation": "Engineer",
        "annual_ctc": 1200000,
        "joining_date": "2026-01-01",
    }, headers=headers)

    assert emp_res.status_code == 201, emp_res.text
    emp_id = emp_res.json()["id"]

    # 3. Create a loan / salary advance for the employee
    loan_res = client.post("/api/v1/loans", json={
        "employee_id": emp_id,
        "loan_type": "Salary Advance",
        "principal_amount": 50000.0,
        "monthly_installment": 10000.0,
    }, headers=headers)
    assert loan_res.status_code == 201, loan_res.text
    loan_data = loan_res.json()
    assert loan_data["principal_amount"] == 50000.0
    assert loan_data["remaining_balance"] == 50000.0

    # 4. List loans
    list_res = client.get("/api/v1/loans", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 5. Full and Final Settlement estimate
    fnf_res = client.get(f"/api/v1/employees/{emp_id}/full-and-final", headers=headers)
    assert fnf_res.status_code == 200
    fnf_data = fnf_res.json()
    assert fnf_data["pending_loan_recovery"] == 50000.0
    assert "estimated_net_payable" in fnf_data
