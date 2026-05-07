#!/usr/bin/env -S uv run

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from dataclasses import replace
from pathlib import Path

from srt import Cue, SrtError, parse_srt, reindex, write_srt
from validate_srt import validate_srt


MAX_DURATION_MS = 7000
MIN_DURATION_MS = 500
TARGET_MIN_DURATION_MS = 1000
MAX_CPS = 17
MAX_CHARS = 84
LINE_WIDTH = 42
MIN_GAP_MS = 80


def displayed_len(text: str) -> int:
    return len(text.replace("\n", ""))


def wrap_text(text: str, first_width: int = LINE_WIDTH) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= first_width:
        return one_line
    preferred = _best_line_break(one_line, first_width)
    if preferred is not None:
        return one_line[:preferred].rstrip() + "\n" + one_line[preferred:].lstrip()
    first, *rest = textwrap.wrap(one_line, width=first_width, break_long_words=False)
    if not rest:
        return first
    return first + "\n" + textwrap.fill(" ".join(rest), width=LINE_WIDTH, break_long_words=False)


def _best_line_break(text: str, first_width: int = LINE_WIDTH) -> int | None:
    candidates = [match.start() + 1 for match in re.finditer(r"[,.!?;:]\s+", text)]
    candidates += [match.start() for match in re.finditer(r"\s+(?:and|but|or|because|so|yet)\s+", text, re.I)]
    candidates += [match.start() for match in re.finditer(r"\s+", text)]
    valid = [idx for idx in candidates if idx <= first_width and len(text[idx:].strip()) <= LINE_WIDTH]
    if not valid:
        return None
    return min(valid, key=lambda idx: abs(idx - len(text) / 2))


def _split_words(text: str) -> list[str]:
    return re.findall(r"\S+", text.replace("\n", " "))


def _choose_split(words: list[str], max_chars: int) -> int:
    best = 1
    current = 0
    for index, word in enumerate(words, start=1):
        current += len(word) + (1 if index > 1 else 0)
        if current > max_chars:
            break
        best = index
    window = range(max(1, best - 6), min(len(words), best + 6) + 1)
    for marks in ((".", "?", "!"), (",", ";", ":")):
        marked = [idx for idx in window if words[idx - 1].rstrip().endswith(marks)]
        if marked:
            return max(marked)
    return best


def split_long_cue(cue: Cue) -> list[Cue]:
    pending = _split_words(cue.text)
    if not pending:
        return []
    cue_limit = MAX_CHARS - len(f"{cue.speaker}: ") if cue.speaker else MAX_CHARS
    cue_limit = max(20, cue_limit)
    first_width = LINE_WIDTH - len(f"{cue.speaker}: ") if cue.speaker else LINE_WIDTH
    first_width = max(10, first_width)
    parts: list[str] = []
    while pending:
        split_at = len(pending)
        text = " ".join(pending)
        duration_ok = cue.duration_ms <= MAX_DURATION_MS
        chars_ok = len(text) <= cue_limit
        cps_ok = cue.duration_ms <= 0 or displayed_len(text) * 1000 / cue.duration_ms <= MAX_CPS
        if not (duration_ok and chars_ok and cps_ok) and len(pending) > 1:
            max_chars = min(cue_limit, max(1, int(MAX_CPS * MAX_DURATION_MS / 1000)))
            split_at = _choose_split(pending, max_chars)
        while split_at > 1 and len(wrap_text(" ".join(pending[:split_at]), first_width).split("\n")) > 2:
            split_at -= 1
        parts.append(" ".join(pending[:split_at]))
        pending = pending[split_at:]

    total_chars = sum(max(1, displayed_len(part)) for part in parts)
    result: list[Cue] = []
    cursor = cue.start_ms
    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            end_ms = cue.end_ms
        else:
            share = max(1, displayed_len(part)) / total_chars
            end_ms = min(cue.end_ms, cursor + max(MIN_DURATION_MS, round(cue.duration_ms * share)))
        result.append(replace(cue, start_ms=cursor, end_ms=max(cursor + MIN_DURATION_MS, end_ms), text=wrap_text(part)))
        cursor = result[-1].end_ms
    return result


