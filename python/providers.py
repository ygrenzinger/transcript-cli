from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

from srt import Cue, write_srt


class ProviderError(RuntimeError):
    pass


class TranscriptionProvider(Protocol):
    name: str
    models: dict[str, str]
    default_model: str
    env_var: str

    def transcribe(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
        ...


@dataclass(frozen=True)
class VoxtralProvider:
    name: str = "voxtral"
    models: dict[str, str] = None  # type: ignore[assignment]
    default_model: str = "voxtral-mini-2602"
    env_var: str = "MISTRAL_API_KEY"

    def __post_init__(self) -> None:
        if self.models is None:
            object.__setattr__(self, "models", {"voxtral-mini-2602": "voxtral-mini-2602"})

    def transcribe(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
        model_id = resolve_model(self, model)
        api_key = require_env(self.env_var)
        try:
            from mistralai import Mistral  # type: ignore
        except ImportError:
            from mistralai.client import Mistral  # type: ignore

        kwargs: dict[str, object] = {
            "model": model_id,
            "file": {"file_name": audio_path.name, "content": audio_path.read_bytes()},
            "timestamp_granularities": ["segment"],
        }
        if language:
            kwargs["language"] = language
        try:
            with Mistral(api_key=api_key) as client:
                response = client.audio.transcriptions.complete(**kwargs)
        except Exception as exc:  # provider SDK raises several generated exception types
            raise ProviderError(f"voxtral transcription failed: {exc}") from exc

        cues = []
        segments = getattr(response, "segments", None) or []
        for index, segment in enumerate(segments, start=1):
            text = getattr(segment, "text", "").strip()
            if not text:
                continue
            speaker = getattr(segment, "speaker_id", None)
            cues.append(
                Cue(
                    index=index,
                    start_ms=round(float(getattr(segment, "start")) * 1000),
                    end_ms=round(float(getattr(segment, "end")) * 1000),
                    speaker=f"Speaker {speaker}" if speaker else None,
                    text=text,
                )
            )
        if not cues:
            text = getattr(response, "text", "").strip()
            if not text:
                raise ProviderError("voxtral returned no transcription text")
            cues = [Cue(index=1, start_ms=0, end_ms=max(1000, round(len(text) * 1000 / 15)), text=text)]
        atomic_write_srt(output_path, cues)


@dataclass(frozen=True)
class GrokProvider:
    name: str = "grok"
    models: dict[str, str] = None  # type: ignore[assignment]
    default_model: str = "grok-transcribe-1"
    env_var: str = "XAI_API_KEY"
    stt_url: str = "https://api.x.ai/v1/stt"

    def __post_init__(self) -> None:
        if self.models is None:
            object.__setattr__(self, "models", {"grok-transcribe-1": "grok-transcribe-1"})

    def transcribe(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
        model_id = resolve_model(self, model)
        api_key = require_env(self.env_var)
        data: dict[str, str] = {"model": model_id, "response_format": "verbose_json", "timestamp_granularities[]": "word"}
        if language:
            data["language"] = language
        try:
            with audio_path.open("rb") as audio_file:
                response = requests.post(
                    self.stt_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (audio_path.name, audio_file, "audio/mpeg")},
                    data=data,
                    timeout=300,
                )
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as exc:
            raise ProviderError(f"grok transcription failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProviderError("grok transcription response was not JSON") from exc

        cues = grok_result_to_cues(result)
        if not cues:
            raise ProviderError("grok returned no timestamped transcription cues")
        atomic_write_srt(output_path, cues)


def grok_result_to_cues(result: dict) -> list[Cue]:
    if isinstance(result.get("segments"), list):
        cues = []
        for index, segment in enumerate(result["segments"], start=1):
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            speaker = segment.get("speaker") or segment.get("speaker_id")
            cues.append(
                Cue(
                    index=index,
                    start_ms=round(float(segment["start"]) * 1000),
                    end_ms=round(float(segment["end"]) * 1000),
                    speaker=f"Speaker {speaker}" if speaker is not None else None,
                    text=text,
                )
            )
        return cues
    words = result.get("words") or []
    return words_to_cues(words)


def words_to_cues(words: list[dict]) -> list[Cue]:
    cues: list[Cue] = []
    current: list[dict] = []
    for word in words:
        text = str(word.get("word") or word.get("text") or "").strip()
        if not text:
            continue
        normalized = {**word, "text": text}
        if current:
            speaker_changed = normalized.get("speaker") != current[0].get("speaker")
            too_long = float(normalized["end"]) - float(current[0]["start"]) > 7.0
            too_many_chars = len(" ".join(w["text"] for w in current + [normalized])) > 84
            sentence_done = current[-1]["text"].rstrip().endswith((".", "?", "!"))
            if speaker_changed or too_long or too_many_chars or sentence_done:
                cues.append(_cue_from_words(len(cues) + 1, current))
                current = []
        current.append(normalized)
    if current:
        cues.append(_cue_from_words(len(cues) + 1, current))
    return cues


def _cue_from_words(index: int, words: list[dict]) -> Cue:
    speaker = words[0].get("speaker")
    return Cue(
        index=index,
        start_ms=round(float(words[0]["start"]) * 1000),
        end_ms=round(float(words[-1]["end"]) * 1000),
        speaker=f"Speaker {speaker}" if speaker is not None else None,
        text=" ".join(word["text"] for word in words),
    )


PROVIDERS: dict[str, TranscriptionProvider] = {
    "voxtral": VoxtralProvider(),
    "grok": GrokProvider(),
}


def get_provider(name: str) -> TranscriptionProvider:
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        available = ", ".join(sorted(PROVIDERS))
        raise ProviderError(f"unknown provider '{name}'. Available providers: {available}") from exc


def resolve_model(provider: TranscriptionProvider, model: str | None) -> str:
    model_key = model or provider.default_model
    if model_key in provider.models:
        return provider.models[model_key]
    if model_key in provider.models.values():
        return model_key
    available = ", ".join(provider.models)
    raise ProviderError(f"unsupported model '{model_key}' for provider '{provider.name}'. Available models: {available}")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ProviderError(f"missing required environment variable: {name}")
    return value


def validate_provider_ready(provider_name: str, model: str | None) -> TranscriptionProvider:
    provider = get_provider(provider_name)
    resolve_model(provider, model)
    require_env(provider.env_var)
    return provider


def atomic_write_srt(output_path: Path, cues: list[Cue]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=output_path.parent, delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        write_srt(temp_path, cues)
        temp_path.replace(output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def list_providers() -> str:
    payload = {
        name: {"default_model": provider.default_model, "models": sorted(provider.models)}
        for name, provider in sorted(PROVIDERS.items())
    }
    return json.dumps(payload, indent=2, sort_keys=True)
