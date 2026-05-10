from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path
from tempfile import NamedTemporaryFile

from srt import Cue, parse_srt, write_srt


@dataclass(frozen=True)
class SplitterConfig:
    target_chunk_duration: int = 1800
    overlap_duration: int = 45
    silence_threshold_db: int = -30
    silence_min_duration: float = 0.5
    search_window: int = 180
    similarity_threshold: float = 0.8

    def validate(self) -> None:
        if self.target_chunk_duration <= 0:
            raise AudioSplitterError("target chunk duration must be greater than zero")
        if self.overlap_duration < 0:
            raise AudioSplitterError("overlap duration cannot be negative")
        if self.overlap_duration >= self.target_chunk_duration:
            raise AudioSplitterError("overlap duration must be less than target chunk duration")
        if self.silence_min_duration <= 0:
            raise AudioSplitterError("minimum silence duration must be greater than zero")
        if self.search_window <= 0:
            raise AudioSplitterError("search window must be greater than zero")
        if not 0 <= self.similarity_threshold <= 1:
            raise AudioSplitterError("similarity threshold must be between 0 and 1")


class AudioSplitterError(RuntimeError):
    pass


@dataclass(frozen=True)
class SilencePoint:
    start: float
    end: float
    duration: float

    @property
    def center(self) -> float:
        return (self.start + self.end) / 2


@dataclass(frozen=True)
class AudioChunk:
    path: Path
    index: int
    start_time: float
    end_time: float
    overlap_start: float = 0
    overlap_end: float = 0


class AudioSplitter:
    def __init__(self, config: SplitterConfig | None = None):
        self.config = config or SplitterConfig()
        self.config.validate()

    def get_audio_duration(self, audio_path: Path) -> float:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError) as exc:
            detail = getattr(exc, "stderr", "") or getattr(exc, "stdout", "") or str(exc)
            raise AudioSplitterError(f"audio duration probe failed: {detail.strip()}") from exc

    def detect_silences(self, audio_path: Path) -> list[SilencePoint]:
        cmd = [
            "ffmpeg",
            "-i",
            str(audio_path),
            "-af",
            f"silencedetect=noise={self.config.silence_threshold_db}dB:d={self.config.silence_min_duration}",
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            detail = result.stderr or result.stdout or "ffmpeg exited non-zero"
            raise AudioSplitterError(f"silence detection failed: {detail.strip()}")
        return parse_silencedetect_output(result.stderr)

    def calculate_split_points(self, duration: float, silences: list[SilencePoint]) -> list[float]:
        split_points: list[float] = []
        target = float(self.config.target_chunk_duration)
        while target < duration - self.config.target_chunk_duration / 2:
            window_start = target - self.config.search_window
            window_end = target + self.config.search_window
            candidates = [s for s in silences if window_start <= s.center <= window_end]
            if candidates:
                split_point = max(candidates, key=lambda s: self._silence_score(s, target)).center
            else:
                split_point = target
            split_points.append(split_point)
            target = split_point + self.config.target_chunk_duration
        return split_points

    def split_audio(self, audio_path: Path, output_dir: Path) -> list[AudioChunk]:
        output_dir.mkdir(parents=True, exist_ok=True)
        duration = self.get_audio_duration(audio_path)
        if duration <= self.config.target_chunk_duration + self.config.target_chunk_duration / 2:
            return [AudioChunk(path=audio_path, index=0, start_time=0, end_time=duration)]

        _log_split("SILENCE_DETECT", status="START", input=audio_path)
        silence_start = time.monotonic()
        silences = self.detect_silences(audio_path)
        _log_split(
            "SILENCE_DETECT",
            status="DONE",
            input=audio_path,
            silences=len(silences),
            duration_seconds=round(time.monotonic() - silence_start, 3),
        )

        split_points = self.calculate_split_points(duration, silences)
        if not split_points:
            return [AudioChunk(path=audio_path, index=0, start_time=0, end_time=duration)]

        chunks: list[AudioChunk] = []
        boundaries = [0.0, *split_points, duration]
        total = len(boundaries) - 1
        _log_split("EXTRACT", status="START", chunks=total)
        extract_start = time.monotonic()
        for index in range(total):
            chunk_start = boundaries[index]
            chunk_end = boundaries[index + 1]
            actual_start = max(0.0, chunk_start - self.config.overlap_duration) if index > 0 else 0.0
            actual_end = min(duration, chunk_end + self.config.overlap_duration) if index < len(boundaries) - 2 else duration
            chunk_path = output_dir / f"{audio_path.stem}_chunk{index:03d}{audio_path.suffix}"
            self.extract_chunk(audio_path, chunk_path, actual_start, actual_end)
            _log_split("EXTRACT", status="PROGRESS", index=index + 1, total=total)
            chunks.append(
                AudioChunk(
                    path=chunk_path,
                    index=index,
                    start_time=actual_start,
                    end_time=actual_end,
                    overlap_start=chunk_start - actual_start if index > 0 else 0,
                    overlap_end=actual_end - chunk_end if index < len(boundaries) - 2 else 0,
                )
            )
        _log_split(
            "EXTRACT",
            status="DONE",
            chunks=total,
            duration_seconds=round(time.monotonic() - extract_start, 3),
        )
        return chunks

    def extract_chunk(self, source: Path, dest: Path, start: float, end: float) -> None:
        cmd = ["ffmpeg", "-y", "-i", str(source), "-ss", str(start), "-t", str(end - start), "-c", "copy", str(dest)]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr or exc.stdout or str(exc)
            raise AudioSplitterError(f"chunk extraction failed: {detail.strip()}") from exc

    def _silence_score(self, silence: SilencePoint, target: float) -> float:
        distance = abs(silence.center - target)
        distance_factor = max(0.0, 1 - (distance / self.config.search_window))
        return silence.duration * distance_factor


def _log_split(event: str, **fields: object) -> None:
    parts: list[str] = []
    for key, value in fields.items():
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'{key}="{escaped}"')
    print(f"{event} {' '.join(parts)}", file=sys.stderr)


