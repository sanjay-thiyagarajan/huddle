"""Calendar files in the schedule service: import, export, a subscribed address, and what stays private."""

import json
from datetime import datetime, timedelta

import httpx
import pytest
from sqlmodel import select

from server import db
from server.engine import home as hm
from server.engine import ical, rounds
from server.engine import schedule_service as ss
from server.engine.rounds import HuddleError

MON = datetime(2026, 10, 5, 9, 0, 0)
NAMES = ["Maya", "Ben", "Chen"]


def cal(*events: str) -> str:
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(events) + "END:VCALENDAR\r\n"


def ev(uid, title, start, end, *extra):
    lines = [f"UID:{uid}", f"SUMMARY:{title}", f"DTSTART:{start}", f"DTEND:{end}", *extra]
    return "BEGIN:VEVENT\r\n" + "".join(f"{ln}\r\n" for ln in lines) + "END:VEVENT\r\n"


DENTIST = ev("d1", "Dentist sentinelcal", "20261008T090000", "20261008T100000")
YOGA = ev("y1", "Yoga", "20261006T180000", "20261006T190000", "RRULE:FREQ=WEEKLY;COUNT=3")


@pytest.fixture
def tok(session):
    out = hm.create_household(session, "Home", [{"name": n} for n in NAMES], MON)
    return {m["name"]: m["token"] for m in out["members"]}


def imp(session, tok, who, text, circle="personal"):
    return ss.import_calendar(session, tok[who], text, circle, MON, "2026-10-05")


def mytime(session, tok, who):
    return ss.get_my_time(session, tok[who], None, MON, "2026-10-05")


# ---- import ------------------------------------------------------------------------------------------------------


def test_import_creates_the_owners_commitments_and_returns_counts_not_titles(session, tok):
    out = imp(session, tok, "Maya", cal(DENTIST, YOGA))
    assert (out["imported"], out["updated"], out["skipped"]) == (2, 0, 0)
    assert "sentinelcal" not in json.dumps(out)
    titles = {i["title"] for i in mytime(session, tok, "Maya")["items"]}
    assert {"Dentist sentinelcal", "Yoga"} <= titles
    assert all(i["flexibility"] == "fixed" for i in mytime(session, tok, "Maya")["items"])


def test_imported_events_are_private_to_their_owner(session, tok):
    imp(session, tok, "Maya", cal(DENTIST))
    for other in ("Ben", "Chen"):
        view = json.dumps(mytime(session, tok, other)) + json.dumps(hm.get_state(session, tok[other], MON))
        assert "sentinelcal" not in view
        assert mytime(session, tok, other)["items"] == []


def test_importing_the_same_file_again_updates_instead_of_duplicating(session, tok):
    imp(session, tok, "Maya", cal(DENTIST))
    again = imp(session, tok, "Maya", cal(DENTIST))
    assert (again["imported"], again["unchanged"]) == (0, 1)
    moved = ev("d1", "Dentist sentinelcal", "20261008T110000", "20261008T120000")
    third = imp(session, tok, "Maya", cal(moved))
    assert (third["imported"], third["updated"]) == (0, 1)
    items = [i for i in mytime(session, tok, "Maya")["items"] if "Dentist" in i["title"]]
    assert len(items) == 1 and items[0]["start"] == "2026-10-08T11:00"


def test_a_commitment_the_person_removed_does_not_come_back(session, tok):
    imp(session, tok, "Maya", cal(DENTIST))
    cid = mytime(session, tok, "Maya")["items"][0]["id"]
    ss.update_commitment(session, tok["Maya"], cid, {"status": "cancelled"}, None, MON)
    out = imp(session, tok, "Maya", cal(DENTIST))
    assert out["imported"] == 0 and out["skipped"] == 1
    assert mytime(session, tok, "Maya")["items"] == []


