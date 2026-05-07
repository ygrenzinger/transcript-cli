import tempfile
import sys
from pathlib import Path

from moviepy import VideoFileClip


def extract_audio(video_path: Path | str, output_path: Path | str | None = None) -> Path:
    video = Path(video_path)
    if not video.exists():
        raise RuntimeError(f"file not found: {video_path}")

    out = Path(output_path) if output_path else video.with_suffix(".mp3")
    if out.exists() and out.stat().st_size > 0:
        print(f"Using cached audio: {out}", file=sys.stderr)
        return out

    clip = None
    temp_path = None
    try:
        clip = VideoFileClip(str(video))
        if clip.audio is None:
            raise RuntimeError("video has no audio track")
        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".mp3", dir=out.parent, delete=False) as temp:
            temp_path = Path(temp.name)
        clip.audio.write_audiofile(str(temp_path))
        if temp_path.stat().st_size == 0:
            raise RuntimeError("extracted audio file is empty")
        temp_path.replace(out)
        return out
    finally:
        if clip is not None:
            clip.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit("extract_audio.py is internal; run transcribe.py instead")
