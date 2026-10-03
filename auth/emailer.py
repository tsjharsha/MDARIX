"""Every email MDARIX sends: one SMTP path, one branded layout, plain text and HTML in each message.

Messages are built from structured blocks (paragraphs, a button, a list, label/value details), so the text and HTML
versions always say the same thing, and every value that came from a person (names, titles, quotes) is escaped.
Each email names the company that sent it, its address, the support contact and why the recipient is getting it.

Delivery returns "SENT", or "NOT_CONFIGURED" when this server has no SMTP account (local development; production
refuses to start without one), and raises EmailDeliveryError, without credentials or protocol detail, when the
provider refuses or cannot be reached.
"""

from __future__ import annotations

import html
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr

from dotenv import load_dotenv

load_dotenv()

BRAND = "#087b78"
INK = "#10202f"
MUTED = "#4a5d6e"


class EmailDeliveryError(RuntimeError):
    """Controlled SMTP failure that never includes credentials or raw protocol data."""


def smtp_configuration_status() -> dict[str, object]:
    required = {
        "host": os.getenv("MDARIX_SMTP_HOST"),
        "username": os.getenv("MDARIX_SMTP_USERNAME"),
        "password": os.getenv("MDARIX_SMTP_PASSWORD"),
        "sender": os.getenv("MDARIX_SMTP_FROM"),
    }
    return {
        "configured": all(required.values()),
        "present": {name: bool(value) for name, value in required.items()},
        "port_present": bool(os.getenv("MDARIX_SMTP_PORT")),
        "app_url_present": bool(os.getenv("MDARIX_APP_URL")),
        "sender_domain_verified": bool(os.getenv("MDARIX_SMTP_VERIFIED_DOMAIN"))
        and parseaddr(required["sender"] or "")[1].endswith("@" + os.getenv("MDARIX_SMTP_VERIFIED_DOMAIN", "")),
    }


@dataclass(frozen=True)
class Company:
    name: str
    address: str
    support_email: str
    app_url: str


def company() -> Company:
    return Company(
        name=os.getenv("MDARIX_COMPANY_LEGAL_NAME", "").strip() or "MDARIX",
        address=os.getenv("MDARIX_COMPANY_ADDRESS", "").strip(),
        support_email=os.getenv("MDARIX_SUPPORT_EMAIL", "").strip(),
        app_url=(os.getenv("MDARIX_APP_URL", "").strip() or "http://127.0.0.1:5178").rstrip("/"),
    )


# ------------------------------------------------------------------------------------------- layout


@dataclass(frozen=True)
class Message:
    subject: str
    heading: str
    paragraphs: tuple[str, ...] = ()
    button: tuple[str, str] | None = None  # (label, url)
    details: tuple[tuple[str, str], ...] = ()  # (label, value)
    items: tuple[str, ...] = ()
    closing: tuple[str, ...] = ()
    reason: str = "You are receiving this email because of your MDARIX account."


