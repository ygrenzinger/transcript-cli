# Video To SRT

Python tools for extracting audio from videos, transcribing audio to SRT, validating SRT files, and standardizing subtitle formatting.

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

Outputs:

- Cached audio: `/path/to/video.mp3`
- Raw provider SRT: `/path/to/video.<provider>.raw.srt`
- Final standardized SRT: `/path/to/video.srt`

## Individual Commands

Extract MP3 audio from a video:

```bash
uv run extract-audio "/path/to/video.mkv"
```

Transcribe an existing audio file:

```bash
uv run transcribe-srt --provider grok --output "/path/to/output.srt" "/path/to/audio.mp3"
```

List available transcription providers:

```bash
uv run transcribe-srt --list-providers
```

Validate an SRT file:

```bash
uv run validate-srt "/path/to/subtitles.srt"
```

Standardize an SRT file:

```bash
uv run standardize-srt "/path/to/input.srt" "/path/to/output.srt"
```

## Direct Script Usage

The scripts also have `uv` shebangs, so they can be run directly from this directory:

```bash
./pipeline.py --provider grok "/path/to/video.mkv"
./transcribe_grok.py --output "/path/to/output.srt" "/path/to/audio.mp3"
```
