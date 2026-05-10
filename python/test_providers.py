from __future__ import annotations

import json
import os
import sys
import tarfile
import tempfile
import types
import unittest
from io import BytesIO, StringIO
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import providers
from audio_splitter import AudioChunk, SplitterConfig
from providers import (
    ProviderError,
    SHERPA_PARAKEET_MODEL_KEY,
    get_provider,
    ensure_sherpa_parakeet_model,
    list_providers,
    sherpa_parakeet_model_is_valid,
    sherpa_result_to_cues,
    sherpa_runtime_candidates,
    validate_required_env_vars,
    transcribe_with_splitter,
    vertex_gemini_result_to_cues,
)
from srt import parse_srt, write_srt


@dataclass(frozen=True)
class FakeProvider:
    name: str = "fake"
    models: dict[str, str] = None  # type: ignore[assignment]
    default_model: str = "fake-model"
    required_env_vars: tuple[str, ...] = ("ONE", "TWO")

    def __post_init__(self) -> None:
        if self.models is None:
            object.__setattr__(self, "models", {"fake-model": "fake-model"})


class ProviderConfigurationTests(unittest.TestCase):
    def test_single_required_env_var_error_names_missing_value(self) -> None:
        provider = FakeProvider(required_env_vars=("ONLY",))

        with self.assertRaisesRegex(ProviderError, "ONLY"):
            validate_required_env_vars(provider, get_env=lambda _: None)

    def test_multiple_required_env_var_error_names_first_missing_value(self) -> None:
        provider = FakeProvider(required_env_vars=("ONE", "TWO"))

        values = {"ONE": "set"}

        with self.assertRaisesRegex(ProviderError, "TWO"):
            validate_required_env_vars(provider, get_env=values.get)

    def test_default_split_policies_are_provider_owned(self) -> None:
        self.assertIsNone(getattr(providers.get_provider("voxtral"), "split_config", None))
        self.assertIsNone(getattr(providers.get_provider("grok"), "split_config", None))
        gemini = providers.get_provider("vertex-gemini")
        parakeet = providers.get_provider("sherpa-parakeet")

        self.assertEqual(900, gemini.split_config.target_chunk_duration)
        self.assertEqual(30, parakeet.split_config.target_chunk_duration)
        self.assertEqual(5, parakeet.split_config.overlap_duration)
        self.assertEqual(5, parakeet.split_config.search_window)


class ProviderOwnedSplittingTests(unittest.TestCase):
    def test_chunked_provider_helper_preserves_options_and_merges_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            audio = root / "audio.mp3"
            audio.write_bytes(b"audio")
            output = root / "out.srt"
            calls: list[tuple[str, str | None, str | None]] = []

            class FakeAudioSplitter:
                def __init__(self, _config: SplitterConfig) -> None:
                    return None

                def split_audio(self, _audio_path: Path, output_dir: Path) -> list[AudioChunk]:
                    first = output_dir / "chunk000.mp3"
                    second = output_dir / "chunk001.mp3"
                    first.write_bytes(b"first")
                    second.write_bytes(b"second")
                    return [AudioChunk(first, 0, 0, 5), AudioChunk(second, 1, 5, 10)]

            def transcribe_one(audio_path: Path, output_path: Path, model: str | None, language: str | None) -> None:
                calls.append((audio_path.name, model, language))
                text = "hello" if audio_path.name == "chunk000.mp3" else "world"
                write_srt(output_path, [providers.Cue(index=1, start_ms=0, end_ms=1000, text=text)])

            stderr = StringIO()
            with patch.object(providers, "AudioSplitter", FakeAudioSplitter), patch("sys.stderr", stderr):
                transcribe_with_splitter(transcribe_one, audio, output, "model-a", "fr", SplitterConfig(target_chunk_duration=10, overlap_duration=1))

            self.assertEqual([("chunk000.mp3", "model-a", "fr"), ("chunk001.mp3", "model-a", "fr")], calls)
            self.assertEqual(["hello", "world"], [cue.text for cue in parse_srt(output)])
            self.assertIn('SPLIT status="START"', stderr.getvalue())
            self.assertIn('target_chunk_seconds="10"', stderr.getvalue())
            self.assertIn('CHUNK status="START" index="1" total="2"', stderr.getvalue())
            self.assertIn('MERGE status="DONE"', stderr.getvalue())

    def test_chunked_provider_helper_retries_each_chunk_and_avoids_partial_final_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            audio = root / "audio.mp3"
            audio.write_bytes(b"audio")
            output = root / "out.srt"
            attempts: dict[str, int] = {}

            class FakeAudioSplitter:
                def __init__(self, _config: SplitterConfig) -> None:
                    return None

                def split_audio(self, _audio_path: Path, output_dir: Path) -> list[AudioChunk]:
                    first = output_dir / "chunk000.mp3"
                    second = output_dir / "chunk001.mp3"
                    first.write_bytes(b"first")
                    second.write_bytes(b"second")
                    return [AudioChunk(first, 0, 0, 5), AudioChunk(second, 1, 5, 10)]

            def transcribe_one(audio_path: Path, output_path: Path, _model: str | None, _language: str | None) -> None:
                attempts[audio_path.name] = attempts.get(audio_path.name, 0) + 1
                if audio_path.name == "chunk000.mp3" and attempts[audio_path.name] == 1:
                    try:
                        raise providers.requests.Timeout("temporary")
                    except providers.requests.Timeout as exc:
                        raise ProviderError("temporary") from exc
                if audio_path.name == "chunk001.mp3":
                    raise ProviderError("permanent")
                write_srt(output_path, [providers.Cue(index=1, start_ms=0, end_ms=1000, text="hello")])

            stderr = StringIO()
            with patch.object(providers, "AudioSplitter", FakeAudioSplitter), patch("sys.stderr", stderr):
                with patch.object(providers.time, "sleep", lambda _delay: None):
                    with self.assertRaisesRegex(RuntimeError, "chunk 1"):
                        transcribe_with_splitter(transcribe_one, audio, output, None, None, SplitterConfig(target_chunk_duration=10, overlap_duration=1))

            self.assertEqual(2, attempts["chunk000.mp3"])
            self.assertEqual(1, attempts["chunk001.mp3"])
            self.assertFalse(output.exists())
            self.assertIn('CHUNK status="FAIL" index="2" total="2"', stderr.getvalue())


