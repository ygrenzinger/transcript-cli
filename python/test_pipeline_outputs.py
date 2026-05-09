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
    required_env_vars: tuple[str, ...] = ("FAKE_API_KEY",)

    def __post_init__(self) -> None:
        if self.models is None:
            object.__setattr__(self, "models", {"fake-model": "fake-model"})


class PipelineOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_extract_audio = transcribe.extract_audio
        self._original_validate_provider_ready = transcribe.validate_provider_ready
        self._original_resolve_model = transcribe.resolve_model
        self._original_transcribe_with_retries = transcribe.transcribe_with_retries
        self._original_download_youtube_video = transcribe.download_youtube_video
        self._original_shutil_which = transcribe.shutil.which
        self._original_subprocess_run = transcribe.subprocess.run

    def tearDown(self) -> None:
        transcribe.extract_audio = self._original_extract_audio
        transcribe.validate_provider_ready = self._original_validate_provider_ready
        transcribe.resolve_model = self._original_resolve_model
        transcribe.transcribe_with_retries = self._original_transcribe_with_retries
        transcribe.download_youtube_video = self._original_download_youtube_video
        transcribe.shutil.which = self._original_shutil_which
        transcribe.subprocess.run = self._original_subprocess_run

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

    def test_vertex_gemini_pipeline_uses_provider_name_for_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "clip.mp4"
            video.write_bytes(b"video")
            self._stub_pipeline(video, provider=FakeProvider(name="vertex-gemini", default_model="gemini-2.5-flash"))

            output = transcribe.run_pipeline(video, "vertex-gemini", None, None, True)

            self.assertEqual(video.with_suffix(".vertex-gemini.improved.srt"), output)
            self.assertTrue(video.with_suffix(".vertex-gemini.raw.srt").exists())
            self.assertFalse(video.with_suffix(".mp3").exists())

    def test_resolve_input_source_returns_existing_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            video = Path(tmpdir) / "clip.mp4"
            video.write_bytes(b"video")
            transcribe.download_youtube_video = self._fail_download

            self.assertEqual(video, transcribe.resolve_input_source(video))

    def test_main_downloads_youtube_url_then_runs_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            downloaded = Path(tmpdir) / "Downloaded Title [abc123].mp4"
            downloaded.write_bytes(b"video")
            self._stub_pipeline(downloaded)
            downloaded_urls: list[str] = []

            def download_youtube_video(url: str, download_dir: Path | None = None) -> Path:
                downloaded_urls.append(url)
                return downloaded

            transcribe.download_youtube_video = download_youtube_video

            status = transcribe.main(["https://www.youtube.com/watch?v=abc123", "--provider", "fake"])

            self.assertEqual(0, status)
            self.assertEqual(["https://www.youtube.com/watch?v=abc123"], downloaded_urls)
            self.assertTrue(downloaded.with_suffix(".fake.raw.srt").exists())
            self.assertFalse(downloaded.with_suffix(".mp3").exists())

    def test_resolve_input_source_rejects_unsupported_http_url(self) -> None:
        transcribe.download_youtube_video = self._fail_download

        with self.assertRaisesRegex(RuntimeError, "only local video files and YouTube URLs are supported"):
            transcribe.resolve_input_source("https://example.com/video.mp4")

    def test_youtube_download_requires_ytdlp(self) -> None:
        transcribe.shutil.which = lambda _: None

        with self.assertRaisesRegex(RuntimeError, "yt-dlp is required for YouTube URLs"):
            transcribe.download_youtube_video("https://youtu.be/abc123")

    def test_youtube_download_failure_reports_error(self) -> None:
        transcribe.shutil.which = lambda _: "/usr/local/bin/yt-dlp"

        def run(*_: object, **__: object) -> object:
            raise transcribe.subprocess.CalledProcessError(1, ["yt-dlp"], stderr="network failed")

        transcribe.subprocess.run = run

        with self.assertRaisesRegex(RuntimeError, "YouTube download failed: network failed"):
            transcribe.download_youtube_video("https://youtu.be/abc123")

    def test_youtube_download_failure_prevents_pipeline_stages(self) -> None:
        extracted: list[Path] = []
        transcribe.download_youtube_video = lambda *_: (_ for _ in ()).throw(RuntimeError("YouTube download failed"))
        transcribe.extract_audio = lambda video: extracted.append(video) or video.with_suffix(".mp3")

        status = transcribe.main(["https://youtu.be/abc123", "--provider", "fake"])

        self.assertEqual(1, status)
        self.assertEqual([], extracted)

    def _fail_download(self, *_: object) -> Path:
        raise AssertionError("yt-dlp should not be invoked")

    def _stub_pipeline(self, video: Path, transcribe_failure: bool = False, provider: FakeProvider | None = None) -> None:
        provider = provider or FakeProvider()

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
