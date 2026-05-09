#!/usr/bin/env -S uv run

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlparse

from extract_audio import extract_audio
from providers import ProviderError, resolve_model, transcribe_with_retries, validate_provider_ready
from srt import SrtError
from improve_subtitles import improve_subtitles
from validate_srt import validate_srt

T = TypeVar("T")

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


@dataclass(frozen=True)
class PipelineStage:
    number: int
    name: str
    total: int
    context: dict[str, object] = field(default_factory=dict)


def _format_progress_value(value: object) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def progress(message: str) -> None:
    print(message, file=sys.stderr)


def emit_progress(stage: PipelineStage, status: str, **context: object) -> None:
    fields: dict[str, object] = {
        "stage": f"{stage.number}/{stage.total}",
        "name": stage.name,
        "status": status,
        **stage.context,
        **context,
    }
    detail = " ".join(f"{key}={_format_progress_value(value)}" for key, value in fields.items())
    progress(f"PROGRESS {detail}")


def run_stage(stage: PipelineStage, action: Callable[[], T], **done_context: object) -> T:
    emit_progress(stage, "START")
    try:
        result = action()
    except Exception as exc:
        emit_progress(stage, "FAIL", error=type(exc).__name__)
        raise
    emit_progress(stage, "DONE", **done_context)
    return result


def is_http_url(source: str) -> bool:
    return urlparse(source).scheme in {"http", "https"}


def is_youtube_url(source: str) -> bool:
    parsed = urlparse(source)
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and host in YOUTUBE_HOSTS


def download_youtube_video(url: str, download_dir: Path | None = None) -> Path:
    executable = shutil.which("yt-dlp")
    if executable is None:
        raise RuntimeError("yt-dlp is required for YouTube URLs")

    target_dir = download_dir or Path.cwd()
    target_dir.mkdir(parents=True, exist_ok=True)
    output_template = "%(title).200B [%(id)s].%(ext)s"
    command = [
        executable,
        "--no-playlist",
        "--paths",
        str(target_dir),
        "-o",
        output_template,
        "--print",
        "after_move:filepath",
        url,
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        message = "YouTube download failed"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message) from exc

    downloaded_paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(downloaded_paths) != 1:
        raise RuntimeError("YouTube download failed: yt-dlp did not report exactly one downloaded file")

    downloaded = Path(downloaded_paths[0])
    if not downloaded.is_absolute():
        downloaded = target_dir / downloaded
    if not downloaded.exists():
        raise RuntimeError(f"YouTube download failed: downloaded file not found: {downloaded}")
    return downloaded


def resolve_input_source(input_source: str | Path) -> Path:
    source = str(input_source)
    if is_youtube_url(source):
        return download_youtube_video(source)
    if is_http_url(source):
        raise RuntimeError("only local video files and YouTube URLs are supported")

    video_path = Path(input_source)
    if not video_path.exists():
        raise RuntimeError(f"file not found: {video_path}")
    return video_path


def run_pipeline(
    video_path: Path,
    provider_name: str,
    model: str | None,
    language: str | None,
    improve: bool,
    output_path: Path | None = None,
) -> Path:
    provider = validate_provider_ready(provider_name, model)
    resolved_model = resolve_model(provider, model)
    raw_srt = video_path.with_suffix(f".{provider.name}.raw.srt")
    improved_srt = output_path or video_path.with_suffix(f".{provider.name}.improved.srt")
    total_stages = 3 if improve else 2

    audio_path = run_stage(
        PipelineStage(1, "extract_audio", total_stages, {"input": video_path}),
        lambda: extract_audio(video_path),
        artifact=video_path.with_suffix(".mp3"),
    )

    transcription_context: dict[str, object] = {"provider": provider.name, "model": resolved_model, "input": audio_path}
    if model:
        transcription_context["requested_model"] = model
    run_stage(
        PipelineStage(2, "transcribe", total_stages, transcription_context),
        lambda: transcribe_with_retries(provider, audio_path, raw_srt, model, language),
        artifact=raw_srt,
    )
    audio_path.unlink(missing_ok=True)

    if not improve:
        return raw_srt

    run_stage(
        PipelineStage(3, "improve_subtitles", total_stages, {"input": raw_srt}),
        lambda: (improve_subtitles(raw_srt, improved_srt), validate_srt(improved_srt)),
        artifact=improved_srt,
    )
    return improved_srt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Turn a local video file or YouTube URL into raw or improved SRT subtitles.")
    parser.add_argument("input_source")
    parser.add_argument("--provider", default="voxtral")
    parser.add_argument("--model")
    parser.add_argument("--language")
    parser.add_argument("--improve-subtitles", action="store_true", help="write a readability-improved SRT")
    parser.add_argument("--output", "-o", type=Path, help="custom improved SRT path; requires --improve-subtitles")
    args = parser.parse_args(argv)

    if args.output and not args.improve_subtitles:
        parser.error("--output requires --improve-subtitles")

    try:
        video_path = resolve_input_source(args.input_source)
        output = run_pipeline(
            video_path,
            args.provider,
            args.model,
            args.language,
            args.improve_subtitles,
            args.output,
        )
    except (OSError, RuntimeError, ProviderError, SrtError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
