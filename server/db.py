"""SQLite persistence (SQLModel). Private answers live only in the `answer` table."""

from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine

from . import config

_engine = None


class Round(SQLModel, table=True):
    id: str = Field(primary_key=True)
    mode: str
    state: str = "collecting"  # collecting -> reminded -> closed
    created_at: NaiveDatetime
    reminder_at: NaiveDatetime
    deadline_at: NaiveDatetime
    need: dict = Field(default_factory=dict, sa_column=Column(JSON))
    result: dict | None = Field(default=None, sa_column=Column(JSON))
    defaults_applied: bool = False


class Participant(SQLModel, table=True):
    id: str = Field(primary_key=True)
    round_id: str = Field(index=True)
    name: str
    channel: str  # voice | link
    is_host: bool = False


class Answer(SQLModel, table=True):
    participant_id: str = Field(primary_key=True)
    round_id: str = Field(index=True)
    data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    is_default: bool = False
    created_at: NaiveDatetime


class Event(SQLModel, table=True):
    """Value-free audit trail: who did what when, never what they answered."""

    id: int | None = Field(default=None, primary_key=True)
    round_id: str = Field(index=True)
    at: NaiveDatetime
    kind: str  # opened | answered | reminded | closed | checked_in
    actor: str | None = None
    detail: str | None = None


class Checkin(SQLModel, table=True):
    """Day-after check-in: one private 1-5 comfort score per participant."""

    participant_id: str = Field(primary_key=True)
    round_id: str = Field(index=True)
    score: int
    created_at: NaiveDatetime


class RoundHousehold(SQLModel, table=True):
    """Links rounds into a household chain. The id is random and only inherited via revisit."""

    round_id: str = Field(primary_key=True)
    household_id: str = Field(index=True)


class HouseholdLoad(SQLModel, table=True):
    """Public assignment history for the fairness record (never private limits)."""

    id: int | None = Field(default=None, primary_key=True)
    household_id: str = Field(index=True)
    round_id: str
    person_name: str
    heavy_hours: int
    total_hours: int


class Contact(SQLModel, table=True):
    """Optional email for reminders. Server-side only: never returned by any API or written to logs."""

    participant_id: str = Field(primary_key=True)
    email: str


class PersonalShare(SQLModel, table=True):
    """One person's own hours per task. Returned ONLY to that person (never in the group result)."""

    id: int | None = Field(default=None, primary_key=True)
    round_id: str = Field(index=True)
    person_name: str
    task_id: str
    label: str
    hours: int


class Home(SQLModel, table=True):
    """A persistent household: its members plan chores week after week."""

    id: str = Field(primary_key=True)
    name: str
    created_at: NaiveDatetime
    auto_plan: bool = True


class Member(SQLModel, table=True):
    id: str = Field(primary_key=True)
    home_id: str = Field(index=True)
    name: str
    is_admin: bool = False


class MemberProfile(SQLModel, table=True):
    """PRIVATE to the member: availability, preferences, skills, exemptions. Owner-only."""

    member_id: str = Field(primary_key=True)
    availability: int = 240  # minutes of chores per week
    prefs: dict = Field(default_factory=dict, sa_column=Column(JSON))
    skills: dict = Field(default_factory=dict, sa_column=Column(JSON))
    learn: list = Field(default_factory=list, sa_column=Column(JSON))
    keywords: list = Field(default_factory=list, sa_column=Column(JSON))
    exempt_weeks: list = Field(default_factory=list, sa_column=Column(JSON))
    updated_at: NaiveDatetime | None = None


class Chore(SQLModel, table=True):
    id: str = Field(primary_key=True)
    home_id: str = Field(index=True)
    title: str
    category: str
    minutes: int  # per occurrence
    cadence: str = "once"  # once | daily | weekly | biweekly | monthly
    due: str | None = None  # ISO date for one-off chores
    heaviness: int = 1
    people_needed: int = 1
    mental: bool = False
    status: str = "active"  # active | done | archived
    created_by: str = ""
    created_at: NaiveDatetime | None = None
    start_week: str = ""
    estimated: bool = False


class Assignment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    home_id: str = Field(index=True)
    chore_id: str = Field(index=True)
    week: str = Field(index=True)  # ISO date of that week's Monday
    slot: int = 0
    member_id: str | None = None
    status: str = "unassigned"  # unassigned | proposed | planned | done
    minutes: int = 0  # for the week
    proposed_to: str | None = None  # PRIVATE: only the proposed member ever sees this
    proposed_at: NaiveDatetime | None = None
    excluded: list = Field(default_factory=list, sa_column=Column(JSON))  # PRIVATE: declines and reasons
    why: str | None = None  # PRIVATE reason code, shown only to the owner
    source: str = "plan"  # plan | adhoc | swap
    completed_at: NaiveDatetime | None = None


