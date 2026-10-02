"""Voice routes with real models on the synthetic clips. Skipped when the `voice` extra is absent."""
from pathlib import Path

import httpx
import pytest

from server import api

pytest.importorskip("speechbrain")
pytest.importorskip("soundfile")
AUDIO = Path(__file__).parent / "audio"


async def test_enrol_identify_reject_unknown_and_forget():
    transport = httpx.ASGITransport(app=api.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=120) as c:
        for voice in ("samantha", "daniel", "karen"):
            for clip in sorted((AUDIO / "enrol" / voice).glob("*.wav")):
                r = await c.post("/api/voice/enrol", params={"name": voice}, content=clip.read_bytes())
                assert r.status_code == 200, r.text
        assert (await c.get("/api/voice/profiles")).json()["enrolled"] == ["daniel", "karen", "samantha"]

        for voice in ("samantha", "daniel", "karen"):
            r = (await c.post("/api/voice/identify",
                              content=(AUDIO / "test" / voice / "t2.wav").read_bytes())).json()
            assert r["recognized"] and r["name"] == voice, r
            assert set(r) == {"recognized", "name", "score", "note"}  # no other profile's score

        unknown = (await c.post("/api/voice/identify",
                                content=(AUDIO / "test" / "tessa" / "t2.wav").read_bytes())).json()
        assert unknown["recognized"] is False and unknown["name"] is None

        assert (await c.post("/api/voice/identify", content=b"")).status_code == 400
        await c.delete("/api/voice/profiles/karen")
        assert "karen" not in (await c.get("/api/voice/profiles")).json()["enrolled"]


async def test_transcribe_fallback():
    transport = httpx.ASGITransport(app=api.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=120) as c:
        r = await c.post("/api/voice/transcribe",
                         content=(AUDIO / "test" / "samantha" / "t4.wav").read_bytes())
        assert "close the round" in r.json()["text"].lower()
