"""Runtime configuration. HUDDLE_MODE=mock (default) needs no AWS credentials."""
import os

MODE = os.environ.get("HUDDLE_MODE", "mock")
DB_URL = os.environ.get("HUDDLE_DB_URL", "sqlite:///huddle.db")
# Signs round tokens. Override in any shared deployment.
SECRET = os.environ.get("HUDDLE_SECRET", "dev-only-change-me")
# Where links in reminder emails point (the address people can reach this server at).
PUBLIC_URL = os.environ.get("HUDDLE_PUBLIC_URL", "http://localhost:8000").rstrip("/")
# How often the background scheduler looks for due reminders and expired deadlines.
TICK_SECONDS = float(os.environ.get("HUDDLE_TICK_SECONDS", "15"))
