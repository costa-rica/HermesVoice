"""Tests for latency instrumentation: TurnTimer class and pipeline log events.

Verifies:
- TurnTimer emits structured log lines with stable event names and correlation fields
- run_voice_turn logs latency.turn_started, latency.stt_completed,
  latency.hermes_first_delta, latency.turn_completed, latency.turn_failed
- All latency.* log lines carry cid= and tid= fields
- Timing values are non-negative
- No real sleeps: time is injected via time_fn parameter on TurnTimer
"""
from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import patch

import pytest
from loguru import logger


# ---------------------------------------------------------------------------
# Log capture helper
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def capture_logs(level: str = "INFO"):
    """Capture loguru messages at *level* or above into a list of strings."""
    messages: list[str] = []
    hid = logger.add(messages.append, level=level, format="{message}")
    try:
        yield messages
    finally:
        logger.remove(hid)


# ---------------------------------------------------------------------------
# TurnTimer unit tests
# ---------------------------------------------------------------------------


def test_turn_timer_log_contains_event_name():
    """log() emits a message that starts with the event name."""
    from app.services.latency import TurnTimer

    fake_time = [0.0]
    timer = TurnTimer("cid-1", 1, 1024, "wav", time_fn=lambda: fake_time[0])

    with capture_logs() as msgs:
        timer.log("latency.turn_started")

    assert msgs, "Expected at least one log message"
    assert msgs[-1].startswith("latency.turn_started"), msgs[-1]


def test_turn_timer_log_contains_correlation_fields():
    """log() includes cid=, tid=, elapsed_ms=, audio_bytes=, audio_format=, sample_rate=."""
    from app.services.latency import TurnTimer

    fake_time = [0.0]
    timer = TurnTimer(
        "cid-abc", 7, 2048, "webm/opus", sample_rate=16000,
        time_fn=lambda: fake_time[0],
    )

    with capture_logs() as msgs:
        timer.log("latency.test_event")

    msg = msgs[-1]
    assert "cid=cid-abc" in msg
    assert "tid=7" in msg
    assert "elapsed_ms=" in msg
    assert "audio_bytes=2048" in msg
    assert "audio_format=" in msg
    assert "sample_rate=16000" in msg


def test_turn_timer_elapsed_ms_with_fake_time():
    """elapsed_ms() returns correct value when time is injected."""
    from app.services.latency import TurnTimer

    fake_time = [1000.0]
    timer = TurnTimer("cid-t", 1, 0, "wav", time_fn=lambda: fake_time[0])

    fake_time[0] = 1000.5  # 500 ms later
    assert abs(timer.elapsed_ms() - 500.0) < 0.01


def test_turn_timer_mark_and_delta():
    """mark() + delta_ms() computes elapsed since the mark, not since start."""
    from app.services.latency import TurnTimer

    fake_time = [0.0]
    timer = TurnTimer("cid-d", 2, 0, "wav", time_fn=lambda: fake_time[0])

    fake_time[0] = 0.1
    timer.mark("stt_start")
    fake_time[0] = 0.35

    delta = timer.delta_ms("stt_start")
    assert delta is not None
    assert abs(delta - 250.0) < 0.01


def test_turn_timer_delta_none_for_unknown_mark():
    """delta_ms() returns None for a stage that has not been marked yet."""
    from app.services.latency import TurnTimer

    timer = TurnTimer("cid-n", 1, 0, "wav")
    assert timer.delta_ms("not_marked") is None


def test_turn_timer_extra_kwargs_appear_in_log():
    """Extra kwargs passed to log() are rendered as key=value pairs in the message."""
    from app.services.latency import TurnTimer

    timer = TurnTimer("cid-e", 3, 100, "wav")
    with capture_logs() as msgs:
        timer.log("latency.stt_completed", stt_ms=123.4, transcript_len=42)

    msg = msgs[-1]
    assert "transcript_len=42" in msg
    assert "stt_ms=" in msg


def test_turn_timer_no_sample_rate_omits_field():
    """When sample_rate is None, sample_rate= is not included in the log line."""
    from app.services.latency import TurnTimer

    timer = TurnTimer("cid-z", 1, 0, "wav", sample_rate=None)
    with capture_logs() as msgs:
        timer.log("latency.turn_started")

    msg = msgs[-1]
    assert "sample_rate" not in msg


# ---------------------------------------------------------------------------
# Pipeline latency event integration tests
# ---------------------------------------------------------------------------


async def _fake_stt(audio_bytes: bytes, audio_format: str) -> str:
    return "hello test"


async def _fake_hermes(text: str, cid: str):
    yield "response chunk one"
    yield " and two"


async def _fake_tts(text: str) -> bytes:
    return b"audio:" + text.encode()


def _make_callbacks():
    sent_json: list[dict] = []
    sent_bytes: list[bytes] = []

    async def send_json(data: dict) -> None:
        sent_json.append(data)

    async def send_bytes(data: bytes) -> None:
        sent_bytes.append(data)

    return sent_json, sent_bytes, send_json, send_bytes


@pytest.mark.asyncio
async def test_pipeline_emits_latency_turn_started():
    """run_voice_turn logs latency.turn_started."""
    from app.services.pipeline import run_voice_turn

    _, _, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
        capture_logs() as msgs,
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 512,
            audio_format="wav",
            conversation_id="cid-pipe",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    event_names = [m.split(" |")[0] for m in msgs if m.startswith("latency.")]
    assert "latency.turn_started" in event_names, f"Missing latency.turn_started; got: {event_names}"