def extend_for_cps(cues: list[Cue]) -> list[Cue]:
    result = cues[:]
    for i, cue in enumerate(result):
        cps = displayed_len(cue.text) * 1000 / max(1, cue.duration_ms)
        if cps <= MAX_CPS:
            continue
        required_end = cue.start_ms + round(displayed_len(cue.text) * 1000 / MAX_CPS)
        next_start = result[i + 1].start_ms - MIN_GAP_MS if i + 1 < len(result) else required_end
        result[i] = replace(cue, end_ms=max(cue.end_ms, min(required_end, next_start)))
    return result


def enforce_gaps(cues: list[Cue]) -> list[Cue]:
    result = cues[:]
    for i in range(len(result) - 1):
        current = result[i]
        nxt = result[i + 1]
        if nxt.start_ms - current.end_ms >= MIN_GAP_MS:
            continue
        target_end = nxt.start_ms - MIN_GAP_MS
        if target_end - current.start_ms >= MIN_DURATION_MS:
            result[i] = replace(current, end_ms=target_end)
            continue
        target_start = current.end_ms + MIN_GAP_MS
        if nxt.end_ms - target_start >= MIN_DURATION_MS:
            result[i + 1] = replace(nxt, start_ms=target_start)
            continue
        if nxt.start_ms < current.end_ms:
            result[i] = replace(current, end_ms=max(current.start_ms + 1, nxt.start_ms))
    return result


def standardize_cues(cues: list[Cue]) -> list[Cue]:
    cues = [cue for cue in cues if cue.end_ms > cue.start_ms]
    cues = split_embedded_speaker_changes(cues)
    multi_speaker = len({cue.speaker for cue in cues if cue.speaker}) >= 2
    standardized: list[Cue] = []
    for cue in cues:
        speaker = cue.speaker if multi_speaker else None
        base = replace(cue, speaker=speaker, text=" ".join(cue.text.split()))
        standardized.extend(split_long_cue(base))
    standardized = extend_for_cps(standardized)
    standardized = enforce_gaps(standardized)
    standardized = [replace(cue, text=wrap_cue_text(cue)) for cue in standardized if cue.text.strip()]
    return reindex(standardized)


def wrap_cue_text(cue: Cue) -> str:
    first_width = LINE_WIDTH - len(f"{cue.speaker}: ") if cue.speaker else LINE_WIDTH
    return wrap_text(cue.text, max(10, first_width))


def split_embedded_speaker_changes(cues: list[Cue]) -> list[Cue]:
    result: list[Cue] = []
    marker = re.compile(r"\b(Speaker\s+[^:]+):")
    for cue in cues:
        matches = list(marker.finditer(cue.text))
        if not matches:
            result.append(cue)
            continue
        pieces: list[tuple[str, str]] = []
        if cue.text[: matches[0].start()].strip():
            pieces.append((cue.speaker or "Speaker 1", cue.text[: matches[0].start()].strip()))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(cue.text)
            pieces.append((match.group(1), cue.text[match.end() : end].strip()))
        pieces = [(speaker, text) for speaker, text in pieces if text]
        if len(pieces) <= 1:
            result.append(cue)
            continue
        total = sum(max(1, displayed_len(text)) for _, text in pieces)
        cursor = cue.start_ms
        for index, (speaker, text) in enumerate(pieces):
            if index == len(pieces) - 1:
                end_ms = cue.end_ms
            else:
                end_ms = cursor + round(cue.duration_ms * max(1, displayed_len(text)) / total)
            result.append(replace(cue, start_ms=cursor, end_ms=end_ms, speaker=speaker, text=text))
            cursor = end_ms
    return result


def standardize_srt(input_path: Path | str, output_path: Path | str) -> None:
    cues = parse_srt(Path(input_path))
    output = Path(output_path)
    write_srt(output, standardize_cues(cues))
    validate_srt(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Standardize an SRT file for readability.")
    parser.add_argument("input_srt", type=Path)
    parser.add_argument("output_srt", type=Path, nargs="?")
    args = parser.parse_args(argv)
    output = args.output_srt or args.input_srt
    try:
        standardize_srt(args.input_srt, output)
    except (OSError, SrtError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
