from fastapi.testclient import TestClient
from database import SessionLocal
from models import Notification, User


def test_notifications_and_omni_search(client: TestClient):
    # 1. Sign up new company owner
    signup_res = client.post("/api/v1/auth/signup-company", json={
        "company_name": "Notif Omni Corp",
        "first_name": "Nora",
        "last_name": "Search",
        "email": "nora@notifomni.com",
        "password": "Password123!",
    })
    assert signup_res.status_code == 201, signup_res.text
    token = signup_res.json()["access_token"]
    user_id = signup_res.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Verify notifications list
    notif_res = client.get("/api/v1/notifications", headers=headers)
    assert notif_res.status_code == 200
    assert isinstance(notif_res.json(), list)

    # 3. Create a test notification directly in DB
    with SessionLocal() as db:
        user = db.get(User, user_id)
        test_notif = Notification(
            company_id=user.company_id,
            user_id=user.id,
            title="Payroll Ready",
            message="Calculations complete for current month",
            type="payroll_ready",
            is_read=False,
        )
        db.add(test_notif)
        db.commit()
        notif_id = test_notif.id

    # 4. Fetch notifications and check unread
    notif_res = client.get("/api/v1/notifications", headers=headers)
    assert notif_res.status_code == 200
    items = notif_res.json()
    assert any(n["id"] == notif_id and not n["is_read"] for n in items)

    # 5. Mark as read
    read_res = client.post(f"/api/v1/notifications/{notif_id}/read", headers=headers)
    assert read_res.status_code == 200

    # 6. Mark all read
    read_all_res = client.post("/api/v1/notifications/read-all", headers=headers)
    assert read_all_res.status_code == 200

    # 7. Test ⌘K Omni-Search
    search_res = client.get("/api/v1/search?q=dash", headers=headers)
    assert search_res.status_code == 200
    results = search_res.json()
    assert any(r["category"] == "page" and "Dashboard" in r["title"] for r in results)

    # Search for employees
    search_emp_res = client.get("/api/v1/search?q=nora", headers=headers)
    assert search_emp_res.status_code == 200
