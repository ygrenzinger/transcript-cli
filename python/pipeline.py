#!/usr/bin/env -S uv run

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from extract_audio import extract_audio
from providers import ProviderError, resolve_model, validate_provider_ready
from srt import SrtError
from standardize_srt import standardize_srt
from validate_srt import validate_srt

T = TypeVar("T")
TOTAL_STAGES = 4


@dataclass(frozen=True)
class PipelineStage:
    number: int
    name: str
    context: dict[str, object] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return TOTAL_STAGES


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


def run_pipeline(video_path: Path, provider_name: str, model: str | None, language: str | None) -> Path:
    provider = validate_provider_ready(provider_name, model)
    resolved_model = resolve_model(provider, model)
    raw_srt = video_path.with_suffix(f".{provider.name}.raw.srt")
    final_srt = video_path.with_suffix(".srt")

    audio_path = run_stage(
        PipelineStage(1, "extract_audio", {"input": video_path}),
        lambda: extract_audio(video_path),
        artifact=video_path.with_suffix(".mp3"),
    )

    transcription_context: dict[str, object] = {"provider": provider.name, "model": resolved_model, "input": audio_path}
    if model:
        transcription_context["requested_model"] = model
    run_stage(
        PipelineStage(2, "transcribe", transcription_context),
        lambda: provider.transcribe(audio_path, raw_srt, model, language),
        artifact=raw_srt,
    )

    run_stage(
        PipelineStage(3, "validate_raw_srt", {"input": raw_srt}),
        lambda: validate_srt(raw_srt),
        artifact=raw_srt,
    )

    run_stage(
        PipelineStage(4, "standardize_srt", {"input": raw_srt}),
        lambda: (standardize_srt(raw_srt, final_srt), validate_srt(final_srt)),
        artifact=final_srt,
    )
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
