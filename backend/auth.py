"""Authentication (JWT + bcrypt), role checks and the /auth and /users routes.
Supports multi-tenancy: each user belongs to exactly one Company.
"""
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
import re

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import (
    ACCESS_TOKEN_EXPIRE_MINUTES, ALLOW_PUBLIC_REGISTRATION, COOKIE_DOMAIN,
    COOKIE_SAMESITE, COOKIE_SECURE, JWT_ALGORITHM, JWT_SECRET, REFRESH_TOKEN_EXPIRE_DAYS,
)
from database import get_db
from email_service import send_password_reset_email
from models import (
    ADMIN_ROLES, ROLE_ADMIN, ROLE_EMPLOYEE, ROLE_HR, ROLE_OWNER, STAFF_ROLES,
    Company, Employee, Invitation, PasswordResetToken, RefreshToken, User, utcnow,
)
from schemas import (
    CompanyOut, CompanySignupIn, ForgotPasswordIn, InviteAcceptIn, LoginIn, MeOut,
    Message, PasswordChange, ProfileUpdate, RefreshTokenIn, RegisterIn,
    ResetPasswordIn, TokenOut, UserAdminUpdate, UserOut,
)
from security import (
    enforce_rate_limit, generate_secure_token, get_client_ip, hash_token,
    invite_limiter, login_limiter,
)
from tenancy import calculate_permissions, get_tenant_company
from utils import log_audit

router = APIRouter(tags=["Auth"])
bearer_scheme = HTTPBearer(auto_error=False)  # we raise our own 401 (FastAPI's default is 403)

# ------------------------------- passwords -------------------------------- #
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password-1", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    raw = password.encode()
    if len(raw) > 72:          # bcrypt limit; passwords are capped at 72 bytes when set
        return False
    try:
        return bcrypt.checkpw(raw, hashed.encode())
    except ValueError:
        return False


# ---------------------------------- JWT ----------------------------------- #
def create_access_token(user: User) -> tuple[str, int]:
    expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": str(user.id), "iat": now, "exp": now + expires},
        JWT_SECRET, algorithm=JWT_ALGORITHM,
    )
    return token, int(expires.total_seconds())


def create_refresh_token(user: User, db: Session, request: Optional[Request] = None) -> tuple[str, RefreshToken]:
    raw_token = generate_secure_token()
    token_h = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    user_agent = request.headers.get("user-agent") if request else None
    client_ip = get_client_ip(request) if request else None

    db_token = RefreshToken(
        user_id=user.id,
        token_hash=token_h,
        expires_at=expires_at,
        user_agent=user_agent[:255] if user_agent else None,
        ip_address=client_ip,
    )
    db.add(db_token)
    db.commit()
    return raw_token, db_token


def _set_auth_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    max_age = REFRESH_TOKEN_EXPIRE_DAYS * 86400
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=max_age,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path="/api/v1/auth",
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=max_age,
        httponly=False,  # readable by client JS to send in X-CSRF-Token header
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="refresh_token", domain=COOKIE_DOMAIN, path="/api/v1/auth")
    response.delete_cookie(key="csrf_token", domain=COOKIE_DOMAIN, path="/")


