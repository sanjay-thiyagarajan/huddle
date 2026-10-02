"""Reminder delivery. Honest about what actually goes out.

Channels:
  in_app  always: the person's own page shows a banner (and a browser notification if they allow it).
  email   only when HUDDLE_SMTP_HOST is set AND the person gave an address; otherwise it reports "skipped".
There is no SMS, web push or Alexa notification. Reminder text carries no private values and does not
say who else has or hasn't answered. Email addresses are never logged or returned by any API.
"""

import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")

_DECISION = {"care": "care", "everyday": "weekend", "trip": "trip"}
_KIND_LINE = {
    "first": "This is a gentle reminder.",
    "final": "The deadline is close.",
    "manual": "Someone in your group nudged you.",
}


@dataclass
class Delivery:
    channel: str  # in_app | email
    status: str  # queued | sent | skipped | failed
    detail: str


def reminder_message(name: str, mode: str, link: str, kind: str) -> tuple[str, str]:
    """(subject, body). Contains the recipient's name and their own link, nothing about anyone else."""
    subject = "Huddle: your private answer is still needed"
    body = (
        f"Hi {name},\n\n"
        f"Your answer is still needed for your group's {_DECISION.get(mode, 'group')} decision. "
        f"{_KIND_LINE.get(kind, '')}\n\n"
        "It takes about two minutes and it's private: nobody else sees your answer, and the group is "
        "never told who set which limit.\n\n"
        f"Answer here: {link}\n\n"
        "If you weren't expecting this, you can ignore it."
    )
    return subject, body


def email_configured() -> bool:
    return bool(os.environ.get("HUDDLE_SMTP_HOST"))


def send_email(to: str, subject: str, body: str) -> Delivery:
    host = os.environ.get("HUDDLE_SMTP_HOST")
    if not host:
        return Delivery("email", "skipped", "email is not configured")
    msg = EmailMessage()
    msg["From"] = os.environ.get("HUDDLE_SMTP_FROM", "huddle@localhost")
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.environ.get("HUDDLE_SMTP_PORT", "587")), timeout=10) as smtp:
            if os.environ.get("HUDDLE_SMTP_STARTTLS", "1") == "1":
                smtp.starttls(context=ssl.create_default_context())
            if os.environ.get("HUDDLE_SMTP_USER"):
                smtp.login(os.environ["HUDDLE_SMTP_USER"], os.environ.get("HUDDLE_SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        return Delivery("email", "sent", "email sent")
    except Exception as e:  # noqa: BLE001  report the failure class only, never the address
        return Delivery("email", "failed", f"email failed ({type(e).__name__})")


def deliver(*, name: str, email: str | None, mode: str, link: str, kind: str) -> list[Delivery]:
    """Send one reminder over every channel available to this person."""
    out = [Delivery("in_app", "queued", "shown on their page")]
    if email:
        subject, body = reminder_message(name, mode, link, kind)
        out.append(send_email(email, subject, body))
    else:
        out.append(Delivery("email", "skipped", "no email address given"))
    return out


_HOME_LINES = {
    "proposal": "Someone is asking if you can take '{title}'. You can accept or decline it on your page.",
    "plan": "This week's chore plan is ready. Have a look at your part.",
    "due": "'{title}' is due soon.",
    "decision": (
        "A family decision is waiting for your private answer: {title}. "
        "It takes about two minutes and nobody else sees it."
    ),
    "nudge": "A request for '{title}' has been waiting. If you don't answer it will go to someone else.",
}


def home_message(kind: str, name: str, title: str, link: str) -> tuple[str, str]:
    """Reminder text for the household. Names only the recipient; never says who else was asked."""
    subject = "Huddle: your household chores"
    body = f"Hi {name},\n\n" + _HOME_LINES[kind].format(title=title) + f"\n\nOpen your page: {link}\n"
    return subject, body


def deliver_home(*, name: str, email: str | None, kind: str, title: str, link: str) -> list[Delivery]:
    out = [Delivery("in_app", "queued", "shown on their page")]
    if email:
        subject, body = home_message(kind, name, title, link)
        out.append(send_email(email, subject, body))
    else:
        out.append(Delivery("email", "skipped", "no email address given"))
    return out