def test_the_circle_is_used_and_validated(session, tok):
    imp(session, tok, "Maya", cal(DENTIST), "family")
    assert mytime(session, tok, "Maya")["items"][0]["circle"] == "family"
    with pytest.raises(HuddleError) as e:
        imp(session, tok, "Maya", cal(DENTIST), "work friends")
    assert e.value.code == "bad_commitment"


def test_clashes_with_existing_commitments_are_counted(session, tok):
    ss.add_commitment(
        session, tok["Maya"], {"title": "Lunch", "circle": "friends", "start": "2026-10-08T09:30", "minutes": 60},
        {"choice": "keep_both"}, MON, "2026-10-05",
    )
    out = imp(session, tok, "Maya", cal(DENTIST))
    assert out["clashes"] == 1 and any("clash" in n for n in out["notes"])


def test_unusable_events_are_skipped_and_the_rest_still_import(session, tok):
    monthly = ev("m", "Rent", "20261008T090000", "20261008T093000", "RRULE:FREQ=MONTHLY")
    out = imp(session, tok, "Maya", cal(monthly, DENTIST))
    assert (out["imported"], out["skipped"]) == (1, 1)


def test_a_bad_file_is_an_error_and_changes_nothing(session, tok):
    with pytest.raises(HuddleError) as e:
        imp(session, tok, "Maya", "not a calendar")
    assert e.value.code == "bad_calendar"
    assert mytime(session, tok, "Maya")["items"] == []


def test_a_bad_token_cannot_import(session, tok):
    with pytest.raises(HuddleError):
        ss.import_calendar(session, "nope", cal(DENTIST), "personal", MON)


# ---- export ------------------------------------------------------------------------------------------------------


def test_export_contains_only_the_callers_commitments(session, tok):
    imp(session, tok, "Maya", cal(DENTIST))
    ss.add_commitment(session, tok["Ben"], {"title": "Bensecret", "circle": "personal", "start": "2026-10-09T10:00", "minutes": 60}, None, MON, "2026-10-05")
    out = ss.export_calendar(session, tok["Maya"], "my_time", MON, "2026-10-05")
    assert out["count"] == 1 and "Dentist sentinelcal" in out["ics"] and "Bensecret" not in out["ics"]
    assert out["filename"].endswith(".ics")
    assert "Maya" not in json.dumps(ss.export_calendar(session, tok["Ben"], "my_time", MON, "2026-10-05")["ics"])


def test_exporting_an_imported_event_keeps_its_original_id_so_it_is_not_duplicated(session, tok):
    imp(session, tok, "Maya", cal(DENTIST))
    ics = ss.export_calendar(session, tok["Maya"], "my_time", MON, "2026-10-05")["ics"]
    assert "UID:d1" in ics
    # and a file Huddle exported reads back onto the same commitments
    again = imp(session, tok, "Maya", ics)
    assert again["imported"] == 0


def test_export_skips_the_past_and_tentative_items(session, tok):
    old = ev("old", "Old", "20260901T090000", "20260901T100000")
    imp(session, tok, "Maya", cal(old, DENTIST))
    assert ss.export_calendar(session, tok["Maya"], "my_time", MON, "2026-10-05")["count"] == 1


def test_export_chore_plan_is_all_day_and_only_the_callers_chores(session, tok):
    hm.add_chore_any(session, tok["Maya"], {"title": "Take out bins", "category": "yard", "minutes": 20, "cadence": "weekly", "due": "2026-10-08"}, None, MON)
    hm.plan_week(session, tok["Maya"], "2026-10-05", False, MON)
    texts = {n: ss.export_calendar(session, tok[n], "chore_plan", MON, "2026-10-05") for n in NAMES}
    assert sum(t["count"] for t in texts.values()) == 1
    mine = next(t for t in texts.values() if t["count"])
    assert "Chore: Take out bins" in mine["ics"] and "VALUE=DATE:20261008" in mine["ics"]
    assert ical.parse(mine["ics"]).events == []  # all-day entries are not read back as commitments


def test_export_rejects_an_unknown_kind(session, tok):
    with pytest.raises(HuddleError) as e:
        ss.export_calendar(session, tok["Maya"], "everything", MON)
    assert e.value.code == "bad_export"