class VertexGeminiProviderTests(unittest.TestCase):
    def test_vertex_gemini_provider_is_registered_and_discoverable(self) -> None:
        provider = get_provider("vertex-gemini")
        payload = json.loads(list_providers())

        self.assertEqual("vertex-gemini", provider.name)
        self.assertEqual("gemini-2.5-flash", provider.default_model)
        self.assertEqual(("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"), provider.required_env_vars)
        self.assertEqual("gemini-2.5-flash", payload["vertex-gemini"]["default_model"])
        self.assertEqual(["gemini-2.5-flash", "gemini-2.5-pro"], payload["vertex-gemini"]["models"])
        self.assertEqual("gemini-2.5-pro", provider.models["gemini-2.5-pro"])

    def test_vertex_gemini_result_to_cues_parses_segments(self) -> None:
        cues = vertex_gemini_result_to_cues(
            {"segments": [{"start": 1.25, "end": 2.5, "text": "Bonjour"}, {"start": 2.5, "end": 4, "text": "le monde"}]}
        )

        self.assertEqual(2, len(cues))
        self.assertEqual(1250, cues[0].start_ms)
        self.assertEqual(2500, cues[0].end_ms)
        self.assertEqual("Bonjour", cues[0].text)
        self.assertEqual(2500, cues[1].start_ms)

    def test_vertex_gemini_result_to_cues_rejects_missing_segments(self) -> None:
        with self.assertRaisesRegex(ProviderError, "no timestamped transcription segments"):
            vertex_gemini_result_to_cues({"segments": []})

    def test_vertex_gemini_result_to_cues_rejects_invalid_timestamp(self) -> None:
        with self.assertRaisesRegex(ProviderError, "invalid start timestamp"):
            vertex_gemini_result_to_cues({"segments": [{"start": "soon", "end": 2, "text": "hello"}]})

    def test_vertex_gemini_result_to_cues_rejects_non_positive_duration(self) -> None:
        with self.assertRaisesRegex(ProviderError, "non-positive-duration"):
            vertex_gemini_result_to_cues({"segments": [{"start": 2, "end": 2, "text": "hello"}]})

    def test_vertex_gemini_result_to_cues_rejects_out_of_order_segments(self) -> None:
        with self.assertRaisesRegex(ProviderError, "out-of-order"):
            vertex_gemini_result_to_cues(
                {"segments": [{"start": 2, "end": 3, "text": "first"}, {"start": 1, "end": 2, "text": "second"}]}
            )


