from __future__ import annotations

import pytest
from loguru import logger

pytestmark = pytest.mark.asyncio


class _FakeResponse:
    status_code = 200

    def __init__(self, lines: list[str], delays: list[float] | None = None) -> None:
        self._lines = lines
        self._delays = delays or [0.0] * len(lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aread(self):
        return b""

    async def aiter_lines(self):
        for delay, line in zip(self._delays, self._lines):
            if delay:
                import asyncio
                await asyncio.sleep(delay)
            yield line


class _FakeClient:
    def __init__(self, response: _FakeResponse, *args, **kwargs) -> None:
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, *args, **kwargs):
        return self._response


async def _collect(lines: list[str], monkeypatch, delays: list[float] | None = None):
    from app.services import hermes

    monkeypatch.setattr(hermes.settings, "HERMES_FIRST_EVENT_TIMEOUT", 0.02)
    monkeypatch.setattr(hermes.settings, "HERMES_FIRST_DELTA_TIMEOUT", 0.02)
    monkeypatch.setattr(hermes.settings, "HERMES_INTER_TOKEN_TIMEOUT", 0.02)
    monkeypatch.setattr(hermes.httpx, "AsyncClient", lambda *a, **k: _FakeClient(_FakeResponse(lines, delays), *a, **k))

    return [delta async for delta in hermes.stream_hermes_text("hi", "cid-test")]


async def test_stream_logs_first_event_and_yields_delta(monkeypatch):
    messages: list[str] = []
    hid = logger.add(messages.append, level="INFO", format="{message}")
    try:
        deltas = await _collect([
            "event: response.output_text.delta",
            'data: {"type":"response.output_text.delta","delta":"hello"}',
            "data: [DONE]",
        ], monkeypatch)
    finally:
        logger.remove(hid)

    assert deltas == ["hello"]
    assert any(m.startswith("latency.hermes_first_event") for m in messages)
    assert any("latency.hermes_first_speakable_delta" in m for m in messages)


async def test_stream_first_event_timeout(monkeypatch):
    with pytest.raises(RuntimeError, match="first event timeout"):
        await _collect(["event: response.output_text.delta"], monkeypatch, delays=[0.05])


async def test_stream_first_delta_timeout_after_non_speakable_event(monkeypatch):
    with pytest.raises(RuntimeError, match="first delta timeout"):
        await _collect([
            "event: response.created",
            'data: {"type":"response.created"}',
            "event: response.in_progress",
        ], monkeypatch, delays=[0.0, 0.0, 0.05])


async def test_stream_inter_token_timeout_after_first_delta(monkeypatch):
    with pytest.raises(RuntimeError, match="inter-token timeout"):
        await _collect([
            "event: response.output_text.delta",
            'data: {"type":"response.output_text.delta","delta":"hello"}',
            'data: {"type":"response.output_text.delta","delta":"again"}',
        ], monkeypatch, delays=[0.0, 0.0, 0.05])


# ---------------------------------------------------------------------------
# Payload field tests: source and instructions
# ---------------------------------------------------------------------------


def _make_capturing_client(captured: dict, lines: list[str]):
    """Return a fake httpx.AsyncClient that records the json payload and streams lines."""

    class _CapturingResponse(_FakeResponse):
        def __init__(self):
            super().__init__(lines)

    class _CapturingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url, *, json=None, headers=None, **kwargs):
            captured["payload"] = json
            return _CapturingResponse()

    return _CapturingClient()


async def test_stream_payload_includes_source_and_instructions(monkeypatch):
    """stream_hermes_text adds source and instructions to the Hermes payload when provided."""
    from app.services import hermes

    captured: dict = {}
    monkeypatch.setattr(hermes.settings, "HERMES_FIRST_EVENT_TIMEOUT", 0.02)
    monkeypatch.setattr(hermes.settings, "HERMES_FIRST_DELTA_TIMEOUT", 0.02)
    monkeypatch.setattr(hermes.settings, "HERMES_INTER_TOKEN_TIMEOUT", 0.02)
    monkeypatch.setattr(
        hermes.httpx, "AsyncClient",
        lambda *a, **k: _make_capturing_client(captured, ["data: [DONE]"]),
    )

    _ = [d async for d in hermes.stream_hermes_text(
        "hi", "cid-x", source="voice", instructions="be concise"
    )]

    assert captured["payload"]["source"] == "voice"
    assert captured["payload"]["instructions"] == "be concise"


async def test_stream_payload_omits_source_and_instructions_by_default(monkeypatch):
    """stream_hermes_text omits source and instructions from payload when not provided."""
    from app.services import hermes

    captured: dict = {}
    monkeypatch.setattr(hermes.settings, "HERMES_FIRST_EVENT_TIMEOUT", 0.02)
    monkeypatch.setattr(hermes.settings, "HERMES_FIRST_DELTA_TIMEOUT", 0.02)
    monkeypatch.setattr(hermes.settings, "HERMES_INTER_TOKEN_TIMEOUT", 0.02)
    monkeypatch.setattr(
        hermes.httpx, "AsyncClient",
        lambda *a, **k: _make_capturing_client(captured, ["data: [DONE]"]),
    )

    _ = [d async for d in hermes.stream_hermes_text("hi", "cid-y")]

    assert "source" not in captured["payload"]
    assert "instructions" not in captured["payload"]