# ---- a subscribed address ----------------------------------------------------------------------------------------


def fake(text):
    calls = []

    def fetch(url):
        calls.append(url)
        return text

    fetch.calls = calls
    return fetch


def test_subscribe_reads_now_and_never_returns_the_address(session, tok):
    f = fake(cal(DENTIST))
    url = "https://calendar.example.com/ical/secrettoken123/public/basic.ics"
    out = ss.subscribe_calendar(session, tok["Maya"], url, "work", MON, "2026-10-05", f)
    assert out["subscribed"] and out["imported"] == 1
    assert "secrettoken123" not in json.dumps(out) + json.dumps(mytime(session, tok, "Maya"))
    assert mytime(session, tok, "Maya")["feed"] == {
        "subscribed": True, "circle": "work", "last_status": "ok", "last_fetched": "2026-10-05T09:00",
    }
    assert mytime(session, tok, "Ben")["feed"] == {"subscribed": False}


def test_webcal_addresses_are_read_as_https(session, tok):
    f = fake(cal(DENTIST))
    ss.subscribe_calendar(session, tok["Maya"], "webcal://calendar.example.com/a.ics", "personal", MON, None, f)
    assert f.calls == ["https://calendar.example.com/a.ics"]


@pytest.mark.parametrize(
    "url",
    ["http://calendar.example.com/a.ics", "file:///etc/passwd", "https://user:pw@calendar.example.com/a.ics",
     "https://calendar.example.com:8443/a.ics", "ftp://x/y", "https://"],
)
def test_addresses_that_are_not_plain_https_are_refused(session, tok, url):
    with pytest.raises(HuddleError) as e:
        ss.subscribe_calendar(session, tok["Maya"], url, "personal", MON, None, fake(cal(DENTIST)))
    assert e.value.code == "bad_feed"


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.9", "169.254.169.254", "172.16.0.1", "::1", "::ffff:127.0.0.1", "100.64.0.1"])
def test_hosts_that_resolve_inside_a_network_are_refused(ip):
    def resolve(host, port):
        return [(0, 0, 0, "", (ip, port))]

    with pytest.raises(HuddleError) as e:
        ss._check_host("calendar.example.com", resolve)
    assert e.value.code == "bad_feed"


def test_a_public_host_passes_the_address_check():
    ss._check_host("calendar.example.com", lambda h, p: [(0, 0, 0, "", ("93.184.216.34", p))])


def test_a_host_that_cannot_be_found_is_a_calm_error():
    def resolve(host, port):
        raise OSError("no such host")

    with pytest.raises(HuddleError) as e:
        ss._check_host("calendar.example.com", resolve)
    assert e.value.code == "feed_failed"


def test_fetch_enforces_size_status_and_same_host_redirects(monkeypatch):
    monkeypatch.setattr(ss, "_check_host", lambda host, resolve=None: None)

    def serve(handler):
        real = httpx.Client

        class Stream:
            def __init__(self, method, url, **kw):
                self.r = real(transport=httpx.MockTransport(handler)).send(
                    httpx.Request(method, url), stream=True
                )

            def __enter__(self):
                return self.r

            def __exit__(self, *a):
                self.r.close()

        monkeypatch.setattr(ss.httpx, "stream", Stream)

    serve(lambda req: httpx.Response(200, text="BEGIN:VCALENDAR\nEND:VCALENDAR"))
    assert ss._fetch_feed("https://calendar.example.com/a.ics").startswith("BEGIN:VCALENDAR")

    serve(lambda req: httpx.Response(404))
    with pytest.raises(HuddleError, match="404"):
        ss._fetch_feed("https://calendar.example.com/a.ics")

    serve(lambda req: httpx.Response(200, content=b"x" * (ical.MAX_BYTES + 1)))
    with pytest.raises(HuddleError, match="too large"):
        ss._fetch_feed("https://calendar.example.com/a.ics")

    serve(lambda req: httpx.Response(302, headers={"location": "https://elsewhere.example.net/a.ics"}))
    with pytest.raises(HuddleError, match="redirects somewhere else"):
        ss._fetch_feed("https://calendar.example.com/a.ics")

    hops = []

    def same_host(req):
        hops.append(str(req.url))
        if req.url.path == "/a.ics":
            return httpx.Response(302, headers={"location": "/b.ics"})
        return httpx.Response(200, text="BEGIN:VCALENDAR\nEND:VCALENDAR")

    serve(same_host)
    assert ss._fetch_feed("https://calendar.example.com/a.ics")
    assert hops == ["https://calendar.example.com/a.ics", "https://calendar.example.com/b.ics"]


