#!/usr/bin/env python3
"""
Hermes Responses-API streaming smoke test.

Sends a single prompt to Hermes' OpenAI-compatible /v1/responses endpoint
with stream=true and prints every event type that comes back, plus a short
sample of each event's payload. Used to nail down the exact event taxonomy
so the V1 pipeline can implement `is_speakable_event` correctly and decide
which non-speakable events are worth surfacing as tool-progress UX.

By default the prompt forces a tool call so we observe the tool-progress
event shape, not just plain text deltas.

Usage:
    export HERMES_BASE_URL=http://127.0.0.1:8642/v1
    export HERMES_API_KEY=<API_SERVER_KEY from ~/.hermes/.env>

    python scripts/smoke_responses_stream.py
    python scripts/smoke_responses_stream.py --prompt "ping" --no-tools
    python scripts/smoke_responses_stream.py --raw

Run this on avatar08 (where Hermes listens on loopback). To run from the
MacBook, SSH-forward the port first:
    ssh -N -L 8642:127.0.0.1:8642 avatar08

Setup (one-time):
    python3 -m venv .venv && source .venv/bin/activate
    pip install httpx
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter

import httpx


TOOL_PROMPT = (
    "Use your terminal tool to run `echo hermesvoice-smoke` and tell me "
    "exactly what it printed. Keep your reply to one sentence."
)
PLAIN_PROMPT = "Reply with the single word: pong."


def stream_events(base_url: str, api_key: str, prompt: str, model: str, conversation: str):
    payload = {
        "model": model,
        "input": prompt,
        "conversation": conversation,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    url = base_url.rstrip("/") + "/responses"

    with httpx.stream("POST", url, json=payload, headers=headers, timeout=600.0) as resp:
        resp.raise_for_status()
        event_name: str | None = None
        for line in resp.iter_lines():
            if not line:
                event_name = None
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
                continue
            if line.startswith("data:"):
                data = line[5:].strip()
                if data == "[DONE]":
                    yield ("__done__", None)
                    return
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    parsed = {"_raw": data}
                etype = (
                    parsed.get("type")
                    if isinstance(parsed, dict) else None
                ) or event_name or "<unknown>"
                yield (etype, parsed)


def summarise(payload) -> str:
    if not isinstance(payload, dict):
        return repr(payload)[:120]
    for key in ("delta", "text", "name", "status", "arguments"):
        if key in payload and payload[key] not in (None, ""):
            value = payload[key]
            return f"{key}={json.dumps(value)[:120]}"
    keys = ",".join(sorted(payload.keys()))
    return f"keys=[{keys}]"


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes Responses streaming probe")
    parser.add_argument("--prompt", help="Override the prompt sent to Hermes.")
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Use a plain prompt that should not trigger a tool call.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("HERMES_MODEL", "hermes-agent"),
    )
    parser.add_argument(
        "--conversation",
        default=f"smoke-{int(time.time())}",
        help="Conversation id (UUID-ish). New value = fresh chain in Hermes.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print full JSON payloads in addition to the type summary.",
    )
    args = parser.parse_args()

    base_url = os.environ.get("HERMES_BASE_URL")
    api_key = os.environ.get("HERMES_API_KEY")
    if not base_url or not api_key:
        print("error: set HERMES_BASE_URL and HERMES_API_KEY", file=sys.stderr)
        return 2

    if args.prompt:
        prompt = args.prompt
    elif args.no_tools:
        prompt = PLAIN_PROMPT
    else:
        prompt = TOOL_PROMPT

    print(f"endpoint     : {base_url}/responses")
    print(f"model        : {args.model}")
    print(f"conversation : {args.conversation}")
    print(f"prompt       : {prompt!r}")
    print()
    print("--- stream ---")

    counts: Counter[str] = Counter()
    started = time.perf_counter()
    first_delta_at: float | None = None
    speakable_chars = 0

    try:
        for etype, payload in stream_events(
            base_url, api_key, prompt, args.model, args.conversation
        ):
            counts[etype] += 1
            now = time.perf_counter() - started
            if etype == "response.output_text.delta" and first_delta_at is None:
                first_delta_at = now
            if etype == "response.output_text.delta" and isinstance(payload, dict):
                speakable_chars += len(payload.get("delta") or "")
            tag = "SPEAK" if etype == "response.output_text.delta" else "     "
            line = f"[{now:6.2f}s] {tag} {etype}"
            if not args.raw:
                line += f"  {summarise(payload)}"
            print(line)
            if args.raw and payload is not None:
                print("    " + json.dumps(payload)[:500])
    except httpx.HTTPStatusError as exc:
        print(f"\nHTTP {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"\ntransport error: {exc}", file=sys.stderr)
        return 1

    total = time.perf_counter() - started
    print()
    print("--- summary ---")
    print(f"total time          : {total:.2f} s")
    if first_delta_at is not None:
        print(f"time to first token : {first_delta_at:.2f} s")
    else:
        print("time to first token : (no output_text.delta seen)")
    print(f"speakable chars     : {speakable_chars}")
    print("event counts:")
    for etype, n in counts.most_common():
        print(f"  {n:4d}  {etype}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
