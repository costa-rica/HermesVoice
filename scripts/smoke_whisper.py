#!/usr/bin/env python3
"""
Whisper smoke test: send an audio file to OpenAI Whisper and report
transcript, wall-clock latency, and uploaded byte count.

Used to answer the V1 audio-format question: is 16 kHz mono PCM WAV uplink
fast enough, and does Opus help meaningfully? Run it for both formats and
compare.

Usage:
    export OPENAI_API_KEY=sk-...

    # Generate a 3-second test clip locally, then run:
    python scripts/smoke_whisper.py --generate
    python scripts/smoke_whisper.py --file /tmp/hv_smoke.wav
    python scripts/smoke_whisper.py --file /tmp/hv_smoke.ogg

Setup (one-time):
    python3 -m venv .venv && source .venv/bin/activate
    pip install openai
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


SAMPLE_TEXT = (
    "This is a HermesVoice smoke test. The quick brown fox "
    "jumps over the lazy dog. End of utterance."
)


def generate_sample(target: Path, fmt: str) -> Path:
    """Generate a 16 kHz mono speech clip on macOS or Linux."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to generate sample audio")

    aiff = target.with_suffix(".aiff")
    say = shutil.which("say")
    if say:
        subprocess.run(
            [say, "-o", str(aiff), SAMPLE_TEXT],
            check=True,
        )
    else:
        filters = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if " flite " not in filters:
            raise RuntimeError(
                "sample generation requires macOS `say` or ffmpeg built with libflite; "
                "otherwise pass --file PATH to an existing speech clip"
            )
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write(SAMPLE_TEXT)
            text_path = Path(fh.name)
        try:
            subprocess.run(
                [
                    ffmpeg, "-y", "-loglevel", "error",
                    "-f", "lavfi",
                    "-i", f"flite=textfile={text_path}:voice=slt",
                    str(aiff),
                ],
                check=True,
            )
        finally:
            text_path.unlink(missing_ok=True)

    if fmt == "wav":
        out = target.with_suffix(".wav")
        subprocess.run(
            [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", str(aiff),
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                str(out),
            ],
            check=True,
        )
    elif fmt == "opus":
        out = target.with_suffix(".ogg")
        subprocess.run(
            [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", str(aiff),
                "-ar", "16000", "-ac", "1", "-c:a", "libopus", "-b:a", "24k",
                str(out),
            ],
            check=True,
        )
    else:
        raise ValueError(f"unknown format: {fmt}")
    aiff.unlink(missing_ok=True)
    return out


def transcribe(path: Path, model: str) -> tuple[str, float, int]:
    from openai import OpenAI

    client = OpenAI()
    size = path.stat().st_size
    started = time.perf_counter()
    with path.open("rb") as fh:
        result = client.audio.transcriptions.create(
            model=model,
            file=fh,
            response_format="text",
        )
    elapsed = time.perf_counter() - started
    text = result if isinstance(result, str) else getattr(result, "text", str(result))
    return text.strip(), elapsed, size


def main() -> int:
    parser = argparse.ArgumentParser(description="Whisper latency smoke test")
    parser.add_argument(
        "--file",
        type=Path,
        help="Audio file to transcribe (wav, ogg/oga, m4a, mp3, flac all accepted by Whisper).",
    )
    parser.add_argument(
        "--generate",
        choices=["wav", "opus", "both"],
        help="Generate a local sample clip (macOS `say` or ffmpeg+flite), then transcribe it.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("STT_MODEL", "whisper-1"),
    )
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("error: OPENAI_API_KEY is not set", file=sys.stderr)
        return 2

    targets: list[Path] = []
    if args.generate:
        base = Path("/tmp/hv_smoke")
        formats = ["wav", "opus"] if args.generate == "both" else [args.generate]
        for fmt in formats:
            targets.append(generate_sample(base, fmt))
    if args.file:
        targets.append(args.file)

    if not targets:
        parser.error("pass --file PATH or --generate {wav,opus,both}")

    print(f"model: {args.model}")
    print(f"reference text: {SAMPLE_TEXT!r}")
    print()

    for path in targets:
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            continue
        try:
            text, elapsed, size = transcribe(path, args.model)
        except Exception as exc:
            print(f"FAIL  {path.name}: {exc}", file=sys.stderr)
            continue
        kbps = (size * 8 / 1000) / max(elapsed, 1e-6)
        print(f"file       : {path}")
        print(f"size       : {size:,} bytes")
        print(f"latency    : {elapsed:.2f} s")
        print(f"upload rate: {kbps:.1f} kbit/s effective")
        print(f"transcript : {text}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
