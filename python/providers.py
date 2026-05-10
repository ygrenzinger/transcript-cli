from __future__ import annotations

import json
import os
import platform
import re
import sys
import tarfile
import tempfile
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Protocol

import requests

from audio_splitter import AudioChunk, AudioSplitter, SplitterConfig, merge_chunk_srts
from srt import Cue, write_srt


class ProviderError(RuntimeError):
    pass


TRANSCRIPTION_RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)
SHERPA_PARAKEET_MODEL_KEY = "parakeet-tdt-0.6b-v3-int8"
SHERPA_PARAKEET_MODEL_DIRNAME = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
SHERPA_PARAKEET_MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2"
)
SHERPA_PARAKEET_REQUIRED_FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")
SHERPA_PARAKEET_CACHE_ENV = "SHERPA_ONNX_PARAKEET_CACHE_DIR"
SHERPA_ONNX_PROVIDER_ENV = "SHERPA_ONNX_PROVIDER"
SHERPA_ONNX_NUM_THREADS_ENV = "SHERPA_ONNX_NUM_THREADS"


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


TranscribeOne = Callable[[Path, Path, str | None, str | None], None]


def transcribe_one_with_retries(
    transcribe_one: TranscribeOne,
    audio_path: Path,
    output_path: Path,
    model: str | None,
    language: str | None,
) -> None:
    for attempt_index in range(len(TRANSCRIPTION_RETRY_DELAYS_SECONDS) + 1):
        try:
            transcribe_one(audio_path, output_path, model, language)
            return
        except ProviderError as exc:
            if attempt_index == len(TRANSCRIPTION_RETRY_DELAYS_SECONDS) or not is_retryable_provider_error(exc):
                raise RuntimeError(f"chunk transcription failed for {audio_path}: {exc}") from exc
            time.sleep(retry_delay_seconds(exc, TRANSCRIPTION_RETRY_DELAYS_SECONDS[attempt_index]))


def transcribe_with_splitter(
    transcribe_one: TranscribeOne,
    audio_path: Path,
    output_path: Path,
    model: str | None,
    language: str | None,
    split_config: SplitterConfig,
) -> None:
    split_config.validate()
    with tempfile.TemporaryDirectory(prefix="video-to-srt-chunks-") as tmpdir:
        work_dir = Path(tmpdir)
        log_provider_progress(
            "SPLIT",
            status="START",
            input=audio_path,
            target_chunk_seconds=split_config.target_chunk_duration,
            overlap_seconds=split_config.overlap_duration,
        )
        try:
            chunks = AudioSplitter(split_config).split_audio(audio_path, work_dir)
        except Exception as exc:
            log_provider_progress("SPLIT", status="FAIL", input=audio_path, error=type(exc).__name__)
            raise
        log_provider_progress(
            "SPLIT",
            status="DONE",
            input=audio_path,
            chunks=len(chunks),
            duration_seconds=round(max((chunk.end_time for chunk in chunks), default=0), 3),
        )
        if len(chunks) == 1 and chunks[0].path == audio_path:
            log_provider_progress("SPLIT", status="SKIP", input=audio_path, reason="below_chunk_capacity")
            transcribe_one_with_retries(transcribe_one, audio_path, output_path, model, language)
            return
        chunk_srt_paths: list[Path] = []
        for chunk in chunks:
            chunk_srt = work_dir / f"chunk{chunk.index:03d}.srt"
            log_provider_progress(
                "CHUNK",
                status="START",
                index=chunk.index + 1,
                total=len(chunks),
                input=chunk.path,
                start_seconds=round(chunk.start_time, 3),
                end_seconds=round(chunk.end_time, 3),
            )
            try:
                transcribe_one_with_retries(transcribe_one, chunk.path, chunk_srt, model, language)
            except RuntimeError as exc:
                log_provider_progress(
                    "CHUNK",
                    status="FAIL",
                    index=chunk.index + 1,
                    total=len(chunks),
                    input=chunk.path,
                    error=type(exc).__name__,
                )
                raise RuntimeError(f"chunk transcription failed for chunk {chunk.index} at {chunk.path}: {exc}") from exc
            log_provider_progress(
                "CHUNK",
                status="DONE",
                index=chunk.index + 1,
                total=len(chunks),
                artifact=chunk_srt,
            )
            chunk_srt_paths.append(chunk_srt)
        log_provider_progress("MERGE", status="START", chunks=len(chunks), output=output_path)
        merge_chunk_srts(chunks, chunk_srt_paths, output_path, split_config.similarity_threshold)
        log_provider_progress("MERGE", status="DONE", chunks=len(chunks), artifact=output_path)


