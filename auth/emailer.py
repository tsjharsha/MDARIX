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
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr

from dotenv import load_dotenv

from backend.app import links

# How long an invitation link works, as the emails say it (auth.durable.INVITATION_SECONDS; a test keeps the two
# in step).
INVITATION_VALID_FOR = "48 hours"

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
    # Without an explicit context smtplib encrypts but verifies neither the certificate nor the host name, so anyone
    # on the path could read the login and the mail. The default context checks both against the system CA store.
    tls = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15, context=tls) as client:
                client.login(username, password)
                client.send_message(email)
        else:
            with smtplib.SMTP(host, port, timeout=15) as client:
                client.starttls(context=tls)
                client.login(username, password)
                client.send_message(email)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailDeliveryError(
            "The email provider refused the message or could not be reached. Check the SMTP settings and the "
            "sender's domain."
        ) from exc
    return "SENT"


# ------------------------------------------------------------------------------------------- accounts


def _privacy_line() -> str:
    """Where an invited person reads how their account data is used, before they activate it."""
    return f"How MDARIX uses your personal data is explained in our privacy policy: {company().app_url}/privacy"


def send_activation_email(
    recipient: str,
    token: str,
    organization: str,
    valid_for: str = INVITATION_VALID_FOR,
    *,
    invited_by: str | None = None,
) -> str:
    """The invitation to an organization's MDARIX; ``invited_by`` names the administrator who sent it."""
    url = f"{company().app_url}/activate-account?token={token}"
    return _send(
        recipient,
        Message(
            subject="Activate your MDARIX account",
            heading=(
                f"{invited_by} invited you to MDARIX for {organization}"
                if invited_by
                else f"You are invited to MDARIX for {organization}"
            ),
            paragraphs=(
                "MDARIX connects complaints, product versions, suppliers, lots and evidence so your team can "
                "investigate product signals in one place.",
                "Choose your password to activate your account. Only you will know it.",
            ),
            button=("Activate my account", url),
            closing=(
                f"This link works once and expires in {valid_for}. If it has expired, ask your administrator to send "
                "a new invitation.",
                _privacy_line(),
            ),
            reason=(
                f"You are receiving this email because {invited_by}, an administrator of {organization}, invited you "
                "to MDARIX."
                if invited_by
                else f"You are receiving this email because an administrator of {organization} invited you to MDARIX."
            ),
        ),
    )


def send_trial_invitation(
    recipient: str,
    token: str,
    organization: str,
    *,
    ends_on: str,
    users: int,
    rows: int,
    valid_for: str = INVITATION_VALID_FOR,
    invited_by: str | None = None,
    sample_data: bool = True,
) -> str:
    """The invitation to a free-trial workspace: what the trial includes and what happens when it ends. The person
    who requested the trial gets it as their own; a colleague the trial's owner invited (``invited_by``, the owner's
    name) learns who invited them and what MDARIX is, and hears of the sample investigation only while the trial
    still has it (``sample_data``). Both are told to have their phone ready for two-factor sign-in."""
    url = f"{company().app_url}/activate-account?token={token}"
    if invited_by:
        return _send(
            recipient,
            Message(
                subject=f"{invited_by} invited you to the MDARIX free trial",
                heading=f"{invited_by} invited you to the MDARIX free trial of {organization}",
                paragraphs=(
                    "MDARIX helps medical-device quality teams handle complaints and post-market surveillance "
                    "investigations: complaints, reporting clocks, trend signals, investigations and the CAPAs to raise "
                    "in your QMS, in one traceable place.",
                    *(
                        (
                            "The trial workspace includes a ready-made sample investigation, so you can see MDARIX at "
                            "work before using any data.",
                        )
                        if sample_data
                        else ()
                    ),
                    "Have your phone ready: when you first sign in, you add MDARIX to an authenticator app on your "
                    "phone (two-factor sign-in) and save your recovery codes.",
                ),
                details=(
                    ("Trial ends", ends_on),
                    ("Included", f"up to {users} users and {rows:,} uploaded rows"),
                    ("Trial data", "deleted 30 days after the trial ends, unless your organization continues"),
                ),
                items=(
                    "Activate your account and choose a password.",
                    "Set up the authenticator app on your phone.",
                    "Open Getting started and follow the sample story."
                    if sample_data
                    else "Open Getting started to see what you can try.",
                ),
                button=("Activate my account", url),
                closing=(f"This link works once and expires in {valid_for}.", _privacy_line()),
                reason=(
                    f"You are receiving this email because {invited_by}, who runs your organization's trial, "
                    "invited you."
                ),
            ),
        )
    # The subject says it is the trial, and the phone is mentioned before the first sign-in asks for it, as in the
    # colleague's invitation (UX-13).
    return _send(
        recipient,
        Message(
            subject="Your MDARIX free trial is ready: activate your account",
            heading="Your MDARIX free trial is ready",
            paragraphs=(
                f"Your private workspace for {organization} is set up with a ready-made sample investigation, so you "
                "can see MDARIX at work before sharing any data.",
                "Have your phone ready: when you first sign in, you add MDARIX to an authenticator app on your phone "
                "(two-factor sign-in) and save your recovery codes.",
            ),
            details=(
                ("Trial ends", ends_on),
                ("Included", f"up to {users} users and {rows:,} uploaded rows"),
                ("Your data", "deleted 30 days after the trial ends, unless you continue"),
            ),
            items=(
                "Activate your account and choose a password.",
                "Set up the authenticator app on your phone.",
                "Open Getting started and follow the sample story.",
                "Try your own data with the CSV templates (no patient-identifiable data, please).",
            ),
            button=("Activate my account", url),
            closing=(f"This link works once and expires in {valid_for}.", _privacy_line()),
            reason="You are receiving this email because you requested a free MDARIX trial.",
        ),
    )


