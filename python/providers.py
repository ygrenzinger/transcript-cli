from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Protocol

import requests

from srt import Cue, write_srt


class ProviderError(RuntimeError):
    pass


TRANSCRIPTION_RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)


class TranscriptionProvider(Protocol):
    name: str
    models: dict[str, str]
    default_model: str
    required_env_vars: tuple[str, ...]

    def transcribe(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
        ...


def transcribe_with_retries(
    provider: TranscriptionProvider,
    audio_path: Path,
    output_path: Path,
    model: str | None,
    language: str | None,
) -> None:
    for attempt_index in range(len(TRANSCRIPTION_RETRY_DELAYS_SECONDS) + 1):
        try:
            provider.transcribe(audio_path, output_path, model, language)
            return
        except ProviderError as exc:
            if attempt_index == len(TRANSCRIPTION_RETRY_DELAYS_SECONDS) or not is_retryable_provider_error(exc):
                raise
            time.sleep(retry_delay_seconds(exc, TRANSCRIPTION_RETRY_DELAYS_SECONDS[attempt_index]))


def is_retryable_provider_error(error: ProviderError) -> bool:
    cause = error.__cause__
    if isinstance(cause, (requests.ConnectionError, requests.Timeout)):
        return True
    status_code = provider_status_code(cause)
    return status_code == 429 or (status_code is not None and 500 <= status_code <= 599)


def retry_delay_seconds(error: ProviderError, default_delay: float) -> float:
    if provider_status_code(error.__cause__) != 429:
        return default_delay
    retry_after = provider_retry_after(error.__cause__)
    if retry_after is None:
        return default_delay
    return retry_after


def provider_status_code(exc: BaseException | None) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
    try:
        return int(status_code)
    except (TypeError, ValueError):
        return None


def provider_retry_after(exc: BaseException | None) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())


@dataclass(frozen=True)
class VoxtralProvider:
    name: str = "voxtral"
    models: dict[str, str] = None  # type: ignore[assignment]
    default_model: str = "voxtral-mini-2602"
    required_env_vars: tuple[str, ...] = ("MISTRAL_API_KEY",)

    def __post_init__(self) -> None:
        if self.models is None:
            object.__setattr__(self, "models", {"voxtral-mini-2602": "voxtral-mini-2602"})

    def transcribe(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
        model_id = resolve_model(self, model)
        api_key = require_env("MISTRAL_API_KEY")
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
    required_env_vars: tuple[str, ...] = ("XAI_API_KEY",)
    stt_url: str = "https://api.x.ai/v1/stt"

    def __post_init__(self) -> None:
        if self.models is None:
            object.__setattr__(self, "models", {"grok-transcribe-1": "grok-transcribe-1"})

    def transcribe(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
        model_id = resolve_model(self, model)
        api_key = require_env("XAI_API_KEY")
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


VERTEX_GEMINI_PROMPT = """Transcribe the audio into subtitle-ready segments.

Return only JSON matching this shape:
{
  "segments": [
    {"start": 0.0, "end": 2.4, "text": "spoken text"}
  ]
}

Rules:
- Use seconds as numbers for start and end.
- Preserve the spoken language; do not translate.
- Do not summarize or omit speech.
- Keep segments short enough for subtitles.
- Return valid JSON only, with no markdown.
"""

VERTEX_GEMINI_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["start", "end", "text"],
            },
        }
    },
    "required": ["segments"],
}


@dataclass(frozen=True)
class VertexGeminiProvider:
    name: str = "vertex-gemini"
    models: dict[str, str] = None  # type: ignore[assignment]
    default_model: str = "gemini-2.5-flash"
    required_env_vars: tuple[str, ...] = ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")

    def __post_init__(self) -> None:
        if self.models is None:
            object.__setattr__(
                self,
                "models",
                {
                    "gemini-2.5-flash": "gemini-2.5-flash",
                    "gemini-2.5-pro": "gemini-2.5-pro",
                },
            )

    def transcribe(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
        model_id = resolve_model(self, model)
        project = require_env("GOOGLE_CLOUD_PROJECT")
        location = require_env("GOOGLE_CLOUD_LOCATION")
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except ImportError as exc:
            raise ProviderError("vertex-gemini requires the google-genai package") from exc

        prompt = VERTEX_GEMINI_PROMPT
        if language:
            prompt += f"\n- The caller supplied language hint: {language}."
        try:
            client = genai.Client(vertexai=True, project=project, location=location)
            response = client.models.generate_content(
                model=model_id,
                contents=[
                    types.Part.from_bytes(data=audio_path.read_bytes(), mime_type="audio/mp3"),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=VERTEX_GEMINI_RESPONSE_SCHEMA,
                ),
            )
        except Exception as exc:  # Google SDK exception shapes vary by auth/transport/API failure.
            raise ProviderError(f"vertex-gemini transcription failed: {exc}") from exc

        atomic_write_srt(output_path, vertex_gemini_response_to_cues(response))


def vertex_gemini_response_to_cues(response: object) -> list[Cue]:
    text = str(getattr(response, "text", "") or "").strip()
    if not text:
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return vertex_gemini_result_to_cues(_json_compatible(parsed))
        raise ProviderError("vertex-gemini returned no transcription text")
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError("vertex-gemini transcription response was not JSON") from exc
    return vertex_gemini_result_to_cues(result)


def _json_compatible(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    if hasattr(value, "dict"):
        return value.dict()
    return value


def vertex_gemini_result_to_cues(result: object) -> list[Cue]:
    if not isinstance(result, dict):
        raise ProviderError("vertex-gemini transcription response had unexpected shape")
    segments = result.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ProviderError("vertex-gemini returned no timestamped transcription segments")

    cues: list[Cue] = []
    previous_start_ms = -1
    for segment in segments:
        if not isinstance(segment, dict):
            raise ProviderError("vertex-gemini transcription segment had unexpected shape")
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start_ms = _vertex_gemini_timestamp_ms(segment, "start")
        end_ms = _vertex_gemini_timestamp_ms(segment, "end")
        if end_ms <= start_ms:
            raise ProviderError("vertex-gemini returned a non-positive-duration segment")
        if start_ms < previous_start_ms:
            raise ProviderError("vertex-gemini returned out-of-order segments")
        previous_start_ms = start_ms
        cues.append(Cue(index=len(cues) + 1, start_ms=start_ms, end_ms=end_ms, text=text))

    if not cues:
        raise ProviderError("vertex-gemini returned no transcription text")
    return cues


def _vertex_gemini_timestamp_ms(segment: dict[str, object], key: str) -> int:
    try:
        return round(float(segment[key]) * 1000)
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError(f"vertex-gemini returned a segment with invalid {key} timestamp") from exc


PROVIDERS: dict[str, TranscriptionProvider] = {
    "voxtral": VoxtralProvider(),
    "grok": GrokProvider(),
    "vertex-gemini": VertexGeminiProvider(),
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


def validate_required_env_vars(provider: TranscriptionProvider, get_env: Callable[[str], str | None] = os.environ.get) -> None:
    for name in provider.required_env_vars:
        if not get_env(name):
            raise ProviderError(f"missing required environment variable: {name}")


def validate_provider_ready(provider_name: str, model: str | None) -> TranscriptionProvider:
    provider = get_provider(provider_name)
    resolve_model(provider, model)
    validate_required_env_vars(provider)
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
