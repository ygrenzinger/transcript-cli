# Video To SRT

Python tool for transcribing videos to standardized SRT files.

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

Extract audio, transcribe, validate, and standardize in one command:

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

Write the final SRT to a custom path:

```bash
uv run video-to-srt --provider voxtral --output "/path/to/output.srt" "/path/to/video.mkv"
```

Outputs:

- Cached audio: `/path/to/video.mp3`
- Raw provider SRT: `/path/to/video.<provider>.raw.srt`
- Final standardized SRT: `/path/to/video.srt`

## Direct Script Usage

Only `transcribe.py` is intended to be run directly:

```bash
./transcribe.py --provider grok "/path/to/video.mkv"
```
