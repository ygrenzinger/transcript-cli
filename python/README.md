# Video To SRT

Python tool for transcribing videos to raw SRT files, with optional subtitle improvement.

## Setup

Run commands from this directory:

```bash
cd /Users/yannick.grenzinger/Downloads/transcrition/python
```

Install and sync dependencies with `uv`:

```bash
uv sync
```

## Environment

Grok transcription requires:

```bash
export XAI_API_KEY="..."
```

Voxtral transcription requires:

```bash
export MISTRAL_API_KEY="..."
```

## Full Video Pipeline

Extract audio and transcribe in one command:

```bash
uv run video-to-srt --provider grok "/path/to/video.mkv"
```

Use Voxtral instead:

```bash
uv run video-to-srt --provider voxtral "/path/to/video.mkv"
```

Specify a language when supported by the provider:

```bash
uv run video-to-srt --provider grok --language en "/path/to/video.mkv"
```

Improve subtitles for readability:

```bash
uv run video-to-srt --provider voxtral --improve-subtitles "/path/to/video.mkv"
```

Write improved subtitles to a custom path:

```bash
uv run video-to-srt --provider voxtral --improve-subtitles --output "/path/to/output.srt" "/path/to/video.mkv"
```

Outputs:

- Cached audio: `/path/to/video.mp3`
- Raw provider SRT: `/path/to/video.<provider>.raw.srt`
- Improved SRT, when requested: `/path/to/video.<provider>.improved.srt`

## Direct Script Usage

Only `transcribe.py` is intended to be run directly:

```bash
./transcribe.py --provider grok "/path/to/video.mkv"
```

Improve an existing raw SRT directly:

```bash
uv run improve-subtitles "/path/to/video.voxtral.raw.srt" "/path/to/video.voxtral.improved.srt"
```
