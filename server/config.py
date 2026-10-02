"""Runtime configuration. HUDDLE_MODE=mock (default) needs no AWS credentials."""
import os

MODE = os.environ.get("HUDDLE_MODE", "mock")
DB_URL = os.environ.get("HUDDLE_DB_URL", "sqlite:///huddle.db")
# Signs round tokens. Override in any shared deployment.
SECRET = os.environ.get("HUDDLE_SECRET", "dev-only-change-me")
