#!/usr/bin/env -S uv run

from __future__ import annotations

import sys

from transcribe import main


if __name__ == "__main__":
    argv = ["--provider", "voxtral", *sys.argv[1:]]
    raise SystemExit(main(argv))