def send_welcome_email(recipient: str, organization: str, *, mfa_required: bool = False) -> str:
    # Whether this person's role must use two-factor sign-in (backend/app/mfa.py required_for): trial users must.
    paragraphs = [f"You can now sign in to MDARIX for {organization} with your email and the password you chose."]
    if mfa_required:
        paragraphs.append(
            "At your first sign-in you set up an authenticator app on your phone (two-factor sign-in) and save your "
            "recovery codes, so have your phone ready."
        )
    return _send(
        recipient,
        Message(
            subject="Welcome to MDARIX",
            heading="Your account is active",
            paragraphs=tuple(paragraphs),
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


# The deletion date in trial emails is the earliest one (backend/app/trial/retention.py deletion_date): a grace
# extension, a request to move the data into the pilot or a legal hold can only make it later.
DELETED_ON = "Data deleted, at the earliest, on"


def send_trial_reminder(recipient: str, organization: str, *, days_left: int, ends_on: str, delete_on: str) -> str:
    left = "today" if days_left <= 0 else ("tomorrow" if days_left == 1 else f"in {days_left} days")
    return _send(
        recipient,
        Message(
            subject=f"Your MDARIX trial ends {left}",
            heading=f"Your MDARIX trial for {organization} ends {left}",
            details=(("Trial ends", ends_on), (DELETED_ON, delete_on)),
            paragraphs=(
                "To continue, reply to this email and we will talk about a pilot with you. The pilot works only with "
                "your real data: if you uploaded your own data and removed the sample data, we can move it into your "
                "pilot on request.",
                "If you do nothing, the workspace closes when the trial ends and its data is deleted 30 days later, "
                "on the date above at the earliest.",
                f"What a pilot on your real data involves is in Next steps, in your workspace: {_app_link('Next steps')}",
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
                "Your workspace is closed. Your data is kept at least until the date below, then deleted for good.",
                "To continue, reply to this email before then and we will talk about a pilot with you. The pilot works "
                "only with your real data: if you uploaded your own data and removed the sample data, we can move it "
                "into your pilot on request.",
            ),
            details=((DELETED_ON, delete_on),),
            reason="You are receiving this email because you started a free MDARIX trial.",
        ),
    )


def send_trial_ended_early(recipient: str, organization: str, *, data_deleted: bool, delete_on: str = "") -> str:
    """Tell the trial owner that the trial ended early as they asked, whether its data is gone or kept until a date,
    and ask, simply by replying, why they ended it (backend/app/trial/early_exit.py)."""
    if data_deleted:
        data = (
            "Everything your organization stored in the trial has been deleted: its records, uploads and files, and "
            "your team's accounts. Only a minimal record that the trial existed is kept, without names or email "
            "addresses, as the free trial agreement and the privacy policy describe.",
        )
        details: tuple[tuple[str, str], ...] = ()
    else:
        data = ("Your workspace is closed. Your data is kept at least until the date below, then deleted for good.",)
        details = ((DELETED_ON, delete_on),) if delete_on else ()
    return _send(
        recipient,
        Message(
            subject="Your MDARIX trial has ended",
            heading=f"The MDARIX trial for {organization} has ended, as you asked",
            paragraphs=(
                "We have ended your free trial early, as you asked.",
                *data,
                "Would you tell us why you ended the trial early? Simply reply to this email: a line or two about what "
                "did not work for you, or what was missing, helps us make MDARIX better for quality teams like yours.",
            ),
            details=details,
            closing=("Thank you for trying MDARIX.",),
            reason="You are receiving this email because you asked to end your free MDARIX trial.",
        ),
    )


def send_trial_exit_declined(recipient: str, organization: str, *, note: str) -> str:
    """Tell the trial owner that their request to end early was not approved yet, with the MDARIX team's message.
    The trial continues."""
    return _send(
        recipient,
        Message(
            subject="Your request to end your MDARIX trial",
            heading=f"About ending the MDARIX trial for {organization}",
            paragraphs=(
                "We have not ended your trial yet. A message from the MDARIX team:",
                note,
                "Your trial continues until its end date. Reply to this email if you still want to end it early.",
            ),
            button=("Open MDARIX", f"{company().app_url}/app"),
            reason="You are receiving this email because you asked to end your free MDARIX trial.",
        ),
    )


def send_trial_exit_request_alert(
    recipient: str,
    *,
    organization: str,
    requested_by: str,
    reason: str = "",
    delete_data: bool = True,
    days_left: int = 0,
) -> str:
    """Tell the MDARIX team that a trial owner asked to end the trial early (to approve in Platform Admin)."""
    details = [
        ("Organization", organization),
        ("Asked by", requested_by),
        ("Their data", "Delete it" if delete_data else "Keep it until the usual deletion date"),
        ("Days left", str(days_left)),
    ]
    if reason:
        details.append(("Why", reason))
    return _send(
        recipient,
        Message(
            subject=f"Trial early end requested: {organization}",
            heading="A free trial asked to end early. Please review it.",
            details=tuple(details),
            button=("Open Platform Admin", f"{company().app_url}/app/admin"),
            closing=("Approve or decline it in Platform Admin > Customers & Tenants > Trials.",),
            reason="You are receiving this email because you handle MDARIX free trials.",
        ),
    )


# ------------------------------------------------------------------------------------------- the trial team
# What a trial owner's change to their team means for the person changed and for the owner
# (backend/app/trial/team.py). No links into MDARIX: nobody is asked to do anything there.

TEAM_REMOVED = "REMOVED"
TEAM_INVITATION_WITHDRAWN = "INVITATION_WITHDRAWN"
TEAM_MFA_RESET = "MFA_RESET"


def _named(name: str, email: str) -> str:
    """The person as "Name (email)", the email alone when they have no other name, or the name alone without an email
    (MDARIX support)."""
    if not email:
        return name
    return email if not name or name == email else f"{name} ({email})"


def _questions() -> str:
    support = company().support_email
    return f"If you have questions about MDARIX, write to {support}." if support else "Questions: reply to this email."


def send_trial_colleague_removed(recipient: str, *, owner: str, organization: str) -> str:
    """Tell a colleague that the trial's owner removed them from the trial."""
    return _send(
        recipient,
        Message(
            subject=f"{owner} removed you from the MDARIX free trial of {organization}",
            heading=f"{owner} removed you from the MDARIX free trial of {organization}",
            paragraphs=(
                "You can no longer sign in to this trial, and you were signed out.",
                f"What you did in the trial stays there under your name: it is part of the trial data of {organization}.",
                f"If this is unexpected, please contact {owner}.",
            ),
            closing=(_questions(),),
            reason=f"You are receiving this email because you were on the MDARIX free trial of {organization}.",
        ),
    )


def send_trial_invitation_withdrawn(recipient: str, *, owner: str, organization: str) -> str:
    """Tell an invited colleague, who had not activated yet, that the trial's owner withdrew the invitation."""
    return _send(
        recipient,
        Message(
            subject=f"{owner} withdrew your invitation to the MDARIX free trial of {organization}",
            heading=f"{owner} withdrew your invitation to the MDARIX free trial of {organization}",
            paragraphs=(
                "The activation link in the earlier invitation email no longer works. You do not need to do anything.",
            ),
            closing=(_questions(),),
            reason=f"You are receiving this email because {owner} invited you to the MDARIX free trial of "
            f"{organization}.",
        ),
    )


def send_trial_mfa_reset_notice(
    recipient: str, *, owner: str, organization: str, when: str, by_support: bool = False
) -> str:
    """Tell a colleague that the trial's owner removed their authenticator. With ``by_support`` MDARIX support removed
    it in Platform Admin (for the owner or a colleague who lost their phone and recovery codes): ``owner`` is then
    "MDARIX support", never the staff member's name. The reason stays in the audit trail: it is not part of this
    email."""
    support = company().support_email
    who = (
        f"{owner} removed the authenticator app of your account in the MDARIX free trial of {organization}"
        if by_support
        else f"{owner}, who runs the MDARIX free trial of {organization}, removed the authenticator app of your account"
    )
    return _send(
        recipient,
        Message(
            subject="The authenticator app of your MDARIX account was removed",
            heading=f"{owner} removed the authenticator app of your MDARIX account",
            paragraphs=(
                f"{who}, and you were signed out.",
                "At your next sign-in, sign in with your password as usual: MDARIX then asks you to set up a new "
                "authenticator app on your phone and gives you new recovery codes.",
            ),
            details=(("When", when),),
            closing=(
                (f"If you did not ask for this, contact {support}." if support else _questions())
                if by_support
                else f"If you did not ask for this, contact {owner}" + (f" or {support}." if support else "."),
            ),
            reason="You are receiving this email because the sign-in settings of your MDARIX account changed.",
        ),
    )


def send_trial_team_change_confirmation(
    recipient: str, *, change: str, person: str, person_email: str, organization: str, when: str
) -> str:
    """Confirm to the trial's owner a change they made to their team. It is also a security notice: if the owner's
    account is misused, the owner learns of it."""
    if change == TEAM_REMOVED:
        subject = f"You removed {person} from your MDARIX trial"
        what = (
            f"{_named(person, person_email)} can no longer sign in to the MDARIX free trial of {organization} and was "
            "signed out. Their seat is free for someone else, and what they did stays in the trial under their name. "
            "MDARIX has told them by email."
        )
    elif change == TEAM_INVITATION_WITHDRAWN:
        subject = f"You withdrew the invitation to {person}"
        what = (
            f"The activation link MDARIX sent to {person_email} no longer works, and the seat is free for someone "
            "else. MDARIX has told them by email."
        )
    else:
        subject = f"You reset {person}'s authenticator"
        what = (
            f"The authenticator app of {_named(person, person_email)} was removed and they were signed out of the MDARIX "
            f"free trial of {organization}. They set up a new one at their next sign-in. MDARIX has told them by "
            "email."
        )
    support = company().support_email
    return _send(
        recipient,
        Message(
            subject=subject,
            heading=subject,
            paragraphs=(what,),
            details=(("When", when),),
            closing=(
                "If this was not you, change your password now"
                + (f" and contact {support}." if support else " and reply to this email."),
            ),
            reason=f"You are receiving this email because you run the MDARIX free trial of {organization}.",
        ),
    )


# ------------------------------------------------------------------------------------------- an organization's team
# What a Customer Administrator's change to a paying organization's team means for the person changed, and for the
# organization's other Customer Administrators when it concerns an administrator account (backend/app/team_notices.py).
# The words follow the trial's team emails, for an organization that is not a trial.

TEAM_INVITED = "INVITED"
TEAM_SUSPENDED = "SUSPENDED"
TEAM_RESTORED = "RESTORED"
TEAM_ROLE_CHANGED = "ROLE_CHANGED"


def send_team_change_notice(
    recipient: str,
    *,
    change: str,
    actor: str,
    organization: str,
    when: str,
    role_before: str | None = None,
    role_now: str | None = None,
    roles_added: tuple[str, ...] = (),
    roles_removed: tuple[str, ...] = (),
    by_support: bool = False,
) -> str:
    """Tell a person what an administrator of their organization changed about their account, and who did. With
    ``by_support`` the change was MDARIX support's, in Platform Admin: ``actor`` is "MDARIX support", not one of the
    organization's administrators."""
    support = company().support_email
    # Who made the change, in the sentence that says what they did.
    who = actor if by_support else f"{actor}, an administrator of {organization},"
    # Said after the details, where the person has read what changed.
    contact: tuple[str, ...] = (f"If this is unexpected, please contact {actor}.",)
    button = None
    details: list[tuple[str, str]] = []
    items: tuple[str, ...] = ()
    reason = f"You are receiving this email because you have an MDARIX account for {organization}."
    if change == TEAM_REMOVED:
        subject = f"{actor} removed you from MDARIX for {organization}"
        paragraphs = (
            f"You can no longer sign in to MDARIX for {organization}, and you were signed out.",
            f"What you did in MDARIX stays there under your name: it is part of the records of {organization}.",
        )
        reason = f"You are receiving this email because you had an MDARIX account for {organization}."
    elif change == TEAM_INVITATION_WITHDRAWN:
        subject = f"{actor} withdrew your invitation to MDARIX for {organization}"
        paragraphs = (
            "The activation link in the earlier invitation email no longer works. You do not need to do anything.",
        )
        reason = f"You are receiving this email because {actor} invited you to MDARIX for {organization}."
        contact = ()
    elif change == TEAM_SUSPENDED:
        subject = f"{actor} suspended your MDARIX account for {organization}"
        paragraphs = (
            f"You cannot sign in until an administrator of {organization} restores your account, and you were "
            "signed out.",
            "Nothing you did in MDARIX is changed.",
        )
    elif change == TEAM_RESTORED:
        subject = f"Your MDARIX account for {organization} is active again"
        paragraphs = (
            f"{actor} restored your account. You can sign in to MDARIX for {organization} again with your email and "
            "your password.",
        )
        button = ("Sign in", f"{company().app_url}/signin")
        contact = ()
    elif change == TEAM_ROLE_CHANGED:
        subject = f"{actor} changed your role in MDARIX for {organization}"
        paragraphs = (f"{who} changed what you can do in MDARIX. It applies from your next action in MDARIX.",)
        if role_before and role_now:
            details += [("Role before", role_before), ("Role now", role_now)]
        items = tuple(f"Added: {role}" for role in roles_added) + tuple(f"Removed: {role}" for role in roles_removed)
    else:  # TEAM_MFA_RESET
        return _send(
            recipient,
            Message(
                subject="The authenticator app of your MDARIX account was removed",
                heading=f"{actor} removed the authenticator app of your MDARIX account",
                paragraphs=(
                    f"{who} removed the authenticator app of your account, and you were signed out.",
                    "At your next sign-in, sign in with your password as usual: MDARIX then asks you to set up a new "
                    "authenticator app on your phone and gives you new recovery codes.",
                ),
                details=(("When", when),),
                closing=(
                    (f"If you did not ask for this, contact {support}." if support else _questions())
                    if by_support
                    else f"If you did not ask for this, contact {actor}" + (f" or {support}." if support else "."),
                ),
                reason="You are receiving this email because the sign-in settings of your MDARIX account changed.",
            ),
        )
    return _send(
        recipient,
        Message(
            subject=subject,
            heading=subject,
            paragraphs=paragraphs,
            details=(*details, ("When", when)),
            items=items,
            button=button,
            closing=(*contact, _questions()),
            reason=reason,
        ),
    )


def send_team_admin_change_notice(
    recipient: str,
    *,
    change: str,
    actor: str,
    actor_email: str,
    person: str,
    person_email: str,
    organization: str,
    when: str,
    role_before: str | None = None,
    role_now: str | None = None,
    by_support: bool = False,
) -> str:
    """Tell a Customer Administrator that another administrator changed an administrator account of the organization
    (or made someone one, or took the role away). A security notice: a change nobody expected is noticed. With
    ``by_support`` MDARIX support made the change in Platform Admin (``actor`` is "MDARIX support")."""
    title = "a Customer Administrator"
    if change == TEAM_INVITED:
        subject = f"{actor} invited {person} as a Customer Administrator of {organization}"
    elif change == TEAM_REMOVED:
        subject = f"{actor} removed {person}, {title} of {organization}"
    elif change == TEAM_INVITATION_WITHDRAWN:
        subject = f"{actor} withdrew the invitation to {person} as a Customer Administrator of {organization}"
    elif change == TEAM_SUSPENDED:
        subject = f"{actor} suspended {person}, {title} of {organization}"
    elif change == TEAM_RESTORED:
        subject = f"{actor} restored the account of {person}, {title} of {organization}"
    elif change == TEAM_ROLE_CHANGED and role_now == "Customer Administrator":
        subject = f"{actor} made {person} a Customer Administrator of {organization}"
    elif change == TEAM_ROLE_CHANGED:
        subject = f"{actor} took the Customer Administrator role from {person}"
    else:  # TEAM_MFA_RESET
        subject = f"{actor} reset the authenticator of {person}, {title} of {organization}"
    details = [("Changed by", _named(actor, actor_email)), ("Person", _named(person, person_email))]
    if change == TEAM_ROLE_CHANGED and role_before and role_now:
        details += [("Role before", role_before), ("Role now", role_now)]
    support = company().support_email
    return _send(
        recipient,
        Message(
            subject=subject,
            heading=subject,
            paragraphs=(
                f"Every Customer Administrator of {organization} is told when an administrator account changes, so "
                "that a change nobody expected is noticed. You do not need to do anything if you expected it.",
            ),
            details=(*details, ("When", when)),
            button=("Review the users", f"{company().app_url}/app/customer-admin"),
            closing=(
                (
                    f"If you did not expect this, contact {support}."
                    if support
                    else "If you did not expect this, reply to this email."
                )
                if by_support
                else f"If you did not expect this, check with {actor}"
                + (f" and contact {support}." if support else " and reply to this email."),
            ),
            reason=f"You are receiving this email as an administrator of {organization} in MDARIX.",
        ),
    )


# ------------------------------------------------------------------------------------------- customer administrators


def send_subscription_reminder(
    recipient: str,
    organization: str,
    *,
    expires_on: str,
    days_left: int,
    template: tuple[str, str] | None = None,
) -> str:
    """The renewal reminder. ``template`` is the organization's own (subject, body) with its values already filled in
    (backend/app/notifications.py); without one, the standard wording is used. Either way the layout, the footer and
    the escaping are the same, so a template can change the words but never inject markup."""
    when = "today" if days_left <= 0 else f"in {days_left} days"
    if template:
        subject, body = template
        paragraphs = tuple(" ".join(part.split()) for part in body.split("\n\n") if part.strip())
        heading = subject
    else:
        subject = f"Your MDARIX subscription for {organization} expires {when}"
        heading = "Subscription renewal"
        paragraphs = (
            f"The MDARIX subscription for {organization} expires on {expires_on}. Reply to this email or contact "
            "your MDARIX account team to renew, so access continues without interruption.",
        )
    return _send(
        recipient,
        Message(
            subject=subject,
            heading=heading,
            paragraphs=paragraphs,
            button=("Open MDARIX", f"{company().app_url}/app"),
            reason=f"You are receiving this email because {organization} lists you to receive MDARIX subscription "
            "reminders.",
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

# Where Platform Admin handles demo, trial and pilot requests, and the address that opens it (FUN-11: it is under
# Identity & Access, not Customers & Tenants; frontend/src/app/router.ts "platform-onboarding").
ONBOARDING_PLACE = "Platform Admin > Identity & Access > Onboarding"
ONBOARDING_PATH = "/platform-admin/onboarding"


def send_trial_request_alert(
    recipient: str, *, organization: str, display_name: str, email: str, profile_lines: tuple = ()
) -> str:
    """Tell the Platform Admin that a free-trial request is waiting for review. ``profile_lines`` = what the requester
    said about their company and trial, as (label, words) pairs (backend/app/trial/request_profile.py describe)."""
    return _send(
        recipient,
        Message(
            subject=f"New MDARIX free trial request: {organization}",
            heading="A free trial request is waiting for review",
            details=(("Company", organization), ("Name", display_name), ("Email", email), *profile_lines),
            button=("Review in Platform Admin", f"{company().app_url}{ONBOARDING_PATH}"),
            closing=(f"{ONBOARDING_PLACE}.",),
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
            button=("Open Platform Admin", f"{company().app_url}{ONBOARDING_PATH}"),
            closing=(f"Mark it contacted in {ONBOARDING_PLACE}.",),
            reason="You are receiving this email because you handle MDARIX demo requests.",
        ),
    )


def send_trial_demo_request_alert(
    recipient: str,
    *,
    display_name: str,
    email: str,
    organization: str,
    phone: str = "",
    preferred_time: str = "",
    progress: str = "",
    focus: tuple[str, ...] = (),
    note: str = "",
) -> str:
    """Tell the MDARIX team that someone in a free trial booked a one-to-one demo, with how far the trial got."""
    details = [("Name", display_name), ("Email", email), ("Organization", organization)]
    if phone:
        details.append(("Phone", phone))
    if preferred_time:
        details.append(("Times that suit", preferred_time))
    if progress:
        details.append(("Trial progress", progress))
    if focus:
        details.append(("Focus", "; ".join(focus)))
    return _send(
        recipient,
        Message(
            subject=f"Trial demo request: {organization} ({display_name})",
            heading="Someone in a free trial booked a one-to-one demo. Please contact them.",
            details=tuple(details),
            paragraphs=(f"Their note: {note}",) if note else (),
            button=("Open Platform Admin", f"{company().app_url}{ONBOARDING_PATH}"),
            closing=(f"Mark it contacted in {ONBOARDING_PLACE}.",),
            reason="You are receiving this email because you handle MDARIX demo requests.",
        ),
    )


def send_trial_mvp_request_alert(
    recipient: str,
    *,
    display_name: str,
    email: str,
    organization: str,
    expectations: str,
    scope: str = "",
    phone: str = "",
    contact_preference: str = "",
    move_trial_data: bool = False,
    days_left: int = 0,
    updated: bool = False,
) -> str:
    """Tell the MDARIX team that someone in a free trial asked for a pilot conversation (or updated their request)."""
    details = [("Name", display_name), ("Email", email), ("Organization", organization)]
    if phone:
        details.append(("Phone", phone))
    if contact_preference:
        details.append(("How and when to reach them", contact_preference))
    details.append(("Trial data", "Move it into the pilot" if move_trial_data else "Start the pilot without it"))
    details.append(("Days left in the trial", str(days_left)))
    paragraphs = [f"What they expect from the pilot: {expectations}"]
    if scope:
        paragraphs.append(f"Products, sites and systems in mind: {scope}")
    return _send(
        recipient,
        Message(
            subject=f"Pilot conversation {'request updated' if updated else 'requested'}: {organization}",
            heading=(
                "A free trial updated its request for a pilot conversation."
                if updated
                else "Someone in a free trial asked for a pilot conversation. Please reply to arrange a scoping call."
            ),
            details=tuple(details),
            paragraphs=tuple(paragraphs),
            button=("Open Platform Admin", f"{company().app_url}{ONBOARDING_PATH}"),
            closing=(f"Mark it contacted in {ONBOARDING_PLACE}.",),
            reason="You are receiving this email because you handle MDARIX demo requests.",
        ),
    )


_TEAM_CHANGE_WORDS = {
    TEAM_REMOVED: "removed {person}",
    TEAM_INVITATION_WITHDRAWN: "withdrew the invitation to {person}",
    TEAM_MFA_RESET: "reset MFA for {person}",
}


def send_trial_team_change_alert(
    recipient: str,
    *,
    change: str,
    organization: str,
    tenant_key: str,
    owner: str,
    owner_email: str,
    person_email: str,
    when: str,
) -> str:
    """Tell the MDARIX team that a trial owner removed a colleague, withdrew an invitation or reset a colleague's MFA
    (Platform Admin > Customers & Tenants > Trials shows the trial's team changes too)."""
    done = _TEAM_CHANGE_WORDS.get(change, "changed {person}").format(person=person_email)
    line = f"Trial team change: {organization} ({tenant_key}): {owner} {done}"
    return _send(
        recipient,
        Message(
            subject=line[:180],
            heading=line,
            details=(
                ("Organization", organization),
                ("Tenant key", tenant_key),
                ("Trial owner", _named(owner, owner_email)),
                ("Person", person_email),
                ("When", when),
            ),
            button=("Open Platform Admin", f"{company().app_url}/app/admin"),
            closing=("The trial's team changes are under Platform Admin > Customers & Tenants > Trials.",),
            reason="You are receiving this email because you handle MDARIX free trials.",
        ),
    )


def send_operations_alert(recipient: str, subject: str, body: str, *, reply_to: str | None = None) -> str:
    """An operational alert for the team running MDARIX (backend/app/alerts.py). ``reply_to`` is the person a reply
    should reach (a problem report's reporter, FUN-07); without it a reply goes to the support address."""
    return _send(
        recipient,
        Message(
            subject=subject,
            heading=subject,
            paragraphs=tuple(line for line in body.split("\n") if line.strip()),
            reason="You are receiving this email because you are on the MDARIX operations alert list.",
        ),
        reply_to=reply_to,
    )


def send_feedback_alert(
    recipient: str,
    *,
    organization: str,
    rating: int,
    recommend_score: int | None,
    consent: str,
    contact_ok: bool,
) -> str:
    """Tell the MDARIX team that a customer sent product feedback. The answers themselves stay in Platform Admin."""
    consents = {
        "NAMED": "may be quoted with the company's name, after review",
        "ANONYMOUS": "may be quoted anonymously, after review",
        "PRIVATE": "for the MDARIX team only",
    }
    return _send(
        recipient,
        Message(
            subject=f"New MDARIX feedback from {organization}",
            heading="A customer sent feedback",
            details=(
                ("Organization", organization),
                ("Overall rating", f"{rating} of 5"),
                ("Would recommend", f"{recommend_score} of 10" if recommend_score is not None else "not answered"),
                ("Quote", consents.get(consent, consent.lower())),
                ("May be contacted", "yes" if contact_ok else "no"),
            ),
            button=("Read it in Platform Admin", f"{company().app_url}/app/admin"),
            reason="You are receiving this email because you handle MDARIX customer feedback.",
        ),
    )


# ------------------------------------------------------------------------------------------- people who asked us


def send_demo_request_acknowledgement(recipient: str, *, display_name: str) -> str:
    """Confirm to a website visitor that their demo request arrived and what happens next."""
    return _send(
        recipient,
        Message(
            subject="We received your MDARIX demo request",
            heading=f"Thank you, {display_name}",
            paragraphs=(
                "We received your request for an MDARIX demo. Someone from our team will contact you, usually "
                "within one business day, to agree a time.",
                "You do not need to do anything else. If you did not ask for a demo, you can ignore this email; we "
                "will not contact you unless you reply.",
            ),
            reason="You are receiving this email because this address was entered on the MDARIX demo request form.",
        ),
    )


def send_trial_request_acknowledgement(recipient: str, *, display_name: str, organization: str) -> str:
    """Confirm to the requester that their free-trial request is waiting for review."""
    return _send(
        recipient,
        Message(
            subject="We received your MDARIX free trial request",
            heading=f"Thank you, {display_name}",
            paragraphs=(
                f"We received your request for a free MDARIX trial for {organization}. The MDARIX team reviews it, "
                "usually within one business day.",
                "Once it is approved you will receive a second email with a link to activate your account. The link "
                "works once, so keep that email.",
            ),
            closing=("If you did not ask for a trial, you can ignore this email.",),
            reason="You are receiving this email because this address was entered on the MDARIX free trial form.",
        ),
    )


def send_trial_request_declined(recipient: str, *, display_name: str, organization: str) -> str:
    """Tell the requester, politely, that their free-trial request was not approved, and how to reach us.

    The administrator's reason is an internal note and is deliberately not included.
    """
    support = company().support_email
    contact = f"write to {support}" if support else "reply to this email"
    return _send(
        recipient,
        Message(
            subject="Your MDARIX free trial request",
            heading=f"Thank you for your interest, {display_name}",
            paragraphs=(
                f"We have reviewed your request for a free MDARIX trial for {organization} and are not able to "
                "offer a trial at this time.",
                "Trials are currently limited to organizations we can support closely during the evaluation. This "
                "is not a judgement on your organization, and it may change.",
            ),
            closing=(f"If you would like to talk about MDARIX, {contact} and we will gladly help.",),
            reason="You are receiving this email because this address was entered on the MDARIX free trial form.",
        ),
    )


# ------------------------------------------------------------------------------------------- workspace work


def send_urgent_case_alert(
    recipient: str, *, organization: str, reference: str, received: str | None, reminder: bool = False
) -> str:
    """B7 (spec 5): an urgent case arrived, open MDARIX. Only the reference and the time: never a product, the
    reporter's words or patient data; the link needs sign-in and MFA."""
    at = f" at {received}" if received else ""
    return _send(
        recipient,
        Message(
            subject="MDARIX: urgent case not acknowledged" if reminder else "MDARIX: urgent case received",
            heading="An urgent case still waits for acknowledgement" if reminder else "An urgent case was received",
            paragraphs=(f"An urgent case ({reference}) was received{at}. Open MDARIX to see it.",),
            button=("Open MDARIX", _app_link("Complaints", "Triage")),
            reason=_work_reason(organization),
        ),
    )


def _work_reason(organization: str) -> str:
    return f"You are receiving this email because of your work in MDARIX for {organization}."


def _app_link(section: str, tab: str | None = None, *, case: str | None = None) -> str:
    """A link to a workspace screen, in the browser's own address scheme (backend/app/links.py app_path)."""
    return f"{company().app_url}{links.app_path(section, tab, record=('case', case) if case else None)}"


def _case_link(step: str | None, case: str | None) -> str | None:
    """A deep link that opens one investigation on its case page, at a step (/app/investigations?case=INV000147&
    step=Decision), or None without a case."""
    case = str(case or "").strip()
    if not case:
        return None
    return _app_link("Investigations", step, case=case)


def send_assignment_notice(
    recipient: str, *, organization: str, reference: str, assigned_by: str | None, case: str | None = None
) -> str:
    """An investigation was assigned to the recipient. With ``case`` (the investigation's business id) the button
    opens that investigation; without it, My work."""
    case_url = _case_link(None, case)
    return _send(
        recipient,
        Message(
            subject=f"Investigation {reference} is assigned to you",
            heading=f"Investigation {reference} is assigned to you",
            paragraphs=(
                (f"{assigned_by} assigned you" if assigned_by else "You were assigned")
                + f" investigation {reference} in MDARIX for {organization}.",
            ),
            button=("Open the investigation", case_url) if case_url else ("Open My work", _app_link("My Work")),
            reason=_work_reason(organization),
        ),
    )


def send_review_pending_notice(
    recipient: str, *, organization: str, reference: str, submitted_by: str | None, case: str | None = None
) -> str:
    """A decision is waiting for the recipient's approval. With ``case`` (the investigation's business id) the
    button opens that case's decision."""
    case_url = _case_link("Decision", case)
    return _send(
        recipient,
        Message(
            subject=f"A decision on {reference} is waiting for your approval",
            heading="A decision is waiting for your approval",
            paragraphs=(
                (f"{submitted_by} submitted" if submitted_by else "Someone submitted")
                + f" a decision on {reference} for approval in MDARIX for {organization}.",
                "Approving or rejecting it needs your password and authenticator code.",
            ),
            # The case's Decision step, where the decision is reviewed and signed; without a case, My Work's
            # approvals. ("Open Decisions" named a section the MVP parks, 0.10.67.)
            button=("Open the decision", case_url or _app_link("My Work", "Approvals")),
            reason=_work_reason(organization),
        ),
    )


def send_signoff_completed_notice(
    recipient: str,
    *,
    organization: str,
    reference: str,
    signed_by: str | None,
    decision: str | None = None,
    case: str | None = None,
) -> str:
    """A decision on a case the recipient owns was signed: approved, rejected, or (outcome unknown) signed off. With
    ``case`` (the investigation's business id) the button opens that case's decision."""
    case_url = _case_link("Decision", case)
    done = {"APPROVE": "approved", "REJECT": "rejected"}.get(str(decision or "").upper(), "signed off")
    return _send(
        recipient,
        Message(
            subject=f"The decision on {reference} was {done}",
            heading=f"The decision on {reference} was {done}",
            paragraphs=(
                f"The decision on {reference}, which you own, was {done} with an electronic signature"
                + (f" by {signed_by}" if signed_by else "")
                + f" in MDARIX for {organization}. The signature is recorded in the audit trail.",
            ),
            button=("Open the decision", case_url)
            if case_url
            else ("Open investigations", _app_link("Investigations")),
            reason=_work_reason(organization),
        ),
    )


def send_risk_review_requested_notice(
    recipient: str, *, organization: str, reference: str, requested_by: str | None
) -> str:
    """Someone asked the recipient to review a risk."""
    return _send(
        recipient,
        Message(
            subject=f"Risk review requested: {reference}",
            heading="A risk review is requested",
            paragraphs=(
                (f"{requested_by} asked" if requested_by else "You were asked")
                + f" for a review of risk {reference} in MDARIX for {organization}.",
            ),
            # The review is a task in My Work (Risk & Traceability is parked under the MVP: the link went nowhere).
            button=("Open My work", _app_link("My Work")),
            reason=_work_reason(organization),
        ),
    )


# ------------------------------------------------------------------------------------------- organization health


def send_connector_sync_failed_notice(recipient: str, *, organization: str, connection: str, failure: str) -> str:
    """A scheduled read of a customer system failed; nothing from that run was imported."""
    return _send(
        recipient,
        Message(
            subject=f"MDARIX could not sync {connection}",
            heading=f"The scheduled sync of {connection} failed",
            paragraphs=(
                "Nothing from this run was imported; the records already in MDARIX are unchanged. The next "
                "scheduled run tries again, and you will not get another email while the problem continues.",
            ),
            details=(("Connection", connection), ("Problem", failure)),
            button=("Open Customer Administration", f"{company().app_url}/app/customer-admin"),
            reason=f"You are receiving this email as an administrator of {organization} in MDARIX.",
        ),
    )


def _support_decider(organization: str, trial: bool) -> tuple[str, tuple[str, str], str]:
    """Who decides on support access, where, and why they get the email: a free trial's owner in Getting started ›
    Team; elsewhere the organization's administrators in Customer Administration."""
    if trial:
        return (
            "you approve it",
            ("Open Getting started › Team", _app_link("Getting started", "Team")),
            f"You are receiving this email because you run the MDARIX free trial of {organization}.",
        )
    return (
        "one of your administrators approves it",
        ("Review the request", f"{company().app_url}/app/customer-admin"),
        f"You are receiving this email as an administrator of {organization} in MDARIX.",
    )


def send_support_access_request(
    recipient: str,
    *,
    organization: str,
    person: str,
    areas: list[str],
    write: bool,
    expires: str,
    reason: str,
    trial: bool = False,
) -> str:
    """MDARIX asks to see part of the organization's data: nothing opens until its decision maker approves (one of its
    administrators, or a free trial's owner)."""
    who_decides, button, why = _support_decider(organization, trial)
    return _send(
        recipient,
        Message(
            subject=f"MDARIX asks for support access to {organization}",
            heading="MDARIX asks for your approval",
            paragraphs=(
                f"MDARIX support would like {person} to have temporary access to part of {organization}'s data. "
                f"Nothing is opened until {who_decides}, and you can revoke it at any time.",
                "Every use of the access is recorded in your audit trail.",
            ),
            details=(
                ("Who", person),
                ("Access", "Read and change" if write else "Read only"),
                ("Until", expires),
                ("Why", reason),
            ),
            items=tuple(areas),
            button=button,
            reason=why,
        ),
    )


def send_support_access_granted(
    recipient: str,
    *,
    organization: str,
    person: str,
    areas: list[str],
    write: bool,
    expires: str,
    approved_by: str,
    trial: bool = False,
) -> str:
    """Confirm an approved support access: who has it, to what, and when it ends. Also a security notice."""
    _, button, why = _support_decider(organization, trial)
    support = company().support_email
    return _send(
        recipient,
        Message(
            subject=f"Support access to {organization} is approved",
            heading="You gave MDARIX support access",
            paragraphs=(
                f"{approved_by} approved access for {person} to part of {organization}'s data. "
                f"It is {'read and change' if write else 'read only'} and ends on its own at the time below.",
                "Every use is recorded in your audit trail. You can revoke the access at any time.",
            ),
            details=(("Who", person), ("Approved by", approved_by), ("Until", expires)),
            items=tuple(areas),
            button=(("Revoke or review it", button[1]) if trial else button),
            closing=(
                "If you did not approve this, revoke it now"
                + (f" and contact {support}." if support else " and reply to this email."),
            ),
            reason=why,
        ),
    )


_SUPPORT_ENDINGS = {
    "EXPIRED": "Its time ran out.",
    "REVOKED_BY_CUSTOMER": "Your organization revoked it.",
    "REVOKED_BY_MDARIX": "MDARIX support ended it.",
}


def send_support_access_ended(
    recipient: str, *, organization: str, person: str, ended: str, when: str, trial: bool = False
) -> str:
    """An approved support access ended: on its own, or revoked by the organization or by MDARIX."""
    _, button, why = _support_decider(organization, trial)
    return _send(
        recipient,
        Message(
            subject=f"Support access to {organization} has ended",
            heading="MDARIX support access has ended",
            paragraphs=(
                f"{person} can no longer see {organization}'s data. {_SUPPORT_ENDINGS.get(ended, '')}".strip(),
                "What was opened while it lasted is in your audit trail. MDARIX needs a new approval to look again.",
            ),
            details=(("Who", person), ("Ended", when)),
            button=(("See the history", button[1]) if trial else button),
            reason=why,
        ),
    )


_COLLEAGUE_ENDINGS = {
    "EXPIRED": "Its time ran out.",
    "REVOKED_BY_CUSTOMER": "The person who runs the trial ended it.",
    "REVOKED_BY_MDARIX": "MDARIX support ended it.",
}


def _colleague_reason(organization: str) -> str:
    return f"You are receiving this email because you are on the MDARIX free trial of {organization}."


def send_support_access_colleague_granted(
    recipient: str,
    *,
    organization: str,
    person: str,
    areas: list[str],
    write: bool,
    expires: str,
    approved_by: str,
) -> str:
    """Tell a colleague in a free trial that MDARIX support was given access. For information only: the trial's owner
    decides, so this email has no button."""
    access = "read and change" if write else "read-only"
    return _send(
        recipient,
        Message(
            subject=f"MDARIX support has {access} access to the {organization} trial",
            heading="MDARIX support has access to your trial",
            paragraphs=(
                f"{approved_by} gave {person} of MDARIX support {access} access to part of the data in the MDARIX "
                f"free trial of {organization}, until the time below.",
                "Every use is recorded in the trial's audit trail. Only the person who runs the trial decides on "
                "support access and can end it at any time. You do not need to do anything.",
            ),
            details=(
                ("Who", person),
                ("Access", access.capitalize()),
                ("Approved by", approved_by),
                ("Until", expires),
            ),
            items=tuple(areas),
            reason=_colleague_reason(organization),
        ),
    )


def send_support_access_colleague_ended(
    recipient: str, *, organization: str, person: str, ended: str, when: str
) -> str:
    """Tell a colleague in a free trial that MDARIX support's access ended. For information only, with no button."""
    return _send(
        recipient,
        Message(
            subject=f"MDARIX support access to the {organization} trial has ended",
            heading="MDARIX support access has ended",
            paragraphs=(
                f"{person} of MDARIX support can no longer see the data in the MDARIX free trial of {organization}. "
                f"{_COLLEAGUE_ENDINGS.get(ended, '')}".strip(),
                "What was opened while it lasted is in the trial's audit trail. You do not need to do anything.",
            ),
            details=(("Who", person), ("Ended", when)),
            reason=_colleague_reason(organization),
        ),
    )


_DIGEST_STATES = {"CLEAR": "Clear", "ATTENTION": "Needs attention", "CRITICAL": "Critical", "NOT_SET": "Not set up"}


def send_readiness_digest(recipient: str, *, organization: str, week: str, content: dict) -> str:
    """The weekly readiness email (backend/app/readiness_home/digest.py): the loop, what changed, the weakest link."""
    clear, total = int(content.get("clear") or 0), int(content.get("total") or 0)
    stations = [item for item in content.get("stations") or [] if isinstance(item, dict)]
    weakest = content.get("weakest") if isinstance(content.get("weakest"), dict) else None
    changed = [str(line) for line in content.get("changes") or []]

    def number(value) -> str:
        return "unknown" if value is None else str(value)

    paragraphs = [
        f"{clear} of {total} inspection checks are clear in {organization} this week."
        + (
            " This is your first weekly readiness email: next week it will also say what changed."
            if content.get("first")
            else ""
        )
    ]
    if weakest:
        state = _DIGEST_STATES.get(weakest.get("state"), weakest.get("state") or "")
        line = f"Weakest link: {weakest.get('label')}, {state.lower()} ({number(weakest.get('value'))})."
        if weakest.get("detail"):
            line += f" {weakest['detail']}."
        paragraphs.append(line)
        if weakest.get("why"):
            paragraphs.append(f"Why it matters: {weakest['why']}")
    else:
        paragraphs.append("Every station of the loop is clear. Keep it that way: the checks run every day.")
    if not content.get("first"):
        paragraphs.append("What changed since last week:" if changed else "Nothing changed since last week.")
    return _send(
        recipient,
        Message(
            subject=f"Your quality loop this week: {clear} of {total} inspection checks clear ({week})",
            heading=f"Your quality loop this week, {organization}",
            paragraphs=tuple(paragraphs),
            items=tuple(changed),
            details=tuple(
                (
                    str(station.get("label")),
                    f"{number(station.get('value'))} · {_DIGEST_STATES.get(station.get('state'), station.get('state') or '')}",
                )
                for station in stations
            ),
            button=("Open Readiness", _app_link("Readiness")),
            closing=(
                "On Readiness, the inspection pack (ZIP) holds the summary PDF and every record behind these checks.",
            ),
            reason=(
                f"You receive this weekly summary because you lead quality for {organization} in MDARIX. To stop it, "
                "switch off the weekly readiness email under My Account."
            ),
        ),
    )


def send_ai_budget_notice(
    recipient: str, *, organization: str, percent: int, month: str, tokens_used: int | None, budget: int | None
) -> str:
    """The organization used 80% or all of its monthly AI budget."""
    reached = percent >= 100
    details: tuple[tuple[str, str], ...] = (("Month", month),)
    if tokens_used is not None and budget is not None:
        details += (("Used", f"{tokens_used:,} of {budget:,} tokens"),)
    if reached:
        subject = f"{organization} has used its MDARIX AI budget for {month}"
        heading = "The AI budget is used up"
        explanation = (
            "AI features (drafting, Ask MDARIX, the AI investigator) are paused until next month or until the "
            "budget is raised. Everything else keeps working."
        )
    else:
        subject = f"{organization} has used {percent}% of its MDARIX AI budget for {month}"
        heading = f"{percent}% of the AI budget is used"
        explanation = (
            "When the budget is used up, AI features pause until next month; everything else keeps working. "
            "Your MDARIX account team can raise the budget."
        )
    return _send(
        recipient,
        Message(
            subject=subject,
            heading=heading,
            paragraphs=(explanation,),
            details=details,
            button=("Open Customer Administration", f"{company().app_url}/app/customer-admin"),
            reason=f"You are receiving this email as an administrator of {organization} in MDARIX.",
        ),
    )
