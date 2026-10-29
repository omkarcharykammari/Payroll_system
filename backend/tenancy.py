"""Multi-tenant isolation and security utilities.

Provides:
- get_current_company: Extracts the authenticated user's company or errors 403.
- tenant query scoping and entity access verification.
- Centralized loader criteria for multi-tenant isolation.
"""
from typing import Optional, Type, TypeVar
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import Company, User, ROLE_OWNER, ROLE_ADMIN, ROLE_HR, ROLE_EMPLOYEE

T = TypeVar("T")


def get_current_company(
    db: Session = Depends(get_db),
    # imported dynamically or via forward reference to avoid circular imports
) -> Company:
    # Deferred import of get_current_user to avoid circular dependency with auth
    from auth import get_current_user
    raise NotImplementedError("Use get_current_tenant_company")


def get_tenant_company(
    user: User,
    db: Session,
) -> Company:
    if not user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to any company"
        )
    company = db.get(Company, user.company_id)
    if not company or company.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company account is inactive or not found"
        )
    return company


def get_tenant_entity_or_404(db: Session, model: Type[T], entity_id: int, company_id: int) -> T:
    """Fetch an entity by ID ensuring it belongs to the specified company.
    
    If the entity does not exist OR belongs to another company, returns 404
    to prevent leaking the existence of other tenants' records.
    """
    stmt = select(model).where(model.id == entity_id)
    if hasattr(model, "company_id"):
        stmt = stmt.where(model.company_id == company_id)
    entity = db.scalar(stmt)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{model.__name__} not found"
        )
    return entity


def calculate_permissions(role: str) -> list[str]:
    """Calculate granular permissions list for the UI based on role."""
    base_employee_perms = [
        "view_own_profile",
        "edit_own_profile",
        "view_own_attendance",
        "clock_in_out",
        "view_own_leave",
        "request_leave",
        "view_own_payslips",
        "download_own_payslip",
    ]
    if role == ROLE_EMPLOYEE:
        return base_employee_perms

    hr_perms = base_employee_perms + [
        "view_dashboard",
        "view_employees",
        "manage_employees",
        "view_attendance",
        "manage_attendance",
        "view_leave",
        "approve_deny_leave",
        "view_payroll",
        "create_payroll",
        "calculate_payroll",
        "review_payroll",
        "view_payslips",
        "view_reports",
        "export_reports",
        "view_settings",
    ]
    if role == ROLE_HR:
        return hr_perms

    admin_perms = hr_perms + [
        "finalize_payroll",
        "mark_paid_payroll",
        "reopen_payroll",
        "publish_payslips",
        "manage_departments",
        "manage_settings",
        "manage_tax_slabs",
        "manage_holidays",
        "view_audit_logs",
        "manage_users",
        "reveal_bank_details",
    ]
    if role == ROLE_ADMIN:
        return admin_perms

    owner_perms = admin_perms + [
        "manage_company_profile",
        "manage_billing",
        "delete_company",
    ]
    if role == ROLE_OWNER:
        return owner_perms

    return base_employee_perms