def test_a_network_error_never_names_the_address(monkeypatch):
    monkeypatch.setattr(ss, "_check_host", lambda host, resolve=None: None)

    def boom(*a, **k):
        raise httpx.ConnectError("could not reach https://calendar.example.com/ical/secrettoken123")

    monkeypatch.setattr(ss.httpx, "stream", boom)
    with pytest.raises(HuddleError) as e:
        ss._fetch_feed("https://calendar.example.com/ical/secrettoken123/a.ics")
    assert "secrettoken123" not in e.value.message and "ConnectError" in e.value.message


def test_a_failed_first_read_subscribes_nothing(session, tok):
    def boom(url):
        raise HuddleError("feed_failed", "nope")

    with pytest.raises(HuddleError):
        ss.subscribe_calendar(session, tok["Maya"], "https://calendar.example.com/a.ics", "personal", MON, None, boom)
    assert mytime(session, tok, "Maya")["feed"] == {"subscribed": False}


def test_no_url_unsubscribes_and_keeps_what_was_read(session, tok):
    f = fake(cal(DENTIST))
    ss.subscribe_calendar(session, tok["Maya"], "https://calendar.example.com/a.ics", "personal", MON, None, f)
    assert ss.subscribe_calendar(session, tok["Maya"], None, "personal", MON) == {"subscribed": False}
    assert mytime(session, tok, "Maya")["feed"] == {"subscribed": False}
    assert len(mytime(session, tok, "Maya")["items"]) == 1


def test_tick_refreshes_at_most_hourly_and_picks_up_changes(session, tok):
    f = fake(cal(DENTIST))
    ss.subscribe_calendar(session, tok["Maya"], "https://calendar.example.com/a.ics", "personal", MON, None, f)
    assert ss.tick(session, MON + timedelta(minutes=30), fetch=f) == []
    assert len(f.calls) == 1
    f2 = fake(cal(ev("d1", "Dentist sentinelcal", "20261008T110000", "20261008T120000"), YOGA))
    assert ss.tick(session, MON + timedelta(hours=1), fetch=f2) == [("feed", "ok")]
    items = {i["title"]: i for i in mytime(session, tok, "Maya")["items"]}
    assert items["Dentist sentinelcal"]["start"] == "2026-10-08T11:00" and "Yoga" in items


def test_tick_stops_after_repeated_failures_and_reports_failed(session, tok):
    ss.subscribe_calendar(session, tok["Maya"], "https://calendar.example.com/a.ics", "personal", MON, None, fake(cal(DENTIST)))

    def boom(url):
        raise HuddleError("feed_failed", "nope")

    t = MON
    for _ in range(ss.FEED_GIVE_UP_AFTER):
        t += timedelta(hours=1, minutes=1)
        assert ss.tick(session, t, fetch=boom) == [("feed", "failed")]
    assert mytime(session, tok, "Maya")["feed"]["last_status"] == "failed"
    assert ss.tick(session, t + timedelta(hours=2), fetch=boom) == []  # gave up


def test_a_feed_whose_member_is_gone_does_not_crash_the_tick(session, tok):
    ss.subscribe_calendar(session, tok["Maya"], "https://calendar.example.com/a.ics", "personal", MON, None, fake(cal(DENTIST)))
    feed = session.get(db.CalendarFeed, session.get(db.Member, rounds._parse_token(tok["Maya"], MON)[1:]).id)
    session.delete(session.get(db.Member, feed.member_id))
    session.commit()
    assert ss.tick(session, MON + timedelta(hours=2), fetch=fake(cal(DENTIST))) == [("feed", "failed")]