def render(message: Message) -> tuple[str, str]:
    """(plain text, HTML) of one message. Every value is plain text and is escaped for the HTML version."""
    who = company()
    text_lines = [message.heading, ""]
    for paragraph in message.paragraphs:
        text_lines += [paragraph, ""]
    for label, value in message.details:
        text_lines.append(f"{label}: {value}")
    if message.details:
        text_lines.append("")
    for item in message.items:
        text_lines.append(f"  - {item}")
    if message.items:
        text_lines.append("")
    if message.button:
        text_lines += [f"{message.button[0]}: {message.button[1]}", ""]
    for paragraph in message.closing:
        text_lines += [paragraph, ""]
    footer = [message.reason]
    if who.support_email:
        footer.append(f"Questions: {who.support_email}")
    footer.append(" · ".join(part for part in (who.name, who.address) if part))
    text = "\n".join(text_lines + ["--", *footer]) + "\n"

    e = html.escape
    body = [f'<h1 style="margin:0 0 16px;font-size:22px;color:{INK}">{e(message.heading)}</h1>']
    body += [f'<p style="margin:0 0 14px;color:{INK};line-height:1.55">{e(p)}</p>' for p in message.paragraphs]
    if message.details:
        rows = "".join(
            f'<tr><td style="padding:4px 16px 4px 0;color:{MUTED};vertical-align:top">{e(label)}</td>'
            f'<td style="padding:4px 0;color:{INK}">{e(value)}</td></tr>'
            for label, value in message.details
        )
        body.append(f'<table role="presentation" style="margin:0 0 16px;border-collapse:collapse">{rows}</table>')
    if message.items:
        entries = "".join(f'<li style="margin:0 0 6px">{e(item)}</li>' for item in message.items)
        body.append(f'<ul style="margin:0 0 16px;padding-left:20px;color:{INK}">{entries}</ul>')
    if message.button:
        label, url = message.button
        body.append(
            f'<p style="margin:22px 0"><a href="{e(url, quote=True)}" style="background:{BRAND};color:#ffffff;'
            'text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:600;display:inline-block">'
            f"{e(label)}</a></p>"
            f'<p style="margin:0 0 14px;color:{MUTED};font-size:13px">If the button does not work, copy this '
            f'address into your browser:<br><span style="word-break:break-all">{e(url)}</span></p>'
        )
    body += [f'<p style="margin:0 0 14px;color:{INK};line-height:1.55">{e(p)}</p>' for p in message.closing]
    footer_html = "<br>".join(e(line) for line in footer)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{e(message.subject)}</title></head>"
        '<body style="margin:0;padding:24px;background:#f3f6fa;font-family:Segoe UI,Arial,sans-serif;font-size:15px">'
        '<table role="presentation" width="100%" style="max-width:600px;margin:0 auto;background:#ffffff;'
        'border:1px solid #dde5ec;border-radius:12px"><tr><td style="padding:28px 32px">'
        '<p style="margin:0 0 20px;font-weight:700;font-size:18px;color:#183249">MDARIX</p>'
        + "".join(body)
        + '<hr style="border:none;border-top:1px solid #dde5ec;margin:24px 0 14px">'
        f'<p style="margin:0;color:{MUTED};font-size:12px;line-height:1.5">{footer_html}</p>'
        "</td></tr></table></body></html>"
    )
    return text, page


def _send(recipient: str, message: Message, *, reply_to: str | None = None) -> str:
    text, page = render(message)
    return _send_email(recipient, message.subject, text, page, reply_to=reply_to)


def _send_email(
    recipient: str, subject: str, body: str, html_body: str | None = None, *, reply_to: str | None = None
) -> str:
    """Send one email through the configured SMTP provider; NOT_CONFIGURED when there is none."""
    host = os.getenv("MDARIX_SMTP_HOST")
    username = os.getenv("MDARIX_SMTP_USERNAME")
    password = os.getenv("MDARIX_SMTP_PASSWORD")
    sender = os.getenv("MDARIX_SMTP_FROM")
    if not all((host, username, password, sender)):
        return "NOT_CONFIGURED"
    sender_address = parseaddr(sender)[1]
    verified_domain = os.getenv("MDARIX_SMTP_VERIFIED_DOMAIN")
    if verified_domain and not sender_address.endswith("@" + verified_domain):
        raise EmailDeliveryError("The SMTP sender address is not on the verified domain")
    if any(ch in str(recipient) for ch in "\r\n") or "@" not in str(recipient):
        raise EmailDeliveryError("The recipient address is not valid")

    email = EmailMessage()
    email["Subject"] = subject.replace("\r", " ").replace("\n", " ")
    email["From"] = sender
    email["To"] = recipient
    support = reply_to or company().support_email
    if support:
        email["Reply-To"] = support
    email["Message-ID"] = make_msgid(domain=sender_address.split("@")[-1] or None)
    email["Auto-Submitted"] = "auto-generated"
    email.set_content(body)
    if html_body:
        email.add_alternative(html_body, subtype="html")
    port = int(os.getenv("MDARIX_SMTP_PORT", "587"))
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as client:
                client.login(username, password)
                client.send_message(email)
        else:
            with smtplib.SMTP(host, port, timeout=15) as client:
                client.starttls()
                client.login(username, password)
                client.send_message(email)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailDeliveryError(
            "The email provider refused the message or could not be reached. Check the SMTP settings and the "
            "sender's domain."
        ) from exc
    return "SENT"


# ------------------------------------------------------------------------------------------- accounts


