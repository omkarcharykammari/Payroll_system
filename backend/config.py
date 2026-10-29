"""All configuration comes from environment variables (see .env.example)."""
import os

from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)
load_dotenv()


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/vertex"
)
if DATABASE_URL.startswith("sqlite:///./"):
    db_rel = DATABASE_URL[len("sqlite:///./"):]
    db_abs = (Path(__file__).resolve().parent / db_rel).resolve().as_posix()
    DATABASE_URL = f"sqlite:///{db_abs}"

JWT_SECRET = os.getenv("JWT_SECRET", "")
if len(JWT_SECRET) < 16:
    raise RuntimeError(
        "JWT_SECRET is missing or too short (min 16 chars). "
        "Copy .env.example to .env and set a long random value."
    )
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
]
API_PREFIX = os.getenv("API_PREFIX", "/api/v1")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Vertex Enterprise")
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Kolkata")

# First registered user becomes admin; later self-registered users get the
# "employee" role with NO access to anyone's data until an admin links them.
ALLOW_PUBLIC_REGISTRATION = _flag("ALLOW_PUBLIC_REGISTRATION", True)
AUTO_CREATE_TABLES = _flag("AUTO_CREATE_TABLES", True)

# Refresh tokens & Session Security
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
COOKIE_SECURE = _flag("COOKIE_SECURE", False)  # set True in prod (HTTPS)
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")  # "lax", "strict", "none"
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", None)

# Email & SMTP Settings
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))  # Default to Mailpit port 1025
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_TLS = _flag("SMTP_TLS", False)
EMAILS_FROM = os.getenv("EMAILS_FROM", "noreply@vertexhr.com")
APP_URL = os.getenv("APP_URL", "http://localhost:3000")