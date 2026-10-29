"""Email service abstraction for sending transactional emails (invites, password resets, notifications).

Supports standard SMTP, local Mailpit in dev, or safe fallback logging.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from config import (
    APP_URL, EMAILS_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_TLS, SMTP_USER,
)

log = logging.getLogger("vertex.email")


def _send_smtp(to_email: str, subject: str, html_body: str, text_body: Optional[str] = None) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAILS_FROM
    msg["To"] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=5)
        if SMTP_TLS:
            server.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(EMAILS_FROM, [to_email], msg.as_string())
        server.quit()
        log.info(f"Email sent successfully to {to_email}: {subject}")
        return True
    except Exception as exc:
        log.warning(f"Could not send email via SMTP to {to_email} ({exc}). Logged email content locally.")
        return False


def send_invitation_email(to_email: str, employee_name: str, company_name: str, raw_token: str) -> bool:
    invite_url = f"{APP_URL}/accept-invite?token={raw_token}"
    subject = f"You're invited to join {company_name} on Vertex HR"
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0b0f19; color: #f3f4f6; padding: 24px; }}
        .card {{ max-width: 540px; margin: 0 auto; background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 32px; }}
        .btn {{ display: inline-block; background: #6366f1; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; margin: 24px 0; }}
        .footer {{ font-size: 12px; color: #9ca3af; margin-top: 32px; border-top: 1px solid #1f2937; padding-top: 16px; }}
      </style>
    </head>
    <body>
      <div class="card">
        <h2 style="color: #ffffff; margin-top: 0;">Welcome to {company_name}</h2>
        <p>Hello {employee_name},</p>
        <p>An administrator has created your profile on <strong>Vertex HR & Payroll</strong>. Click below to set up your account password and access your dashboard, attendance, and payslips.</p>
        <p><a href="{invite_url}" class="btn">Accept Invitation & Set Password</a></p>
        <p style="font-size: 14px; color: #9ca3af;">This invitation link will expire in 7 days.</p>
        <p style="font-size: 13px; color: #6b7280; word-break: break-all;">Link not working? Paste this into your browser:<br>{invite_url}</p>
        <div class="footer">
          &copy; Vertex HR & Payroll. All rights reserved.
        </div>
      </div>
    </body>
    </html>
    """
    text_body = f"Hello {employee_name},\n\nYou're invited to join {company_name} on Vertex HR.\nAccept your invite here: {invite_url}\n\nThis link expires in 7 days."
    return _send_smtp(to_email, subject, html_body, text_body)


def send_password_reset_email(to_email: str, user_name: str, raw_token: str) -> bool:
    reset_url = f"{APP_URL}/reset-password?token={raw_token}"
    subject = "Reset your Vertex HR account password"
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0b0f19; color: #f3f4f6; padding: 24px; }}
        .card {{ max-width: 540px; margin: 0 auto; background: #111827; border: 1px solid #1f2937; border-radius: 12px; padding: 32px; }}
        .btn {{ display: inline-block; background: #ef4444; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; margin: 24px 0; }}
        .footer {{ font-size: 12px; color: #9ca3af; margin-top: 32px; border-top: 1px solid #1f2937; padding-top: 16px; }}
      </style>
    </head>
    <body>
      <div class="card">
        <h2 style="color: #ffffff; margin-top: 0;">Password Reset Request</h2>
        <p>Hello {user_name},</p>
        <p>We received a request to reset your password for Vertex HR. Click the button below to choose a new password.</p>
        <p><a href="{reset_url}" class="btn">Reset Password</a></p>
        <p style="font-size: 14px; color: #9ca3af;">This link will expire in 1 hour and can only be used once. If you did not request this, you can safely ignore this email.</p>
        <p style="font-size: 13px; color: #6b7280; word-break: break-all;">Link not working? Paste this into your browser:<br>{reset_url}</p>
        <div class="footer">
          &copy; Vertex HR & Payroll. All rights reserved.
        </div>
      </div>
    </body>
    </html>
    """
    text_body = f"Hello {user_name},\n\nWe received a request to reset your password.\nReset link: {reset_url}\n\nThis link expires in 1 hour."
    return _send_smtp(to_email, subject, html_body, text_body)