class HomePlan(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    home_id: str = Field(index=True)
    week: str = Field(index=True)
    shares: dict = Field(default_factory=dict, sa_column=Column(JSON))  # fair-share fractions (private)
    report: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: NaiveDatetime | None = None


class WeekFelt(SQLModel, table=True):
    """PRIVATE: how a week felt to a member (1 to 5). Lightens their next share if it felt too heavy."""

    id: int | None = Field(default=None, primary_key=True)
    member_id: str = Field(index=True)
    week: str
    score: int


class HomeEvent(SQLModel, table=True):
    """Value-free household audit trail."""

    id: int | None = Field(default=None, primary_key=True)
    home_id: str = Field(index=True)
    at: NaiveDatetime
    kind: str
    actor: str | None = None
    detail: str | None = None


class RoundHome(SQLModel, table=True):
    """A family decision (round) started from a household."""
    round_id: str = Field(primary_key=True)
    home_id: str = Field(index=True)


class ParticipantMember(SQLModel, table=True):
    """Which household member a round participant is, so one identity spans chores and decisions."""
    participant_id: str = Field(primary_key=True)
    member_id: str = Field(index=True)


class Commitment(SQLModel, table=True):
    """One person's private commitment. Title and times are visible only to its owner."""
    id: str = Field(primary_key=True)
    member_id: str = Field(index=True)
    title: str
    circle: str  # family | friends | work | personal
    start: NaiveDatetime
    end: NaiveDatetime
    flexibility: str = "movable"  # fixed | movable | optional
    importance: int = 2
    repeat: str = "none"  # none | daily | weekly
    until: str | None = None  # ISO date a repeating series ends
    skips: list = Field(default_factory=list, sa_column=Column(JSON))  # ISO dates of skipped occurrences
    status: str = "active"  # active | tentative | cancelled
    shared_round_id: str | None = None  # agreed with other people through a find-a-time
    created_at: NaiveDatetime | None = None


class ScheduleRule(SQLModel, table=True):
    """PRIVATE: how this person wants conflicts handled. Owner-only."""
    member_id: str = Field(primary_key=True)
    circle_rank: list = Field(default_factory=list, sa_column=Column(JSON))
    protected: list = Field(default_factory=list, sa_column=Column(JSON))  # [{days, start, end, label}]
    work_start: str | None = None
    work_end: str | None = None
    max_evenings: int | None = None
    buffer_minutes: int = 0
    learned: dict = Field(default_factory=dict, sa_column=Column(JSON))  # how they have chosen before
    updated_at: NaiveDatetime | None = None


class CalendarImport(SQLModel, table=True):
    """Which commitment an imported calendar event became, so importing the same file again updates it.
    The uid is the event's own id from the .ics file. Owner-only, like the commitment it points to."""
    member_id: str = Field(primary_key=True)
    uid: str = Field(primary_key=True)
    commitment_id: str


class CalendarFeed(SQLModel, table=True):
    """PRIVATE: a subscribed calendar address. The url works like a password, so it is never returned by any
    route or written to a log; only whether it is subscribed and how the last refresh went."""
    member_id: str = Field(primary_key=True)
    url: str
    circle: str = "personal"
    last_fetched: NaiveDatetime | None = None
    last_status: str = "waiting"  # waiting | ok | failed
    failures: int = 0


class ReminderPref(SQLModel, table=True):
    """PRIVATE: which reminders this person wants, and when not to send them. Owner-only."""
    member_id: str = Field(primary_key=True)
    kinds: list = Field(default_factory=list, sa_column=Column(JSON))  # starting_soon | digest
    quiet_start: str | None = None  # "HH:MM", in the person's own time
    quiet_end: str | None = None
    utc_offset_minutes: int = 0  # their local time minus the server's clock, because times are floating
    updated_at: NaiveDatetime | None = None


class VoiceProfile(SQLModel, table=True):
    """Biometric stand-in data: enrolment embeddings per household profile (never raw audio)."""

    name: str = Field(primary_key=True)
    embeddings: list = Field(default_factory=list, sa_column=Column(JSON))


def init_db(url: str | None = None):
    """(Re)create the engine. In-memory URLs share one connection so tests can reset cheaply."""
    global _engine
    url = url or config.DB_URL
    kwargs = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in url or url == "sqlite://":
        kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, **kwargs)
    SQLModel.metadata.create_all(_engine)
    return _engine


def get_session() -> Session:
    if _engine is None:
        init_db()
    return Session(_engine, expire_on_commit=False)