def send_activation_email(recipient: str, token: str, organization: str, valid_for: str = "72 hours") -> str:
    url = f"{company().app_url}/activate-account?token={token}"
    return _send(
        recipient,
        Message(
            subject="Activate your MDARIX account",
            heading=f"You are invited to MDARIX for {organization}",
            paragraphs=(
                "MDARIX connects complaints, product versions, suppliers, lots and evidence so your team can "
                "investigate product signals in one place.",
                "Choose your password to activate your account. Only you will know it.",
            ),
            button=("Activate my account", url),
            closing=(
                f"This link works once and expires in {valid_for}. If it has expired, ask your administrator to send "
                "a new invitation.",
            ),
            reason=f"You are receiving this email because an administrator of {organization} invited you to MDARIX.",
        ),
    )


def send_trial_invitation(
    recipient: str, token: str, organization: str, *, ends_on: str, users: int, rows: int, valid_for: str = "72 hours"
) -> str:
    """The invitation to a free-trial workspace: what the trial includes and what happens when it ends."""
    url = f"{company().app_url}/activate-account?token={token}"
    return _send(
        recipient,
        Message(
            subject="Activate your MDARIX account",
            heading="Your MDARIX free trial is ready",
            paragraphs=(
                f"Your private workspace for {organization} is set up with a ready-made sample investigation, so you "
                "can see MDARIX at work before sharing any data.",
            ),
            details=(
                ("Trial ends", ends_on),
                ("Included", f"up to {users} users and {rows:,} uploaded rows"),
                ("Your data", "deleted 30 days after the trial ends, unless you continue"),
            ),
            items=(
                "Activate your account and choose a password.",
                "Open the guided investigation in Getting started.",
                "Try your own data with the CSV templates (no patient-identifiable data, please).",
            ),
            button=("Activate my account", url),
            closing=(f"This link works once and expires in {valid_for}.",),
            reason="You are receiving this email because you requested a free MDARIX trial.",
        ),
    )


def send_welcome_email(recipient: str, organization: str) -> str:
    return _send(
        recipient,
        Message(
            subject="Welcome to MDARIX",
            heading="Your account is active",
            paragraphs=(
                f"You can now sign in to MDARIX for {organization} with your email and the password you chose.",
                "Administrators must also set up an authenticator app at their first sign-in.",
            ),
            button=("Sign in", f"{company().app_url}/signin"),
            reason="You are receiving this email because you activated an MDARIX account.",
        ),
    )


def send_password_reset_email(recipient: str, token: str, organization: str | None = None) -> str:
    # A person with accounts in several organizations gets one link per organization, each naming it.
    where = f" for {organization}" if organization else ""
    return _send(
        recipient,
        Message(
            subject=f"Reset your MDARIX password{where}",
            heading=f"Reset your MDARIX password{where}",
            paragraphs=("Someone asked to reset the password of this account. If it was you, choose a new password:",),
            button=("Choose a new password", f"{company().app_url}/reset-password?token={token}"),
            closing=(
                "This link works once and expires in one hour. Your current password keeps working until you use it, "
                "and every other session is signed out when you do.",
                "If you did not ask for this, you can ignore this email.",
            ),
            reason="You are receiving this email because a password reset was requested for your MDARIX account.",
        ),
    )


# ------------------------------------------------------------------------------------------- trial lifecycle


def send_trial_reminder(recipient: str, organization: str, *, days_left: int, ends_on: str, delete_on: str) -> str:
    left = "today" if days_left <= 0 else ("tomorrow" if days_left == 1 else f"in {days_left} days")
    return _send(
        recipient,
        Message(
            subject=f"Your MDARIX trial ends {left}",
            heading=f"Your MDARIX trial for {organization} ends {left}",
            details=(("Trial ends", ends_on), ("Data deleted on", delete_on)),
            paragraphs=(
                "To keep your workspace and its data, reply to this email and we will set up a design-partner or "
                "paid plan with you.",
                "If you do nothing, the workspace closes when the trial ends and its data is deleted 30 days later.",
            ),
            button=("Open MDARIX", f"{company().app_url}/app"),
            reason="You are receiving this email because you started a free MDARIX trial.",
        ),
    )


