"""Real reminders: scheduler timing, who gets one, honest delivery results, privacy of contacts and text,
and an actual SMTP exchange against a local mail sink."""
import asyncio
import json
import socket
from datetime import datetime, timedelta

import pytest
from aiosmtpd.controller import Controller

from server import api, config, notify
from server.db import Round, get_session
from server.engine import rounds

T0 = datetime(2026, 10, 10, 9, 0, 0)
PEOPLE = [{"name": "Maya"}, {"name": "Ben", "email": "ben.sentinel@example.test"},
          {"name": "Chen", "channel": "link"}]


class Recorder:
    """Stands in for notify.deliver: records each call and reports the channels honestly."""
    def __init__(self):
        self.calls = []

    def __call__(self, **kw):
        self.calls.append(kw)
        email = ([notify.Delivery("email", "sent", "email sent")] if kw["email"]
                 else [notify.Delivery("email", "skipped", "no email address given")])
        return [notify.Delivery("in_app", "queued", "shown on their page"), *email]


def make(session, answered=()):
    r = rounds.create_round(session, "care", PEOPLE, 3600, now=T0)
    tok = {p["name"]: p["token"] for p in r["participants"]}
    for name in answered:
        rounds.submit_answer(session, tok[name], {"consent": True, "hours_per_week": 5,
                                                  "dollars_per_month": 100, "dealbreakers": []}, T0)
    return tok


def test_first_reminder_goes_once_to_pending_people_only(session):
    tok = make(session, answered=["Maya"])
    rec = Recorder()
    assert rounds.tick(session, T0 + timedelta(minutes=10), rec) == []          # too early
    sent = rounds.tick(session, T0 + timedelta(minutes=31), rec)                # half-way: 30 minutes
    assert sorted((n, k) for _, n, k in sent) == [("Ben", "first"), ("Chen", "first")]
    assert rounds.tick(session, T0 + timedelta(minutes=35), rec) == []          # never twice
    assert [c["name"] for c in rec.calls] == ["Ben", "Chen"]                    # Maya had answered
    events = [e for e in rounds.status(session, tok["Maya"], T0 + timedelta(minutes=35))["events"]
              if e["kind"] == "reminder_sent"]
    assert [(e["actor"], e["detail"]) for e in events] == [
        ("Ben", "first: in_app queued, email sent"), ("Chen", "first: in_app queued, email skipped")]


def test_final_reminder_near_the_deadline_and_not_to_people_who_answered_meanwhile(session):
    tok = make(session)
    rec = Recorder()
    rounds.tick(session, T0 + timedelta(minutes=31), rec)
    rounds.submit_answer(session, tok["Ben"], {"consent": True, "hours_per_week": 4,
                                               "dollars_per_month": 50, "dealbreakers": []},
                         T0 + timedelta(minutes=40))
    sent = rounds.tick(session, T0 + timedelta(minutes=55), rec)  # final_at = deadline - 6 min
    assert sorted((n, k) for _, n, k in sent) == [("Chen", "final"), ("Maya", "final")]
    assert rounds.tick(session, T0 + timedelta(minutes=58), rec) == []


def test_tick_closes_a_round_at_its_deadline_with_nobody_polling(session):
    make(session)
    rounds.tick(session, T0 + timedelta(hours=1, seconds=2), Recorder())
    rnd = session.exec(__import__("sqlmodel").select(Round)).first()
    assert rnd.state == "closed" and rnd.defaults_applied is True
    rec = Recorder()
    assert rounds.tick(session, T0 + timedelta(hours=2), rec) == [] and rec.calls == []  # no reminders after


def test_my_reminder_shows_only_to_the_person_who_still_owes_an_answer(session):
    tok = make(session)
    rounds.tick(session, T0 + timedelta(minutes=31), Recorder())
    later = T0 + timedelta(minutes=32)
    chen = rounds.status(session, tok["Chen"], later)["reminder"]
    assert chen["kind"] == "first"
    rounds.submit_answer(session, tok["Chen"], {"consent": True, "hours_per_week": 1,
                                                "dollars_per_month": 1, "dealbreakers": []}, later)
    assert rounds.status(session, tok["Chen"], later)["reminder"] is None  # answered: banner goes away


def test_manual_nudge_is_host_only_reports_honestly_and_is_rate_limited(session):
    tok = make(session, answered=["Maya"])
    rec = Recorder()
    with pytest.raises(rounds.HuddleError) as e:
        rounds.nudge_pending(session, tok["Ben"], T0, rec)
    assert e.value.code == "host_only"
    out = rounds.nudge_pending(session, tok["Maya"], T0 + timedelta(minutes=1), rec)
    assert out["pending"] == ["Ben", "Chen"] and "Reminded Ben, Chen" in out["message"]
    by_channel = {(d["name"], d["channel"]): d["status"] for d in out["deliveries"]}
    assert by_channel[("Ben", "email")] == "sent" and by_channel[("Chen", "email")] == "skipped"
    again = rounds.nudge_pending(session, tok["Maya"], T0 + timedelta(minutes=5), rec)
    assert {d["status"] for d in again["deliveries"]} == {"skipped"}
    assert "Nobody needed a new reminder" in again["message"]
    third = rounds.nudge_pending(session, tok["Maya"], T0 + timedelta(minutes=12), rec)
    assert "Reminded Ben, Chen" in third["message"]


def test_nudge_when_nobody_is_pending_says_so(session):
    tok = make(session, answered=["Maya", "Ben", "Chen"])
    out = rounds.nudge_pending(session, tok["Maya"], T0, Recorder())
    assert out["pending"] == [] and out["message"] == "Everyone answered."


