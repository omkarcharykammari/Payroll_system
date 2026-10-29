"""Vertex HR & Payroll API - application entry point.

Run (from the backend/ folder):
    uvicorn main:app --reload --port 8000
Interactive docs:  http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

import attendance, auth, employees, leave, loans_regularisation, notifications, payroll, payslips, reports, settings  # noqa: E401
from bootstrap import ensure_defaults
from config import API_PREFIX, AUTO_CREATE_TABLES, CORS_ORIGINS
from database import Base, SessionLocal, engine
import models  # noqa: F401  (registers every table on Base.metadata)

log = logging.getLogger("vertex")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if AUTO_CREATE_TABLES:
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            ensure_defaults(db)       # leave types, sample tax slabs, payroll config - only if missing
    yield


app = FastAPI(
    title="Vertex HR & Payroll API",
    version="1.0.0",
    description="Backend for the Vertex Next.js frontend. All routes except /health, /auth/login and "
                "/auth/register need `Authorization: Bearer <token>`.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        *CORS_ORIGINS,
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

for module in (auth, employees, attendance, leave, loans_regularisation, notifications, payroll, payslips, reports, settings):
    app.include_router(module.router, prefix=API_PREFIX)




# ------------------------------- error shapes -------------------------------- #
@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    """422 with a flat, UI-friendly list: {"detail": "...", "errors": [{"field", "message"}]}."""
    errors = []
    for err in exc.errors():
        loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
        message = err["msg"].removeprefix("Value error, ")
        errors.append({"field": ".".join(loc) or "request", "message": message})
    first = errors[0] if errors else {"field": "request", "message": "Invalid request"}
    return JSONResponse(status_code=422, content={
        "detail": f"{first['field']}: {first['message']}", "errors": errors})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server"})


@app.get("/health", tags=["System"])
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "up"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "down"})