class SherpaParakeetProviderTests(unittest.TestCase):
    def test_sherpa_parakeet_provider_is_registered_and_discoverable(self) -> None:
        provider = providers.SherpaParakeetProvider()
        payload = json.loads(list_providers())

        self.assertEqual("sherpa-parakeet", provider.name)
        self.assertEqual(SHERPA_PARAKEET_MODEL_KEY, provider.default_model)
        self.assertEqual((), provider.required_env_vars)
        self.assertEqual(SHERPA_PARAKEET_MODEL_KEY, payload["sherpa-parakeet"]["default_model"])
        self.assertEqual([SHERPA_PARAKEET_MODEL_KEY], payload["sherpa-parakeet"]["models"])

    def test_sherpa_parakeet_model_cache_reuses_valid_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / providers.SHERPA_PARAKEET_MODEL_DIRNAME
            model_dir.mkdir()
            for filename in providers.SHERPA_PARAKEET_REQUIRED_FILES:
                (model_dir / filename).write_text("asset", encoding="utf-8")

            result = ensure_sherpa_parakeet_model(get_env={providers.SHERPA_PARAKEET_CACHE_ENV: tmpdir}.get, request_get=self._unexpected_get)

            self.assertEqual(model_dir, result)
            self.assertTrue(sherpa_parakeet_model_is_valid(result))

    def test_sherpa_parakeet_model_cache_downloads_missing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            response = FakeResponse(_model_archive_bytes())

            result = ensure_sherpa_parakeet_model(
                get_env={providers.SHERPA_PARAKEET_CACHE_ENV: tmpdir}.get,
                request_get=lambda *_args, **_kwargs: response,
            )

            self.assertTrue(sherpa_parakeet_model_is_valid(result))
            self.assertTrue(response.iterated)

    def test_sherpa_result_to_cues_parses_token_timestamps(self) -> None:
        result = types.SimpleNamespace(
            text="Hello world. Again.",
            tokens=[" Hello", " world", ".", " Again", "."],
            timestamps=[0.0, 0.4, 0.8, 1.2, 1.6],
        )

        cues = sherpa_result_to_cues(result)

        self.assertEqual(2, len(cues))
        self.assertEqual(0, cues[0].start_ms)
        self.assertEqual(1200, cues[0].end_ms)
        self.assertEqual("Hello world.", cues[0].text)
        self.assertEqual("Again.", cues[1].text)

    def test_sherpa_runtime_candidates_respects_override_with_cpu_fallback(self) -> None:
        candidates = sherpa_runtime_candidates(get_env={providers.SHERPA_ONNX_PROVIDER_ENV: "coreml"}.get)

        self.assertEqual(["coreml", "cpu"], candidates)

    def test_sherpa_transcription_falls_back_to_cpu_and_ignores_language(self) -> None:
        calls: list[str] = []

        class FakeRecognizer:
            def create_stream(self) -> object:
                return FakeStream()

            def decode_stream(self, _stream: object) -> None:
                return None

        class FakeStream:
            result = types.SimpleNamespace(text="Hello.", tokens=[" Hello", "."], timestamps=[0.0, 0.5])

            def accept_waveform(self, _sample_rate: int, _samples: object) -> None:
                return None

        class FakeOfflineRecognizer:
            @staticmethod
            def from_transducer(**kwargs: object) -> FakeRecognizer:
                provider = str(kwargs.get("provider", "cpu"))
                calls.append(provider)
                if provider != "cpu":
                    raise RuntimeError("accelerator unavailable")
                return FakeRecognizer()

        fake_sherpa = types.SimpleNamespace(OfflineRecognizer=FakeOfflineRecognizer)
        fake_numpy = types.SimpleNamespace()
        stderr = StringIO()
        with patch.dict(sys.modules, {"sherpa_onnx": fake_sherpa, "numpy": fake_numpy}):
            with patch.object(providers, "sherpa_runtime_candidates", lambda: ["cuda", "cpu"]):
                with patch.object(providers, "read_sherpa_wave", lambda *_args: (object(), 16000)):
                    with patch("sys.stderr", stderr):
                        cues = providers.transcribe_sherpa_parakeet_wav(Path("audio.wav"), Path("audio.wav"))

        self.assertEqual(["cuda", "cpu"], calls)
        self.assertEqual("Hello.", cues[0].text)
        self.assertIn("sherpa-parakeet selected CPU runtime", stderr.getvalue())

    def test_sherpa_provider_transcribe_ignores_language_argument(self) -> None:
        provider = providers.SherpaParakeetProvider()
        with tempfile.TemporaryDirectory() as tmpdir:
            audio = Path(tmpdir) / "audio.mp3"
            output = Path(tmpdir) / "out.srt"
            audio.write_bytes(b"audio")
            with patch.object(providers, "ensure_sherpa_parakeet_model", lambda *_args, **_kwargs: Path(tmpdir)):
                with patch.object(providers, "prepare_sherpa_audio", lambda *_args, **_kwargs: None):
                    with patch.object(providers, "transcribe_sherpa_parakeet_wav", lambda *_args, **_kwargs: [providers.Cue(index=1, start_ms=0, end_ms=1000, text="hello")]):
                        provider.transcribe(audio, output, None, "fr")

            self.assertTrue(output.exists())

    def _unexpected_get(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("download should not be attempted")


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.iterated = False

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int) -> list[bytes]:
        self.iterated = True
        return [self.payload[index : index + chunk_size] for index in range(0, len(self.payload), chunk_size)]


def _model_archive_bytes() -> bytes:
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as archive:
        for filename in providers.SHERPA_PARAKEET_REQUIRED_FILES:
            data = b"asset"
            info = tarfile.TarInfo(f"{providers.SHERPA_PARAKEET_MODEL_DIRNAME}/{filename}")
            info.size = len(data)
            archive.addfile(info, BytesIO(data))
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
