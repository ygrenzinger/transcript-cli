from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audio_splitter import AudioChunk, AudioSplitter, SilencePoint, SplitterConfig, merge_chunk_srts, offset_cues
from srt import Cue, parse_srt, write_srt


class FakeSplitter(AudioSplitter):
    def __init__(self, duration: float, silences: list[SilencePoint] | None = None, config: SplitterConfig | None = None):
        super().__init__(config)
        self.duration = duration
        self.silences = silences or []
        self.extractions: list[tuple[Path, float, float]] = []

    def get_audio_duration(self, audio_path: Path) -> float:
        return self.duration

    def detect_silences(self, audio_path: Path) -> list[SilencePoint]:
        return self.silences

    def extract_chunk(self, source: Path, dest: Path, start: float, end: float) -> None:
        self.extractions.append((dest, start, end))
        dest.write_bytes(b"chunk")


class AudioSplitterTests(unittest.TestCase):
    def test_split_points_prefer_silence_and_fallback_to_target(self) -> None:
        splitter = AudioSplitter(SplitterConfig(target_chunk_duration=100, overlap_duration=10, search_window=20))

        points = splitter.calculate_split_points(260, [SilencePoint(92, 96, 4)])

        self.assertEqual([94, 194], points)

    def test_split_audio_returns_original_for_short_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio = Path(tmpdir) / "audio.mp3"
            audio.write_bytes(b"audio")
            splitter = FakeSplitter(50, config=SplitterConfig(target_chunk_duration=100, overlap_duration=10))

            chunks = splitter.split_audio(audio, Path(tmpdir) / "chunks")

            self.assertEqual([AudioChunk(audio, 0, 0, 50)], chunks)
            self.assertEqual([], splitter.extractions)

    def test_split_audio_clamps_overlap_at_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio = Path(tmpdir) / "audio.mp3"
            audio.write_bytes(b"audio")
            splitter = FakeSplitter(260, [SilencePoint(98, 102, 4), SilencePoint(198, 202, 4)], SplitterConfig(target_chunk_duration=100, overlap_duration=10, search_window=20))

            chunks = splitter.split_audio(audio, Path(tmpdir) / "chunks")

            self.assertEqual(3, len(chunks))
            self.assertEqual(0, chunks[0].start_time)
            self.assertEqual(10, chunks[0].overlap_end)
            self.assertEqual(10, chunks[1].overlap_start)
            self.assertEqual(10, chunks[1].overlap_end)
            self.assertEqual(260, chunks[-1].end_time)
            self.assertEqual(0, chunks[-1].overlap_end)

    def test_offset_and_merge_srts_deduplicates_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            first = Path(tmpdir) / "first.srt"
            second = Path(tmpdir) / "second.srt"
            output = Path(tmpdir) / "merged.srt"
            write_srt(first, [Cue(1, 0, 1000, "hello"), Cue(2, 4000, 5000, "same words")])
            write_srt(second, [Cue(1, 0, 1000, "same words"), Cue(2, 2000, 3000, "after")])
            chunks = [AudioChunk(first, 0, 0, 5, overlap_end=2), AudioChunk(second, 1, 4, 8, overlap_start=2)]

            merge_chunk_srts(chunks, [first, second], output)

            cues = parse_srt(output)
            self.assertEqual(["hello", "after"], [cue.text for cue in cues])
            self.assertEqual([1, 2], [cue.index for cue in cues])
            self.assertEqual(6000, cues[1].start_ms)

    def test_offset_cues_applies_chunk_start(self) -> None:
        cues = offset_cues([Cue(1, 100, 900, "hello")], 2.5)

        self.assertEqual(2600, cues[0].start_ms)
        self.assertEqual(3400, cues[0].end_ms)


if __name__ == "__main__":
    unittest.main()
