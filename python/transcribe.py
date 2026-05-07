#!/usr/bin/env -S uv run

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from extract_audio import extract_audio
from providers import ProviderError, resolve_model, transcribe_with_retries, validate_provider_ready
from srt import SrtError
from improve_subtitles import improve_subtitles
from validate_srt import validate_srt

T = TypeVar("T")


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
    parser = argparse.ArgumentParser(description="Turn a video file into raw or improved SRT subtitles.")
    parser.add_argument("video_file", type=Path)
    parser.add_argument("--provider", default="voxtral")
    parser.add_argument("--model")
    parser.add_argument("--language")
    parser.add_argument("--improve-subtitles", action="store_true", help="write a readability-improved SRT")
    parser.add_argument("--output", "-o", type=Path, help="custom improved SRT path; requires --improve-subtitles")
    args = parser.parse_args(argv)

    if args.output and not args.improve_subtitles:
        parser.error("--output requires --improve-subtitles")

    if not args.video_file.exists():
        print(f"Error: file not found: {args.video_file}", file=sys.stderr)
        return 1

    try:
        output = run_pipeline(
            args.video_file,
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