def log_provider_progress(event: str, **fields: object) -> None:
    detail = " ".join(f"{key}={format_log_value(value)}" for key, value in fields.items())
    print(f"{event} {detail}", file=sys.stderr)


def format_log_value(value: object) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


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
    split_config: SplitterConfig | None = None

    def __post_init__(self) -> None:
        if self.models is None:
            object.__setattr__(self, "models", {"grok-transcribe-1": "grok-transcribe-1"})

    def transcribe(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
        if self.split_config is not None:
            transcribe_with_splitter(self.transcribe_single, audio_path, output_path, model, language, self.split_config)
            return

        self.transcribe_single(audio_path, output_path, model, language)

    def transcribe_single(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
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
    split_config: SplitterConfig | None = None

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
        if self.split_config is not None:
            transcribe_with_splitter(self.transcribe_single, audio_path, output_path, model, language, self.split_config)
            return

        self.transcribe_single(audio_path, output_path, model, language)

    def transcribe_single(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
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


@dataclass(frozen=True)
class SherpaParakeetProvider:
    name: str = "sherpa-parakeet"
    models: dict[str, str] = None  # type: ignore[assignment]
    default_model: str = SHERPA_PARAKEET_MODEL_KEY
    required_env_vars: tuple[str, ...] = ()
    model_url: str = SHERPA_PARAKEET_MODEL_URL
    split_config: SplitterConfig | None = None

    def __post_init__(self) -> None:
        if self.models is None:
            object.__setattr__(self, "models", {SHERPA_PARAKEET_MODEL_KEY: SHERPA_PARAKEET_MODEL_DIRNAME})

    def transcribe(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
        if self.split_config is not None:
            transcribe_with_splitter(self.transcribe_single, audio_path, output_path, model, language, self.split_config)
            return

        self.transcribe_single(audio_path, output_path, model, language)

    def transcribe_single(self, audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
        resolve_model(self, model)
        model_dir = ensure_sherpa_parakeet_model(self.model_url)
        with tempfile.TemporaryDirectory(prefix="sherpa-parakeet-") as tmpdir:
            wav_path = Path(tmpdir) / f"{audio_path.stem}.wav"
            prepare_sherpa_audio(audio_path, wav_path)
            cues = transcribe_sherpa_parakeet_wav(model_dir, wav_path)
        atomic_write_srt(output_path, cues)


def sherpa_parakeet_cache_root(get_env: Callable[[str], str | None] = os.environ.get) -> Path:
    configured = get_env(SHERPA_PARAKEET_CACHE_ENV)
    if configured:
        return Path(configured).expanduser()
    xdg_cache = get_env("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache).expanduser() / "video-to-srt"
    return Path.home() / ".cache" / "video-to-srt"


def sherpa_parakeet_model_dir(get_env: Callable[[str], str | None] = os.environ.get) -> Path:
    return sherpa_parakeet_cache_root(get_env) / SHERPA_PARAKEET_MODEL_DIRNAME


def ensure_sherpa_parakeet_model(
    model_url: str = SHERPA_PARAKEET_MODEL_URL,
    get_env: Callable[[str], str | None] = os.environ.get,
    request_get: Callable[..., requests.Response] = requests.get,
) -> Path:
    model_dir = sherpa_parakeet_model_dir(get_env)
    if sherpa_parakeet_model_is_valid(model_dir):
        return model_dir

    model_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sherpa-parakeet-download-", dir=model_dir.parent) as tmpdir:
        tmp_path = Path(tmpdir)
        archive_path = tmp_path / "model.tar.bz2"
        try:
            response = request_get(model_url, stream=True, timeout=300)
            response.raise_for_status()
            with archive_path.open("wb") as archive:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        archive.write(chunk)
            safe_extract_tar(archive_path, tmp_path)
        except (OSError, tarfile.TarError, requests.RequestException) as exc:
            raise ProviderError(f"sherpa-parakeet model cache failed: {exc}") from exc

        extracted = tmp_path / SHERPA_PARAKEET_MODEL_DIRNAME
        if not sherpa_parakeet_model_is_valid(extracted):
            raise ProviderError("sherpa-parakeet model cache failed: downloaded archive missing required model files")
        if model_dir.exists():
            remove_existing_model_dir(model_dir)
        extracted.replace(model_dir)
    return model_dir


def sherpa_parakeet_model_is_valid(model_dir: Path) -> bool:
    return all((model_dir / filename).is_file() for filename in SHERPA_PARAKEET_REQUIRED_FILES)


def safe_extract_tar(archive_path: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if destination != target and destination not in target.parents:
                raise ProviderError("sherpa-parakeet model cache failed: archive contains unsafe paths")
        archive.extractall(destination)


def remove_existing_model_dir(model_dir: Path) -> None:
    if not model_dir.is_dir():
        model_dir.unlink(missing_ok=True)
        return
    for child in model_dir.iterdir():
        if child.is_dir():
            remove_existing_model_dir(child)
        else:
            child.unlink()
    model_dir.rmdir()


def prepare_sherpa_audio(audio_path: Path, wav_path: Path) -> None:
    try:
        from moviepy import AudioFileClip  # type: ignore
    except ImportError as exc:
        raise ProviderError("sherpa-parakeet audio preparation failed: moviepy is required") from exc

    clip = None
    try:
        clip = AudioFileClip(str(audio_path))
        clip.write_audiofile(
            str(wav_path),
            fps=16000,
            nbytes=2,
            codec="pcm_s16le",
            ffmpeg_params=["-ac", "1"],
            logger=None,
        )
    except Exception as exc:
        raise ProviderError(f"sherpa-parakeet audio preparation failed: {exc}") from exc
    finally:
        if clip is not None:
            clip.close()

    if not wav_path.is_file() or wav_path.stat().st_size == 0:
        raise ProviderError("sherpa-parakeet audio preparation failed: converted audio file is empty")


def transcribe_sherpa_parakeet_wav(model_dir: Path, wav_path: Path) -> list[Cue]:
    try:
        import numpy as np  # type: ignore
        import sherpa_onnx  # type: ignore
    except ImportError as exc:
        raise ProviderError(f"sherpa-parakeet failed to load sherpa-onnx runtime: {exc}") from exc

    samples, sample_rate = read_sherpa_wave(wav_path, np)
    last_error: Exception | None = None
    for runtime_provider in sherpa_runtime_candidates():
        try:
            recognizer, selected_provider = create_sherpa_parakeet_recognizer(sherpa_onnx, model_dir, runtime_provider)
            log_sherpa_runtime_selection(selected_provider)
            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, samples)
            if hasattr(recognizer, "decode_stream"):
                recognizer.decode_stream(stream)
            else:
                recognizer.decode_streams([stream])
            return sherpa_result_to_cues(stream.result)
        except Exception as exc:  # sherpa runtime errors vary by platform/provider
            last_error = exc
            if runtime_provider == "cpu":
                break
    raise ProviderError(f"sherpa-parakeet transcription failed: {last_error}") from last_error


def read_sherpa_wave(wav_path: Path, np: object) -> tuple[object, int]:
    try:
        with wave.open(str(wav_path)) as wav:
            if wav.getnchannels() != 1:
                raise ProviderError("sherpa-parakeet audio preparation failed: converted audio is not mono")
            if wav.getsampwidth() != 2:
                raise ProviderError("sherpa-parakeet audio preparation failed: converted audio is not 16-bit PCM")
            raw = wav.readframes(wav.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
            return samples, wav.getframerate()
    except wave.Error as exc:
        raise ProviderError(f"sherpa-parakeet audio preparation failed: {exc}") from exc


def sherpa_runtime_candidates(get_env: Callable[[str], str | None] = os.environ.get) -> list[str]:
    configured = get_env(SHERPA_ONNX_PROVIDER_ENV)
    if configured:
        return [configured, "cpu"] if configured != "cpu" else ["cpu"]
    candidates = ["cuda"]
    if platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"}:
        candidates.insert(0, "coreml")
    candidates.append("cpu")
    return candidates


def create_sherpa_parakeet_recognizer(sherpa_onnx: object, model_dir: Path, runtime_provider: str) -> tuple[object, str]:
    kwargs: dict[str, object] = {
        "encoder": str(model_dir / "encoder.int8.onnx"),
        "decoder": str(model_dir / "decoder.int8.onnx"),
        "joiner": str(model_dir / "joiner.int8.onnx"),
        "tokens": str(model_dir / "tokens.txt"),
        "num_threads": sherpa_num_threads(),
        "sample_rate": 16000,
        "feature_dim": 80,
        "decoding_method": "greedy_search",
        "debug": False,
        "model_type": "nemo_transducer",
    }
    if runtime_provider != "cpu":
        kwargs["provider"] = runtime_provider
    try:
        return sherpa_onnx.OfflineRecognizer.from_transducer(**kwargs), runtime_provider
    except TypeError:
        if "provider" not in kwargs:
            raise
        kwargs.pop("provider")
        return sherpa_onnx.OfflineRecognizer.from_transducer(**kwargs), "cpu"


def log_sherpa_runtime_selection(runtime_provider: str) -> None:
    labels = {"coreml": "CoreML", "cuda": "GPU", "cpu": "CPU"}
    label = labels.get(runtime_provider, runtime_provider)
    print(f"sherpa-parakeet selected {label} runtime", file=sys.stderr)


def sherpa_num_threads(get_env: Callable[[str], str | None] = os.environ.get) -> int:
    value = get_env(SHERPA_ONNX_NUM_THREADS_ENV)
    if not value:
        return 2
    try:
        return max(1, int(value))
    except ValueError:
        return 2


def sherpa_result_to_cues(result: object) -> list[Cue]:
    segments = getattr(result, "segments", None)
    if isinstance(segments, list) and segments:
        return sherpa_segments_to_cues(segments)

    text = str(getattr(result, "text", "") or "").strip()
    tokens = list(getattr(result, "tokens", None) or [])
    timestamps = list(getattr(result, "timestamps", None) or [])
    if tokens and timestamps:
        return sherpa_tokens_to_cues(tokens, timestamps)
    if text:
        return [Cue(index=1, start_ms=0, end_ms=max(1000, round(len(text) * 1000 / 15)), text=text)]
    raise ProviderError("sherpa-parakeet returned no transcription text")


def sherpa_segments_to_cues(segments: list[object]) -> list[Cue]:
    cues: list[Cue] = []
    for segment in segments:
        if isinstance(segment, dict):
            text = str(segment.get("text") or segment.get("segment") or "").strip()
            start = segment.get("start")
            end = segment.get("end")
        else:
            text = str(getattr(segment, "text", "") or getattr(segment, "segment", "")).strip()
            start = getattr(segment, "start", None)
            end = getattr(segment, "end", None)
        if not text:
            continue
        try:
            start_ms = round(float(start) * 1000)
            end_ms = round(float(end) * 1000)
        except (TypeError, ValueError) as exc:
            raise ProviderError("sherpa-parakeet returned a segment with invalid timestamp") from exc
        if end_ms <= start_ms:
            raise ProviderError("sherpa-parakeet returned a non-positive-duration segment")
        cues.append(Cue(index=len(cues) + 1, start_ms=start_ms, end_ms=end_ms, text=text))
    if not cues:
        raise ProviderError("sherpa-parakeet returned no transcription text")
    return cues


def sherpa_tokens_to_cues(tokens: list[object], timestamps: list[object]) -> list[Cue]:
    cues: list[Cue] = []
    current_tokens: list[str] = []
    current_start_ms: int | None = None
    previous_start_ms = -1
    usable = min(len(tokens), len(timestamps))
    for index in range(usable):
        token = str(tokens[index])
        if not token:
            continue
        try:
            start_ms = round(float(timestamps[index]) * 1000)
        except (TypeError, ValueError) as exc:
            raise ProviderError("sherpa-parakeet returned an invalid token timestamp") from exc
        if start_ms < previous_start_ms:
            raise ProviderError("sherpa-parakeet returned out-of-order timestamps")
        previous_start_ms = start_ms
        if current_start_ms is None:
            current_start_ms = start_ms
        current_tokens.append(token)
        text = normalize_sherpa_text("".join(current_tokens))
        next_start_ms = sherpa_next_timestamp_ms(timestamps, index, start_ms)
        if next_start_ms - current_start_ms >= 7000 or len(text) > 84 or text.endswith((".", "?", "!")):
            cues.append(Cue(index=len(cues) + 1, start_ms=current_start_ms, end_ms=max(next_start_ms, current_start_ms + 1), text=text))
            current_tokens = []
            current_start_ms = None
    if current_tokens and current_start_ms is not None:
        text = normalize_sherpa_text("".join(current_tokens))
        end_ms = sherpa_next_timestamp_ms(timestamps, usable - 1, current_start_ms)
        cues.append(Cue(index=len(cues) + 1, start_ms=current_start_ms, end_ms=max(end_ms, current_start_ms + 1000), text=text))
    if not cues:
        raise ProviderError("sherpa-parakeet returned no transcription text")
    return cues


def sherpa_next_timestamp_ms(timestamps: list[object], index: int, fallback_ms: int) -> int:
    if index + 1 >= len(timestamps):
        return fallback_ms + 500
    try:
        return round(float(timestamps[index + 1]) * 1000)
    except (TypeError, ValueError):
        return fallback_ms + 500


def normalize_sherpa_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", text)


PROVIDERS: dict[str, TranscriptionProvider] = {
    "voxtral": VoxtralProvider(),
    "grok": GrokProvider(),
    "vertex-gemini": VertexGeminiProvider(split_config=SplitterConfig(target_chunk_duration=900)),
    "sherpa-parakeet": SherpaParakeetProvider(split_config=SplitterConfig(target_chunk_duration=120, overlap_duration=15)),
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
