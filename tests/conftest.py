import socket
import threading
import time

import pytest
import uvicorn

from server import db


@pytest.fixture(autouse=True)
def fresh_db():
    db.init_db("sqlite://")
    yield


@pytest.fixture
def session(fresh_db):
    with db.get_session() as s:
        yield s


@pytest.fixture(scope="session")
def live_server():
    """Real uvicorn on a free port, so MCP tests go over actual HTTP.

    Session-scoped: a FastMCP session manager can only be run once per process.
    """
    from server.api import app

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
