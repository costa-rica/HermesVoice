from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from loguru import logger


class TurnTimer:
    """Small per-turn latency logger with injectable monotonic clock for tests.

    ``utterance_buffer_ms`` is currently the server-observed gap between the
    websocket ``start_utterance`` and ``end_of_utterance`` control frames. It
    is useful as a control-flow timing hint but is not a true user speech
    duration; browsers may bulk-send audio shortly before ``end_of_utterance``.
    The value is None when the caller does not have a control-frame timestamp.
    """

    def __init__(
        self,
        conversation_id: str,
        turn_id: int,
        audio_bytes: int,
        audio_format: str | None,
        *,
        sample_rate: int | None = None,
        utterance_buffer_ms: float | None = None,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.turn_id = turn_id
        self.audio_bytes = audio_bytes
        self.audio_format = audio_format or "unknown"
        self.sample_rate = sample_rate
        self.utterance_buffer_ms = utterance_buffer_ms
        self._time_fn = time_fn or time.monotonic
        self.started_at = self._time_fn()
        self._marks: dict[str, float] = {}

    def elapsed_ms(self) -> float:
        return self._ms_since(self.started_at)

    def mark(self, name: str) -> None:
        self._marks[name] = self._time_fn()

    def delta_ms(self, name: str) -> float | None:
        marked_at = self._marks.get(name)
        if marked_at is None:
            return None
        return self._ms_since(marked_at)

    def log(self, event: str, **fields: Any) -> None:
        parts: list[str] = [
            f"cid={self.conversation_id}",
            f"tid={self.turn_id}",
            f"elapsed_ms={self.elapsed_ms():.1f}",
            f"audio_bytes={self.audio_bytes}",
            f"audio_format={self.audio_format}",
        ]
        if self.sample_rate is not None:
            parts.append(f"sample_rate={self.sample_rate}")
        if self.utterance_buffer_ms is not None:
            parts.append(f"utterance_buffer_ms={self.utterance_buffer_ms:.1f}")

        for key, value in fields.items():
            if value is None:
                continue
            parts.append(f"{key}={self._format_value(value)}")

        logger.info(f"{event} | " + " ".join(parts))

    def _ms_since(self, started_at: float) -> float:
        return max(0.0, (self._time_fn() - started_at) * 1000.0)

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.1f}"
        text = str(value)
        return text.replace("\n", " ").replace("\r", " ")
