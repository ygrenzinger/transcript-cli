# Go video-to-srt

This directory contains the Go reimplementation of the Python `video-to-srt` tool. The Python implementation remains the reference while the Go version reaches and proves parity.

## Setup

- Go: latest stable release, module target `go 1.23`.
- External tools: `ffmpeg` must be installed and available on `PATH` for audio extraction and Sherpa audio preparation; `yt-dlp` is required when the input source is a YouTube URL.
- Test: `go test ./...`
- Build: `go build ./cmd/video-to-srt`

## CLI

```sh
go run ./cmd/video-to-srt --provider voxtral path/to/clip.mp4
go run ./cmd/video-to-srt --provider voxtral 'https://www.youtube.com/watch?v=abc123'
go run ./cmd/video-to-srt --provider grok --language fr --improve-subtitles path/to/clip.mp4
go run ./cmd/video-to-srt --provider vertex-gemini --model gemini-2.5-pro --improve-subtitles -o path/to/custom.srt path/to/clip.mp4
go run ./cmd/video-to-srt providers
```

The positional input can be an existing local video path or a supported YouTube URL. URL inputs are downloaded first, then outputs use the downloaded video's path. Outputs match the Python naming contract:

- Raw SRT: `<video>.<provider>.raw.srt`
- Improved SRT: `<video>.<provider>.improved.srt`, or `--output` when `--improve-subtitles` is set
- Extracted audio: `<video>.mp3`, removed after successful raw SRT creation

Progress is emitted to stderr as `PROGRESS` lines with `stage`, `name`, `status`, and contextual fields.

## Providers

- `voxtral`: default model `voxtral-mini-2602`, requires `MISTRAL_API_KEY`, invoked through the Python reference provider bridge.
- `grok`: default model `grok-transcribe-1`, requires `XAI_API_KEY`, implemented with direct HTTP multipart upload.
- `vertex-gemini`: models `gemini-2.5-flash` and `gemini-2.5-pro`, requires `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`; API calls are isolated behind a `VertexClient` adapter and default to the Python reference provider bridge.
- `sherpa-parakeet`: model `parakeet-tdt-0.6b-v3-int8`, no cloud credentials; cache/audio/runtime concerns are isolated behind provider boundaries and default to the Python reference provider bridge.

The Go code includes deterministic provider parsing, retry, cache, and runtime-boundary tests. The Python bridge keeps the current operational provider behavior available while the Go provider boundaries remain independently testable.
