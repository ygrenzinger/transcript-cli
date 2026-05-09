## Context

The current pipeline starts with a `Path` and derives all output artifacts from that path:

```
local video path
      |
      v
extract_audio -> transcribe -> optional improve -> optional validate
      |
      v
<video>.<provider>.raw.srt / <video>.<provider>.improved.srt
```

YouTube support adds a source-resolution step before the existing pipeline. The rest of the pipeline should continue to operate on a local video file.

```
user input
  |
  +-- local path -----------+
  |                         |
  +-- YouTube URL -> yt-dlp-+
                            v
                     local video path
                            |
                            v
                   existing pipeline stages
```

## Decisions

### Source Resolution Boundary

Introduce a source ingestion boundary before audio extraction. It resolves the positional CLI input into a local video path and returns that path to the orchestrator.

This avoids teaching `audio-extraction` about URLs and keeps provider code unchanged.

### URL Detection

Treat inputs with `http://` or `https://` schemes and a recognized YouTube host (`youtube.com`, `www.youtube.com`, `youtu.be`, or `m.youtube.com`) as YouTube URLs. All other inputs are treated as local paths.

Unsupported HTTP(S) URLs should fail before invoking `yt-dlp` with a clear message that only YouTube URLs are supported.

### Download Behavior

For a YouTube URL, invoke `yt-dlp` as an external executable. The command should be non-interactive and produce exactly one local video file path that can be passed to the existing pipeline.

The implementation should prefer a deterministic output template in the current working directory or an existing output directory option if the CLI later grows one. The downloaded file's stem becomes the basis for raw and improved SRT names.

### Failure Behavior

If `yt-dlp` is missing or exits non-zero, the run fails before audio extraction starts. The error should mention that the YouTube download failed and include enough context for the user to act.

### Cleanup

The downloaded video is an input artifact, not an intermediate audio artifact. The initial implementation may preserve it so users can inspect or reuse it. If automatic cleanup is desired later, it should be controlled explicitly to avoid surprising deletion of a large file the user may expect to keep.

## Risks

- `yt-dlp` output filenames can contain characters that are awkward in shell usage. Use `subprocess` argument arrays and `Path` handling, not shell strings.
- YouTube titles can collide. The downloader should use a template that includes the video id or otherwise avoids overwriting unrelated downloads.
- Some videos require authentication, cookies, or age verification. These should surface as download failures rather than partially running the pipeline.
- Downloaded filenames determine SRT filenames, so tests should avoid depending on real YouTube metadata.
