#!/usr/bin/env -S uv run

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from extract_audio import extract_audio
from providers import ProviderError, validate_provider_ready
from srt import SrtError
from standardize_srt import standardize_srt
from validate_srt import validate_srt


def progress(message: str) -> None:
    print(message, file=sys.stderr)


def run_pipeline(video_path: Path, provider_name: str, model: str | None, language: str | None) -> Path:
    provider = validate_provider_ready(provider_name, model)
    raw_srt = video_path.with_suffix(f".{provider.name}.raw.srt")
    final_srt = video_path.with_suffix(".srt")

    progress("[1/4] Extracting audio...")
    audio_path = extract_audio(video_path)
    progress("[1/4] Extracting audio complete")

    progress(f"[2/4] Transcribing with {provider.name}...")
    provider.transcribe(audio_path, raw_srt, model, language)
    progress("[2/4] Transcribing complete")

    progress("[3/4] Validating raw SRT...")
    validate_srt(raw_srt)
    progress("[3/4] Raw SRT valid")

    progress("[4/4] Standardizing SRT...")
    standardize_srt(raw_srt, final_srt)
    validate_srt(final_srt)
    progress("[4/4] Standardizing complete")
    return final_srt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Turn a video file into a standardized SRT file.")
    parser.add_argument("video_file", type=Path)
    parser.add_argument("--provider", default="voxtral")
    parser.add_argument("--model")
    parser.add_argument("--language")
    args = parser.parse_args(argv)

    if not args.video_file.exists():
        print(f"Error: file not found: {args.video_file}", file=sys.stderr)
        return 1

    try:
        output = run_pipeline(args.video_file, args.provider, args.model, args.language)
    except (OSError, RuntimeError, ProviderError, SrtError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
