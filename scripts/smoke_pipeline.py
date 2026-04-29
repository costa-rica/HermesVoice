#!/usr/bin/env python3
"""
HermesVoice headless pipeline smoke test.

Text → Hermes → TTS → audio file. No WebSocket required.
Validates STT/Hermes/TTS connectivity and basic pipeline function.

Usage:
    cd /path/to/HermesVoice/api
    export HERMES_BASE_URL=http://127.0.0.1:8642/v1
    export HERMES_API_KEY=<API_SERVER_KEY>
    export OPENAI_API_KEY=sk-...

    python ../scripts/smoke_pipeline.py --text "Hello from HermesVoice"
    python ../scripts/smoke_pipeline.py --text "What time is it?" --out /tmp/response.opus
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Allow running from project root or api/ subdirectory
_api_dir = Path(__file__).parent.parent / "api"
if _api_dir.exists():
    sys.path.insert(0, str(_api_dir))

# Minimal env setup before importing settings
for _k, _v in [
    ("NAME_APP", "hermes_voice_smoke"),
    ("RUN_ENVIRONMENT", "development"),
    ("HERMES_VOICE_WEB_PASSWORD", "smoke"),
    ("HERMES_VOICE_API_KEY", "smoke"),
    ("SESSION_SECRET", "smoke-secret-not-used-in-test"),
    ("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", "sk-placeholder")),
    ("HERMES_BASE_URL", os.environ.get("HERMES_BASE_URL", "http://127.0.0.1:8642/v1")),
    ("HERMES_API_KEY", os.environ.get("HERMES_API_KEY", "test")),
]:
    os.environ.setdefault(_k, _v)


async def run(text: str, out_path: Path) -> int:
    from app.services.hermes import stream_hermes_text
    from app.services.tts import synthesize

    conversation_id = f"smoke-{int(time.time())}"

    print(f"prompt        : {text!r}")
    print(f"conversation  : {conversation_id}")
    print(f"output file   : {out_path}")
    print()

    t0 = time.perf_counter()
    chunks: list[str] = []
    first_text_at: float | None = None
    buffer = ""

    print("--- hermes stream ---")
    try:
        async for delta in stream_hermes_text(text, conversation_id):
            if first_text_at is None:
                first_text_at = time.perf_counter() - t0
                print(f"[{first_text_at:.2f}s] first text delta")
            buffer += delta
        if buffer.strip():
            chunks.append(buffer.strip())
    except Exception as exc:
        print(f"Hermes error: {exc}", file=sys.stderr)
        return 1

    hermes_done = time.perf_counter() - t0
    print(f"[{hermes_done:.2f}s] hermes done — {sum(len(c) for c in chunks)} chars")
    print()

    if not chunks:
        print("No text from Hermes — nothing to synthesize", file=sys.stderr)
        return 1

    if not os.environ.get("OPENAI_API_KEY", "").startswith("sk-") or \
            os.environ["OPENAI_API_KEY"] == "sk-placeholder":
        print("OPENAI_API_KEY not set — skipping TTS, writing transcript only")
        out_path.with_suffix(".txt").write_text("\n".join(chunks))
        print(f"transcript written to {out_path.with_suffix('.txt')}")
        return 0

    print("--- TTS ---")
    audio_parts: list[bytes] = []
    for i, chunk in enumerate(chunks):
        t1 = time.perf_counter()
        try:
            audio = await synthesize(chunk)
        except Exception as exc:
            print(f"TTS error on chunk {i}: {exc}", file=sys.stderr)
            return 1
        elapsed = time.perf_counter() - t1
        print(f"chunk {i}: {len(chunk)} chars → {len(audio):,} bytes ({elapsed:.2f}s)")
        audio_parts.append(audio)

    total_audio = b"".join(audio_parts)
    out_path.write_bytes(total_audio)
    total = time.perf_counter() - t0
    print()
    print(f"total time    : {total:.2f} s")
    print(f"first text    : {first_text_at:.2f} s" if first_text_at else "first text    : none")
    print(f"audio bytes   : {len(total_audio):,}")
    print(f"output file   : {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="HermesVoice headless pipeline smoke test")
    parser.add_argument("--text", default="Reply with the single word: pong.")
    parser.add_argument("--out", type=Path, default=Path("/tmp/hv_pipeline_smoke.opus"))
    args = parser.parse_args()

    missing = [v for v in ("HERMES_BASE_URL", "HERMES_API_KEY") if not os.environ.get(v)]
    if missing:
        print(f"error: set {', '.join(missing)}", file=sys.stderr)
        return 2

    return asyncio.run(run(args.text, args.out))


if __name__ == "__main__":
    raise SystemExit(main())