def send_trial_ended(recipient: str, organization: str, *, delete_on: str) -> str:
    return _send(
        recipient,
        Message(
            subject="Your MDARIX trial has ended",
            heading=f"The MDARIX trial for {organization} has ended",
            paragraphs=(
                "Your workspace is closed. Your data is kept until the date below, then deleted for good.",
                "To continue with your data intact, reply to this email before then.",
            ),
            details=(("Data deleted on", delete_on),),
            reason="You are receiving this email because you started a free MDARIX trial.",
        ),
    )


# ------------------------------------------------------------------------------------------- customer administrators


def send_subscription_reminder(recipient: str, organization: str, *, expires_on: str, days_left: int) -> str:
    when = "today" if days_left <= 0 else f"in {days_left} days"
    return _send(
        recipient,
        Message(
            subject=f"Your MDARIX subscription for {organization} expires {when}",
            heading="Subscription renewal",
            paragraphs=(
                f"The MDARIX subscription for {organization} expires on {expires_on}. Reply to this email or contact "
                "your MDARIX account team to renew, so access continues without interruption.",
            ),
            button=("Open Customer Administration", f"{company().app_url}/app"),
            reason=f"You are receiving this email as an administrator of {organization} in MDARIX.",
        ),
    )


def send_tenant_lifecycle_notice(recipient: str, organization: str, *, transition: str, reason: str | None) -> str:
    states = {
        "SUSPENDED": "suspended: no one in your organization can sign in until it is restored",
        "ACTIVE": "active again: everyone can sign in as before",
        "ARCHIVED": "archived: it is closed and its data is kept only as your agreement requires",
        "TERMINATED": "closed",
    }
    return _send(
        recipient,
        Message(
            subject=f"MDARIX access for {organization} has changed",
            heading=f"MDARIX access for {organization} has changed",
            paragraphs=(f"Your organization's MDARIX workspace is now {states.get(transition, transition.lower())}.",),
            details=(("Reason", reason),) if reason else (),
            closing=("Questions about this change: reply to this email.",),
            reason=f"You are receiving this email as an administrator of {organization} in MDARIX.",
        ),
    )


def send_supplier_evidence_request(
    recipient: str, organization: str, *, title: str, items: list[str], reply_to: str | None
) -> str:
    """A request from a customer to one of its suppliers. Replies go to the person who asked."""
    return _send(
        recipient,
        Message(
            subject=f"Evidence request from {organization}: {title}"[:180],
            heading=f"{organization} asks for evidence",
            paragraphs=(title, "Please reply to this email with the following, attached or as a link:"),
            items=tuple(items),
            closing=("Replies go directly to the person who sent this request.",),
            reason=f"You are receiving this email because {organization} lists you as a supplier contact.",
        ),
        reply_to=reply_to,
    )


# ------------------------------------------------------------------------------------------- the MDARIX team


def send_trial_request_alert(recipient: str, *, organization: str, display_name: str, email: str) -> str:
    """Tell the Platform Admin that a free-trial request is waiting for review."""
    return _send(
        recipient,
        Message(
            subject=f"New MDARIX free trial request: {organization}",
            heading="A free trial request is waiting for review",
            details=(("Company", organization), ("Name", display_name), ("Email", email)),
            button=("Review in Platform Admin", f"{company().app_url}/app/admin"),
            closing=("Platform Admin > Customers & Tenants > Onboarding.",),
            reason="You are receiving this email because you are on the MDARIX trial review rota.",
        ),
    )


def send_demo_request_alert(recipient: str, *, display_name: str, email: str, phone: str) -> str:
    """Tell the MDARIX team that a website visitor asked for a demo."""
    return _send(
        recipient,
        Message(
            subject=f"New MDARIX demo request: {display_name}",
            heading="A website visitor asked for a demo. Please contact them.",
            details=(("Name", display_name), ("Email", email), ("Phone", phone)),
            button=("Open Platform Admin", f"{company().app_url}/app/admin"),
            closing=("Mark it contacted in Platform Admin > Customers & Tenants > Onboarding.",),
            reason="You are receiving this email because you handle MDARIX demo requests.",
        ),
    )


def send_operations_alert(recipient: str, subject: str, body: str) -> str:
    """An operational alert for the team running MDARIX (backend/app/alerts.py)."""
    return _send(
        recipient,
        Message(
            subject=subject,
            heading=subject,
            paragraphs=tuple(line for line in body.split("\n") if line.strip()),
            reason="You are receiving this email because you are on the MDARIX operations alert list.",
        ),
    )