def _unauthorized(msg: str = "Not authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token_str = None
    if creds:
        token_str = creds.credentials
    else:
        # Fallback to cookie if present
        token_str = request.cookies.get("access_token")

    if not token_str:
        raise _unauthorized()
    try:
        payload = jwt.decode(token_str, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthorized("Invalid or expired token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Account not found or disabled")
    return user


def get_current_company(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Company:
    return get_tenant_company(user, db)


def require_roles(*roles: str) -> Callable:
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do this")
        return user
    return checker


require_staff = require_roles(*STAFF_ROLES)   # owner, admin, or hr
require_admin = require_roles(*ADMIN_ROLES)   # owner or admin
require_owner = require_roles(ROLE_OWNER)


def is_staff(user: User) -> bool:
    return user.role in STAFF_ROLES


def assert_self_or_staff(user: User, employee_id: int) -> None:
    if not is_staff(user) and user.employee_id != employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only access your own records")


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", text)


# --------------------------------- routes --------------------------------- #
@router.post("/auth/signup-company", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def signup_company(
    body: CompanySignupIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Phase 2: Company onboarding. Creates the company, bootstraps defaults,
    and creates the owner account, logging them in immediately.
    """
    enforce_rate_limit(request, invite_limiter, prefix="signup_company")

    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    company_name = body.company_name.strip()
    base_slug = slugify(company_name) or "company"
    slug = base_slug
    count = 1
    while db.scalar(select(Company.id).where(Company.slug == slug)):
        slug = f"{base_slug}-{count}"
        count += 1

    company = Company(
        name=company_name,
        slug=slug,
        legal_name=f"{company_name} Pvt Ltd",
        status="active",
    )
    db.add(company)
    db.flush()

    # Bootstrap default settings, tax slabs, and leave types for this company
    from bootstrap import ensure_defaults
    ensure_defaults(db, company_id=company.id)

    owner = User(
        company_id=company.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        role=ROLE_OWNER,
        email_verified=True,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    access_token, expires_in = create_access_token(owner)
    raw_refresh, _ = create_refresh_token(owner, db, request)
    csrf_token = generate_secure_token()
    _set_auth_cookies(response, raw_refresh, csrf_token)

    log_audit(db, owner, "company.signup", "company", company.id, {"company_name": company_name})

    return TokenOut(
        access_token=access_token,
        expires_in=expires_in,
        user=UserOut.model_validate(owner),
        refresh_token=raw_refresh,
        csrf_token=csrf_token,
    )


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Registration endpoint for standalone account creation or first admin."""
    existing_users = db.scalar(select(func.count(User.id))) or 0
    if existing_users and not ALLOW_PUBLIC_REGISTRATION:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Public registration is disabled")
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    company_name = (body.company_name or "Vertex Enterprise").strip()
    company = db.scalar(select(Company).where(func.lower(Company.name) == company_name.lower()))
    if not company:
        base_slug = slugify(company_name) or "company"
        slug = base_slug
        count = 1
        while db.scalar(select(Company.id).where(Company.slug == slug)):
            slug = f"{base_slug}-{count}"
            count += 1
        company = Company(
            name=company_name,
            slug=slug,
            legal_name=f"{company_name} Pvt Ltd",
            status="active",
        )
        db.add(company)
        db.flush()
        from bootstrap import ensure_defaults
        ensure_defaults(db, company_id=company.id)

    users_in_company = db.scalar(select(func.count(User.id)).where(User.company_id == company.id)) or 0
    role = ROLE_ADMIN if users_in_company == 0 else ROLE_EMPLOYEE
    user = User(
        company_id=company.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        role=role,
    )
    db.add(user)
    db.commit()
    return user


@router.post("/auth/login", response_model=TokenOut)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    enforce_rate_limit(request, login_limiter, prefix="login")

    user = db.scalar(select(User).where(User.email == body.email))
    ok = verify_password(body.password, user.hashed_password if user else _DUMMY_HASH)
    if not user or not ok:
        raise _unauthorized("Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled")

    access_token, expires_in = create_access_token(user)
    raw_refresh, _ = create_refresh_token(user, db, request)
    csrf_token = generate_secure_token()
    _set_auth_cookies(response, raw_refresh, csrf_token)

    return TokenOut(
        access_token=access_token,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
        refresh_token=raw_refresh,
        csrf_token=csrf_token,
    )


@router.post("/auth/refresh", response_model=TokenOut)
def refresh_session(
    request: Request,
    response: Response,
    body: Optional[RefreshTokenIn] = None,
    db: Session = Depends(get_db),
):
    """Exchange a valid refresh token for a fresh access token + rotated refresh token."""
    raw_refresh = None
    if body and body.refresh_token:
        raw_refresh = body.refresh_token
    else:
        raw_refresh = request.cookies.get("refresh_token")

    if not raw_refresh:
        raise _unauthorized("Missing refresh token")

    token_h = hash_token(raw_refresh)
    now = datetime.now(timezone.utc)

    db_token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_h))
    if not db_token or db_token.revoked_at is not None or db_token.expires_at.replace(tzinfo=timezone.utc) < now:
        _clear_auth_cookies(response)
        raise _unauthorized("Invalid or expired refresh token")

    user = db.get(User, db_token.user_id)
    if not user or not user.is_active:
        _clear_auth_cookies(response)
        raise _unauthorized("User account disabled or not found")

    # Rotate refresh token: revoke current, issue new
    new_raw_refresh = generate_secure_token()
    new_token_h = hash_token(new_raw_refresh)
    db_token.revoked_at = now
    db_token.replaced_by = new_token_h

    expires_at = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    new_db_token = RefreshToken(
        user_id=user.id,
        token_hash=new_token_h,
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent", "")[:255],
        ip_address=get_client_ip(request),
    )
    db.add(new_db_token)
    db.commit()

    access_token, expires_in = create_access_token(user)
    csrf_token = generate_secure_token()
    _set_auth_cookies(response, new_raw_refresh, csrf_token)

    return TokenOut(
        access_token=access_token,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
        refresh_token=new_raw_refresh,
        csrf_token=csrf_token,
    )


@router.post("/auth/logout", response_model=Message)
def logout(
    request: Request,
    response: Response,
    body: Optional[RefreshTokenIn] = None,
    db: Session = Depends(get_db),
):
    raw_refresh = (body.refresh_token if body and body.refresh_token else None) or request.cookies.get("refresh_token")
    if raw_refresh:
        token_h = hash_token(raw_refresh)
        db_token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_h))
        if db_token and db_token.revoked_at is None:
            db_token.revoked_at = datetime.now(timezone.utc)
            db.commit()

    _clear_auth_cookies(response)
    return Message(detail="Logged out successfully")


@router.post("/auth/logout-all", response_model=Message)
def logout_all(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke all active refresh tokens for the current user."""
    now = datetime.now(timezone.utc)
    active_tokens = db.scalars(
        select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
    ).all()
    for t in active_tokens:
        t.revoked_at = now
    db.commit()
    _clear_auth_cookies(response)
    return Message(detail="Logged out of all sessions")


@router.post("/auth/accept-invite", response_model=TokenOut)
def accept_invite(
    body: InviteAcceptIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Accept an employee invitation, set password, link employee, and log in."""
    enforce_rate_limit(request, invite_limiter, prefix="accept_invite")

    token_h = hash_token(body.token)
    now = datetime.now(timezone.utc)

    inv = db.scalar(select(Invitation).where(Invitation.token_hash == token_h))
    if not inv or inv.revoked_at is not None or inv.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired invitation link")
    if inv.accepted_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invitation has already been used")

    emp = db.get(Employee, inv.employee_id)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee record not found")

    user = db.scalar(select(User).where(User.email == inv.email))
    if user:
        # Existing user account, link and update password
        user.hashed_password = hash_password(body.password)
        user.company_id = inv.company_id
        user.employee_id = emp.id
        user.role = inv.role
        user.email_verified = True
    else:
        user = User(
            company_id=inv.company_id,
            email=inv.email,
            hashed_password=hash_password(body.password),
            first_name=emp.first_name,
            last_name=emp.last_name,
            job_title=emp.designation,
            role=inv.role,
            employee_id=emp.id,
            email_verified=True,
        )
        db.add(user)

    inv.accepted_at = now
    db.commit()
    db.refresh(user)

    access_token, expires_in = create_access_token(user)
    raw_refresh, _ = create_refresh_token(user, db, request)
    csrf_token = generate_secure_token()
    _set_auth_cookies(response, raw_refresh, csrf_token)

    log_audit(db, user, "invite.accept", "employee", emp.id)

    return TokenOut(
        access_token=access_token,
        expires_in=expires_in,
        user=UserOut.model_validate(user),
        refresh_token=raw_refresh,
        csrf_token=csrf_token,
    )


@router.post("/auth/forgot-password", response_model=Message)
def forgot_password(
    body: ForgotPasswordIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Generate a password reset token and email it to the user.
    Always returns success to prevent user email enumeration.
    """
    enforce_rate_limit(request, login_limiter, prefix="forgot_password")

    user = db.scalar(select(User).where(User.email == body.email))
    if user and user.is_active:
        raw_token = generate_secure_token()
        token_h = hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        db_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_h,
            expires_at=expires_at,
        )
        db.add(db_token)
        db.commit()

        send_password_reset_email(user.email, user.full_name, raw_token)

    return Message(detail="If an account exists with this email, a password reset link has been sent.")


@router.post("/auth/reset-password", response_model=Message)
def reset_password(
    body: ResetPasswordIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Verify password reset token, update password, and invalidate existing sessions."""
    enforce_rate_limit(request, login_limiter, prefix="reset_password")

    token_h = hash_token(body.token)
    now = datetime.now(timezone.utc)

    db_token = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_h))
    if not db_token or db_token.used_at is not None or db_token.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired password reset link")

    user = db.get(User, db_token.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User account not found or disabled")

    user.hashed_password = hash_password(body.password)
    db_token.used_at = now

    # Invalidate all active refresh tokens on password reset
    for t in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))):
        t.revoked_at = now

    log_audit(db, user, "password.reset", "user", user.id)
    db.commit()
    return Message(detail="Password has been reset successfully. You may now log in.")


