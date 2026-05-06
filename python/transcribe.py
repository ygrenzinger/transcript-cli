#!/usr/bin/env -S uv run

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from providers import ProviderError, get_provider, list_providers, resolve_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transcribe audio to SRT with a registered provider.")
    parser.add_argument("audio_file", nargs="?", type=Path)
    parser.add_argument("--output", "-o", type=Path)
    parser.add_argument("--provider", default="voxtral")
    parser.add_argument("--model")
    parser.add_argument("--language")
    parser.add_argument("--list-providers", action="store_true")
    args = parser.parse_args(argv)

    if args.list_providers:
        print(list_providers())
        return 0
    try:
        provider = get_provider(args.provider)
        resolve_model(provider, args.model)
    except ProviderError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.audio_file is None:
        parser.error("audio_file is required unless --list-providers is used")
    if not args.audio_file.exists():
        print(f"Error: file not found: {args.audio_file}", file=sys.stderr)
        return 1
    output = args.output or args.audio_file.with_suffix(".srt")

    try:
        provider.transcribe(args.audio_file, output, args.model, args.language)
    except ProviderError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