# ---- contacts and message text are private -----------------------------------------------------------

def test_email_is_validated_stored_privately_and_never_returned(session):
    with pytest.raises(rounds.HuddleError) as e:
        bad = [{"name": "A", "email": "not-an-email"}, {"name": "B"}]
        rounds.create_round(session, "care", bad, 3600, now=T0)
    assert e.value.code == "bad_participants"

    r = rounds.create_round(session, "care", PEOPLE, 3600, now=T0)
    tok = {p["name"]: p["token"] for p in r["participants"]}
    bodies = [json.dumps(r)]
    for t in tok.values():
        for fn in (rounds.status, rounds.my_answers, rounds.get_result, rounds.household_history):
            bodies.append(json.dumps(fn(session, t, T0), default=str))
    bodies.append(json.dumps(rounds.nudge_pending(session, tok["Maya"], T0, Recorder())))
    assert not any("ben.sentinel@example.test" in b for b in bodies)


def test_reminder_text_names_only_the_recipient_and_carries_no_values():
    subject, body = notify.reminder_message("Ben", "care", "http://x/r/TOKEN", "manual")
    assert "Hi Ben" in body and "http://x/r/TOKEN" in body and "Maya" not in body and "Chen" not in body
    assert not any(w in body.lower() for w in ("answered", "hasn't", "waiting on", "pending"))
    assert "nobody else sees your answer" in body and "ignore" in body
    assert "private answer" in subject
    assert not any(ch.isdigit() for ch in body.replace("http://x/r/TOKEN", ""))  # no numbers at all


# ---- real SMTP delivery (local sink) ------------------------------------------------------------------

class Sink:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):  # noqa: N802  (aiosmtpd hook name)
        self.messages.append(envelope)
        return "250 OK"


@pytest.fixture
def smtp_sink(monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    sink = Sink()
    controller = Controller(sink, hostname="127.0.0.1", port=port)
    controller.start()
    monkeypatch.setenv("HUDDLE_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("HUDDLE_SMTP_PORT", str(port))
    monkeypatch.setenv("HUDDLE_SMTP_STARTTLS", "0")
    monkeypatch.setattr(config, "PUBLIC_URL", "http://huddle.test")
    yield sink
    controller.stop()


def test_scheduler_tick_really_sends_an_email_over_smtp(session, smtp_sink):
    tok = make(session)
    sent = rounds.tick(session, T0 + timedelta(minutes=31))  # default deliver: real SMTP to the sink
    assert ("Ben", "first") in {(n, k) for _, n, k in sent}
    assert len(smtp_sink.messages) == 1  # only Ben gave an address
    msg = smtp_sink.messages[0]
    assert msg.rcpt_tos == ["ben.sentinel@example.test"]
    text = msg.content.decode() if isinstance(msg.content, bytes) else str(msg.content)
    assert "Subject: Huddle: your private answer is still needed" in text
    assert "Hi Ben" in text and "Maya" not in text and "Chen" not in text
    link = next(w for w in text.split() if w.startswith("http://huddle.test/r/"))
    # The link in the email is Ben's own, working token
    assert rounds.status(session, link.rsplit("/r/", 1)[1], T0 + timedelta(minutes=32))["me"]["name"] == "Ben"
    assert tok["Ben"].split(".")[0] in link  # same participant id as the token issued at the start


def test_smtp_failure_is_reported_as_failed_and_never_leaks_the_address(session, monkeypatch):
    with socket.socket() as s:  # a port nothing listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("HUDDLE_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("HUDDLE_SMTP_PORT", str(port))
    monkeypatch.setenv("HUDDLE_SMTP_STARTTLS", "0")
    tok = make(session)
    rounds.tick(session, T0 + timedelta(minutes=31))
    events = rounds.status(session, tok["Maya"], T0 + timedelta(minutes=32))["events"]
    ben = next(e for e in events if e["kind"] == "reminder_sent" and e["actor"] == "Ben")
    assert ben["detail"] == "first: in_app queued, email failed"
    assert "ben.sentinel" not in json.dumps(events)
    failed = notify.send_email("someone@example.test", "s", "b")  # names the error class only
    assert failed.status == "failed" and failed.detail.startswith("email failed (")
    assert "someone" not in failed.detail


def test_email_not_configured_is_reported_as_skipped_not_sent(session, monkeypatch):
    monkeypatch.delenv("HUDDLE_SMTP_HOST", raising=False)
    tok = make(session)
    rounds.tick(session, T0 + timedelta(minutes=31))
    events = rounds.status(session, tok["Maya"], T0 + timedelta(minutes=32))["events"]
    ben = next(e for e in events if e["kind"] == "reminder_sent" and e["actor"] == "Ben")
    assert ben["detail"] == "first: in_app queued, email skipped"
    skipped = notify.send_email("x@y.test", "s", "b")
    assert skipped == notify.Delivery("email", "skipped", "email is not configured")


# ---- the background scheduler loop --------------------------------------------------------------------

async def test_scheduler_loop_closes_overdue_rounds_by_itself(session, monkeypatch):
    now = rounds.now_utc()
    rounds.create_round(session, "care", PEOPLE, 3600, now=now - timedelta(hours=2))  # long overdue
    monkeypatch.setattr(config, "TICK_SECONDS", 0.05)
    task = asyncio.create_task(api._scheduler())
    try:
        for _ in range(60):
            await asyncio.sleep(0.05)
            with get_session() as s:
                if s.exec(__import__("sqlmodel").select(Round)).first().state == "closed":
                    break
        else:
            raise AssertionError("scheduler never closed the overdue round")
    finally:
        task.cancel()
