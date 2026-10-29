"""Test setup: an in-memory SQLite database, so tests never touch your PostgreSQL data."""
import os

# Must be set BEFORE the app modules are imported (they read config at import time).
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"
os.environ["APP_TIMEZONE"] = "Asia/Kolkata"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["ALLOW_PUBLIC_REGISTRATION"] = "true"
os.environ["TESTING"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import models  # noqa: E402,F401
from bootstrap import ensure_defaults  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402

assert engine.url.get_backend_name() == "sqlite", "Tests must never run against a real database"


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        ensure_defaults(db)
    with TestClient(app) as c:
        yield c