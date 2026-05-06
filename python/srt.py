from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path


TIMING_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> "
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})$"
)


@dataclass(frozen=True)
class Cue:
    index: int
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


class SrtError(ValueError):
    pass


def timestamp_to_ms(value: str) -> int:
    match = re.match(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$", value)
    if not match:
        raise SrtError(f"invalid timestamp: {value}")
    hours, minutes, seconds, milliseconds = map(int, match.groups())
    if minutes >= 60 or seconds >= 60:
        raise SrtError(f"invalid timestamp range: {value}")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds


def ms_to_timestamp(value: int) -> str:
    if value < 0:
        raise SrtError("timestamp cannot be negative")
    seconds, milliseconds = divmod(value, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def parse_timing(line: str) -> tuple[int, int]:
    match = TIMING_RE.match(line)
    if not match:
        raise SrtError(f"invalid timing line: {line}")
    left, right = line.split(" --> ", 1)
    return timestamp_to_ms(left), timestamp_to_ms(right)


def read_srt_bytes(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise SrtError("file must be UTF-8 without BOM")
    if b"\r\n" in data or b"\r" in data:
        raise SrtError("file must use LF line endings, not CRLF")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SrtError("file must be valid UTF-8") from exc


def parse_srt(path: Path | str) -> list[Cue]:
    content = read_srt_bytes(Path(path))
    if not content.strip():
        return []
    if not content.endswith("\n"):
        raise SrtError("file must end with a newline")

    cues: list[Cue] = []
    offset = 0
    for block in content.rstrip("\n").split("\n\n"):
        line_no = content[:offset].count("\n") + 1
        offset += len(block) + 2
        lines = block.split("\n")
        if len(lines) < 3:
            raise SrtError(f"malformed cue at line {line_no}")
        if not lines[0].isdigit():
            raise SrtError(f"missing numeric index at line {line_no}")
        index = int(lines[0])
        try:
            start_ms, end_ms = parse_timing(lines[1])
        except SrtError as exc:
            raise SrtError(f"{exc} at line {line_no + 1}") from exc
        text_lines = lines[2:]
        if not any(line.strip() for line in text_lines):
            raise SrtError(f"empty cue text at line {line_no + 2}")
        speaker, text = split_speaker_prefix("\n".join(text_lines).strip())
        cues.append(Cue(index=index, start_ms=start_ms, end_ms=end_ms, text=text, speaker=speaker))
    return cues


def split_speaker_prefix(text: str) -> tuple[str | None, str]:
    first, sep, rest = text.partition("\n")
    match = re.match(r"^(Speaker\s+[^:]+):\s*(.*)$", first.strip())
    if not match:
        return None, text
    speaker = match.group(1)
    first_text = match.group(2)
    body = first_text if not sep else f"{first_text}\n{rest}".strip()
    return speaker, body


def format_srt(cues: list[Cue]) -> str:
    blocks: list[str] = []
    for new_index, cue in enumerate(cues, start=1):
        text = cue.text.strip()
        if cue.speaker:
            lines = text.split("\n")
            lines[0] = f"{cue.speaker}: {lines[0]}" if lines[0] else f"{cue.speaker}:"
            text = "\n".join(lines)
        blocks.append(
            "\n".join(
                [
                    str(new_index),
                    f"{ms_to_timestamp(cue.start_ms)} --> {ms_to_timestamp(cue.end_ms)}",
                    text,
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def write_srt(path: Path | str, cues: list[Cue]) -> None:
    Path(path).write_text(format_srt(cues), encoding="utf-8", newline="\n")


def reindex(cues: list[Cue]) -> list[Cue]:
    return [replace(cue, index=index) for index, cue in enumerate(cues, start=1)]