@pytest.mark.asyncio
async def test_pipeline_emits_latency_stt_completed():
    """run_voice_turn logs latency.stt_completed with stt_ms and transcript_len."""
    from app.services.pipeline import run_voice_turn

    _, _, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
        capture_logs() as msgs,
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-stt",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    latency_msgs = [m for m in msgs if m.startswith("latency.")]
    event_names = [m.split(" |")[0] for m in latency_msgs]
    assert "latency.stt_completed" in event_names, f"Missing latency.stt_completed; got: {event_names}"

    stt_msg = next(m for m in latency_msgs if m.startswith("latency.stt_completed"))
    assert "stt_ms=" in stt_msg
    assert "transcript_len=" in stt_msg


@pytest.mark.asyncio
async def test_pipeline_emits_latency_hermes_first_delta_once():
    """run_voice_turn logs latency.hermes_first_delta exactly once."""
    from app.services.pipeline import run_voice_turn

    _, _, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
        capture_logs() as msgs,
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-hermes",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=2,
            get_active_turn_id=lambda: 2,
        )

    event_names = [m.split(" |")[0] for m in msgs if m.startswith("latency.")]
    assert "latency.hermes_first_delta" in event_names, f"Missing; got: {event_names}"
    assert event_names.count("latency.hermes_first_delta") == 1, (
        f"hermes_first_delta fired {event_names.count('latency.hermes_first_delta')} times"
    )


@pytest.mark.asyncio
async def test_pipeline_emits_latency_turn_completed_with_stats():
    """run_voice_turn logs latency.turn_completed with total_ms and chunks."""
    from app.services.pipeline import run_voice_turn

    _, _, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
        capture_logs() as msgs,
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-done",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    latency_msgs = [m for m in msgs if m.startswith("latency.")]
    event_names = [m.split(" |")[0] for m in latency_msgs]
    assert "latency.turn_completed" in event_names, f"Missing latency.turn_completed; got: {event_names}"

    done_msg = next(m for m in latency_msgs if m.startswith("latency.turn_completed"))
    assert "total_ms=" in done_msg
    assert "chunks=" in done_msg


@pytest.mark.asyncio
async def test_pipeline_emits_latency_turn_failed_on_exception():
    """run_voice_turn logs latency.turn_failed when the pipeline raises."""
    from app.services.pipeline import run_voice_turn

    _, _, send_json, send_bytes = _make_callbacks()

    async def raising_stt(audio_bytes: bytes, audio_format: str) -> str:
        raise RuntimeError("STT exploded")

    with (
        patch("app.services.pipeline.transcribe", raising_stt),
        patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
        capture_logs("DEBUG") as msgs,
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-fail",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    event_names = [m.split(" |")[0] for m in msgs if m.startswith("latency.")]
    assert "latency.turn_failed" in event_names, f"Missing latency.turn_failed; got: {event_names}"


@pytest.mark.asyncio
async def test_pipeline_latency_events_have_correlation_fields():
    """Every latency.* log line carries cid= and tid= fields."""
    from app.services.pipeline import run_voice_turn

    _, _, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
        capture_logs() as msgs,
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-corr",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=5,
            get_active_turn_id=lambda: 5,
        )

    latency_msgs = [m for m in msgs if m.startswith("latency.")]
    assert latency_msgs, "No latency messages emitted at all"

    for msg in latency_msgs:
        assert "cid=cid-corr" in msg, f"Missing cid= in: {msg}"
        assert "tid=5" in msg, f"Missing tid= in: {msg}"


@pytest.mark.asyncio
async def test_pipeline_latency_events_ordered():
    """Latency events appear in causal order: turn_started -> stt_completed -> hermes_first_delta -> turn_completed."""
    from app.services.pipeline import run_voice_turn

    _, _, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
        capture_logs() as msgs,
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-order",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
        )

    event_names = [m.split(" |")[0] for m in msgs if m.startswith("latency.")]
    checkpoints = [
        "latency.turn_started",
        "latency.stt_completed",
        "latency.hermes_first_delta",
        "latency.turn_completed",
    ]
    indices = {cp: event_names.index(cp) for cp in checkpoints if cp in event_names}

    for i in range(len(checkpoints) - 1):
        a, b = checkpoints[i], checkpoints[i + 1]
        if a in indices and b in indices:
            assert indices[a] < indices[b], (
                f"{a} (pos {indices[a]}) should precede {b} (pos {indices[b]}); order: {event_names}"
            )


@pytest.mark.asyncio
async def test_pipeline_sample_rate_in_latency_logs():
    """When sample_rate is provided, it appears in latency log lines."""
    from app.services.pipeline import run_voice_turn

    _, _, send_json, send_bytes = _make_callbacks()

    with (
        patch("app.services.pipeline.transcribe", _fake_stt),
        patch("app.services.pipeline.stream_hermes_text", _fake_hermes),
        patch("app.services.pipeline.synthesize", _fake_tts),
        capture_logs() as msgs,
    ):
        await run_voice_turn(
            audio_bytes=b"\x00" * 100,
            audio_format="wav",
            conversation_id="cid-sr",
            send_json=send_json,
            send_bytes=send_bytes,
            turn_id=1,
            get_active_turn_id=lambda: 1,
            sample_rate=48000,
        )

    latency_msgs = [m for m in msgs if m.startswith("latency.")]
    assert latency_msgs, "No latency messages emitted"
    assert any("sample_rate=48000" in m for m in latency_msgs), (
        f"sample_rate=48000 not found in any latency message; got: {latency_msgs}"
    )
