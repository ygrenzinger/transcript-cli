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

Some providers split long audio internally before transcription. This is provider-owned behavior and is not exposed as a pipeline CLI option. Current defaults: `vertex-gemini` uses 15-minute chunks, `sherpa-parakeet` uses 120-second chunks with 15-second overlap, and `grok`/`voxtral` do not use chunking. Temporary chunks and per-chunk SRT files are removed by the provider after the merged raw SRT is written successfully.

## Providers

- `voxtral`: default model `voxtral-mini-2602`, requires `MISTRAL_API_KEY`, implemented with direct Mistral HTTP multipart upload.
- `grok`: default model `grok-transcribe-1`, requires `XAI_API_KEY`, implemented with direct HTTP multipart upload.
- `vertex-gemini`: models `gemini-2.5-flash` and `gemini-2.5-pro`, requires `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`; API calls are isolated behind a native `VertexClient` adapter.
- `sherpa-parakeet`: model `parakeet-tdt-0.6b-v3-int8`, no cloud credentials; downloads the model cache automatically and uses `github.com/k2-fsa/sherpa-onnx-go` for local recognition.

The Go CLI no longer shells out to the Python reference providers. Voxtral and Grok are operational native HTTP providers; Vertex Gemini still requires a native client adapter to be injected before use.