# ---- reasons and reading a subscribed address again now ----------------------------------------------------------


def test_the_import_note_names_why_an_event_was_skipped(session, tok):
    too_long = ev("long", "Hackathon work", "20261004T223000", "20261005T233000")  # ends the next day: 25 hours
    out = imp(session, tok, "Maya", cal(too_long, DENTIST))
    assert (out["imported"], out["skipped"], out["skipped_reasons"]) == (1, 1, {"too_long": 1})
    assert any("1 longer than 14 hours" in n for n in out["notes"])
    assert "Hackathon" not in json.dumps(out)  # reasons, never titles


def test_something_removed_here_is_reported_as_such(session, tok):
    imp(session, tok, "Maya", cal(DENTIST))
    cid = mytime(session, tok, "Maya")["items"][0]["id"]
    ss.update_commitment(session, tok["Maya"], cid, {"status": "cancelled"}, None, MON)
    out = imp(session, tok, "Maya", cal(DENTIST))
    assert out["skipped_reasons"] == {"removed_here": 1}


URL = "https://calendar.example.com/a.ics"


def follow(session, tok, text):
    return ss.subscribe_calendar(session, tok["Maya"], URL, "personal", MON, None, fake(text))


def test_read_again_now_picks_up_a_change_without_waiting_an_hour(session, tok):
    long = ev("h", "Hackathon work", "20261004T223000", "20261005T233000")
    assert follow(session, tok, cal(long))["skipped_reasons"] == {"too_long": 1}
    fixed = ev("h", "Hackathon work", "20261004T223000", "20261004T233000")
    soon = MON + timedelta(minutes=5)  # well inside the hourly pause
    out = ss.subscribe_calendar(session, tok["Maya"], None, "personal", soon, None, fake(cal(fixed)), True)
    assert out["subscribed"] and out["imported"] == 1 and out["skipped"] == 0
    assert any(i["title"] == "Hackathon work" for i in ss.get_my_time(session, tok["Maya"], "2026-09-28", soon, "2026-10-04")["items"])
    assert ss.get_my_time(session, tok["Maya"], None, soon, "2026-10-05")["feed"]["last_fetched"] == "2026-10-05T09:05"


def test_read_again_needs_a_subscription_and_never_returns_the_address(session, tok):
    with pytest.raises(HuddleError) as e:
        ss.subscribe_calendar(session, tok["Maya"], None, "personal", MON, None, fake(cal(DENTIST)), True)
    assert e.value.code == "no_feed"
    follow(session, tok, cal(DENTIST))
    out = ss.subscribe_calendar(session, tok["Maya"], None, "personal", MON, None, fake(cal(DENTIST)), True)
    assert out["unchanged"] == 1 and "example.com" not in json.dumps(out)


def feed_row(session):
    return session.exec(select(db.CalendarFeed)).one()


def test_a_failed_read_again_is_recorded_and_a_good_one_clears_it(session, tok):
    follow(session, tok, cal(DENTIST))

    def boom(url):
        raise HuddleError("feed_failed", "nope")

    for n in range(1, ss.FEED_GIVE_UP_AFTER + 1):  # the agent would now have given up on its own...
        with pytest.raises(HuddleError):
            ss.subscribe_calendar(session, tok["Maya"], None, "personal", MON, None, boom, True)
        assert feed_row(session).failures == n
    assert ss.tick(session, MON + timedelta(hours=3), fetch=fake(cal(DENTIST))) == []
    ss.subscribe_calendar(session, tok["Maya"], None, "personal", MON, None, fake(cal(DENTIST)), True)  # ...but you can
    assert ss.tick(session, MON + timedelta(hours=3), fetch=fake(cal(DENTIST))) == [("feed", "ok")]
