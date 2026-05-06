#!/usr/bin/env -S uv run

from __future__ import annotations

import sys

from transcribe import main


if __name__ == "__main__":
    argv = ["--provider", "grok", *[arg for arg in sys.argv[1:] if arg not in {"--timestamps", "--diarize"}]]
    raise SystemExit(main(argv))