@router.get("/auth/me", response_model=MeOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_out = None
    if user.company_id:
        c = db.get(Company, user.company_id)
        if c:
            company_out = CompanyOut.model_validate(c)
    
    emp_dict = None
    if user.employee_id:
        emp = db.get(Employee, user.employee_id)
        if emp:
            emp_dict = {
                "id": emp.id,
                "emp_code": emp.emp_code,
                "first_name": emp.first_name,
                "last_name": emp.last_name,
                "name": emp.full_name,
                "designation": emp.designation,
                "department": emp.department.name if emp.department else None,
                "joining_date": str(emp.joining_date),
            }

    return MeOut(
        user=UserOut.model_validate(user),
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        role=user.role,
        permissions=calculate_permissions(user.role),
        company=company_out,
        employee=emp_dict,
    )


@router.patch("/auth/me", response_model=UserOut)
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    user_fields = {"first_name", "last_name"}
    for f in user_fields:
        if f in data:
            setattr(user, f, data[f].strip() if isinstance(data[f], str) else data[f])

    if user.employee_id:
        emp = db.get(Employee, user.employee_id)
        if emp:
            for f in ("first_name", "last_name", "phone", "address", "date_of_birth", "gender", "emergency_contact", "notification_preferences"):
                if f in data:
                    val = data[f].strip() if isinstance(data[f], str) else data[f]
                    setattr(emp, f, val)

    db.commit()
    return user


@router.post("/auth/change-password", response_model=Message)
def change_password(body: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be different")
    user.hashed_password = hash_password(body.new_password)
    log_audit(db, user, "password.change", "user", user.id)
    db.commit()
    return Message(detail="Password updated")


# ------------------------ user administration (admin) --------------------- #
@router.get("/users", response_model=list[UserOut])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.id)
    if admin.company_id:
        stmt = stmt.where(User.company_id == admin.company_id)
    return db.scalars(stmt).all()


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserAdminUpdate, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or (admin.company_id and user.company_id != admin.company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    data = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (data.get("role", admin.role) not in ADMIN_ROLES or data.get("is_active") is False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot demote or disable your own account")
    if data.get("employee_id") is not None:
        emp = db.get(Employee, data["employee_id"])
        if not emp or (admin.company_id and emp.company_id != admin.company_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
        taken = db.scalar(select(User.id).where(User.employee_id == data["employee_id"], User.id != user.id))
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, "That employee is already linked to another login")
    changes = {}
    for field, value in data.items():
        if getattr(user, field) != value:
            changes[field] = [getattr(user, field), value]
            setattr(user, field, value)
    if changes:
        log_audit(db, admin, "user.update", "user", user.id, {"changes": changes})
    db.commit()
    return user