def parse_silencedetect_output(output: str) -> list[SilencePoint]:
    silences: list[SilencePoint] = []
    silence_start: float | None = None
    for line in output.splitlines():
        if "silence_start:" in line:
            match = re.search(r"silence_start:\s*([\d.]+)", line)
            if match:
                silence_start = float(match.group(1))
        elif "silence_end:" in line and silence_start is not None:
            match = re.search(r"silence_end:\s*([\d.]+)", line)
            if match:
                silence_end = float(match.group(1))
                silences.append(SilencePoint(silence_start, silence_end, silence_end - silence_start))
                silence_start = None
    return silences


def offset_cues(cues: list[Cue], offset_seconds: float) -> list[Cue]:
    offset_ms = round(offset_seconds * 1000)
    return [replace(cue, start_ms=cue.start_ms + offset_ms, end_ms=cue.end_ms + offset_ms) for cue in cues]


def merge_chunk_srts(chunks: list[AudioChunk], srt_paths: list[Path], output_path: Path, similarity_threshold: float = 0.8) -> None:
    if len(chunks) != len(srt_paths):
        raise AudioSplitterError("number of chunks and SRT files must match")
    merged: list[Cue] = []
    for index, (chunk, srt_path) in enumerate(zip(chunks, srt_paths)):
        current = offset_cues(parse_srt(srt_path), chunk.start_time)
        if index == 0:
            merged.extend(current)
            continue
        keep_prev, use_curr = find_overlap_boundary(merged, current, chunk.overlap_start, similarity_threshold)
        merged = merged[:keep_prev]
        merged.extend(current[use_curr:])
    write_srt_atomic(output_path, sorted(merged, key=lambda cue: (cue.start_ms, cue.end_ms)))


def find_overlap_boundary(prev: list[Cue], curr: list[Cue], overlap_seconds: float, similarity_threshold: float) -> tuple[int, int]:
    if not prev or not curr or overlap_seconds <= 0:
        return len(prev), 0
    overlap_ms = round(overlap_seconds * 1000)
    overlap_start = max(0, prev[-1].end_ms - overlap_ms)
    prev_candidates = [(i, cue) for i, cue in enumerate(prev) if cue.start_ms >= overlap_start]
    curr_overlap_end = curr[0].start_ms + overlap_ms
    curr_candidates = [(i, cue) for i, cue in enumerate(curr) if cue.end_ms <= curr_overlap_end]
    best: tuple[int, int] | None = None
    best_score = 0.0
    for prev_index, prev_cue in prev_candidates:
        for curr_index, curr_cue in curr_candidates:
            score = text_similarity(prev_cue.text, curr_cue.text)
            if score >= similarity_threshold and score > best_score:
                best_score = score
                best = (prev_index, curr_index + 1)
    if best is not None:
        return best
    for index, cue in enumerate(prev):
        if cue.start_ms >= overlap_start:
            return index, 0
    return len(prev), 0


def text_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def write_srt_atomic(path: Path, cues: list[Cue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, prefix=".", suffix=".srt", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        write_srt(tmp_path, cues)
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
