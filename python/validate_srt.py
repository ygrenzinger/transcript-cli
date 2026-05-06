#!/usr/bin/env -S uv run

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from srt import SrtError, parse_srt


def validate_srt(path: Path | str) -> None:
    cues = parse_srt(Path(path))
    previous_end = None
    for expected, cue in enumerate(cues, start=1):
        if cue.index != expected:
            raise SrtError(f"bad cue index {cue.index}; expected {expected}")
        if cue.end_ms <= cue.start_ms:
            raise SrtError(f"cue {cue.index} end time must be greater than start time")
        if previous_end is not None and cue.start_ms < previous_end:
            raise SrtError(f"cue {cue.index} overlaps previous cue")
        previous_end = cue.end_ms


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a SubRip SRT file.")
    parser.add_argument("srt_file", type=Path)
    args = parser.parse_args(argv)

    try:
        validate_srt(args.srt_file)
    except (OSError, SrtError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("valid", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
