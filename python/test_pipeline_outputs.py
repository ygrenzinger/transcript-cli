from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

import transcribe
from srt import Cue, write_srt


@dataclass(frozen=True)
class FakeProvider:
    name: str = "fake"
    models: dict[str, str] = None  # type: ignore[assignment]
    default_model: str = "fake-model"
    env_var: str = "FAKE_API_KEY"

    def __post_init__(self) -> None:
        if self.models is None:
            object.__setattr__(self, "models", {"fake-model": "fake-model"})


class PipelineOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_extract_audio = transcribe.extract_audio
        self._original_validate_provider_ready = transcribe.validate_provider_ready
        self._original_resolve_model = transcribe.resolve_model
        self._original_transcribe_with_retries = transcribe.transcribe_with_retries

    def tearDown(self) -> None:
        transcribe.extract_audio = self._original_extract_audio
        transcribe.validate_provider_ready = self._original_validate_provider_ready
        transcribe.resolve_model = self._original_resolve_model
        transcribe.transcribe_with_retries = self._original_transcribe_with_retries

    def test_raw_only_pipeline_returns_provider_raw_srt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "clip.mp4"
            video.write_bytes(b"video")
            self._stub_pipeline(video)

            output = transcribe.run_pipeline(video, "fake", None, None, False)

            self.assertEqual(video.with_suffix(".fake.raw.srt"), output)
            self.assertTrue(output.exists())
            self.assertFalse(video.with_suffix(".mp3").exists())
            self.assertFalse(video.with_suffix(".fake.improved.srt").exists())

    def test_improved_pipeline_writes_provider_improved_srt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "clip.mp4"
            video.write_bytes(b"video")
            self._stub_pipeline(video)

            output = transcribe.run_pipeline(video, "fake", None, None, True)

            self.assertEqual(video.with_suffix(".fake.improved.srt"), output)
            self.assertTrue(video.with_suffix(".fake.raw.srt").exists())
            self.assertTrue(output.exists())
            self.assertFalse(video.with_suffix(".mp3").exists())

    def test_pipeline_keeps_audio_when_transcription_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "clip.mp4"
            video.write_bytes(b"video")
            self._stub_pipeline(video, transcribe_failure=True)

            with self.assertRaises(RuntimeError):
                transcribe.run_pipeline(video, "fake", None, None, False)

            self.assertTrue(video.with_suffix(".mp3").exists())
            self.assertFalse(video.with_suffix(".fake.raw.srt").exists())

    def _stub_pipeline(self, video: Path, transcribe_failure: bool = False) -> None:
        provider = FakeProvider()

        def extract_audio(_: Path) -> Path:
            audio = video.with_suffix(".mp3")
            audio.write_bytes(b"audio")
            return audio

        def transcribe_with_retries(*args: object) -> None:
            if transcribe_failure:
                raise RuntimeError("transcription failed")
            output_path = args[2]
            assert isinstance(output_path, Path)
            write_srt(output_path, [Cue(index=1, start_ms=0, end_ms=1000, text="hello")])

        transcribe.extract_audio = extract_audio
        transcribe.validate_provider_ready = lambda *_: provider
        transcribe.resolve_model = lambda *_: provider.default_model
        transcribe.transcribe_with_retries = transcribe_with_retries


if __name__ == "__main__":
    unittest.main()
