# Spec Traceability

| OpenSpec capability | Go implementation | Go tests | Status |
| --- | --- | --- | --- |
| `audio-extraction` | `internal/audio` | `internal/audio/audio_test.go` | ffmpeg subprocess extraction, cache hit, missing input, failure cleanup |
| `audio-to-srt-transcription` provider contract/selection/discovery/retry | `internal/provider` | `internal/provider/provider_test.go` | registry, model/env validation, discoverability JSON, retry policy, Grok HTTP, conversion helpers |
| `audio-to-srt-transcription` Voxtral | `internal/provider.VoxtralProvider` | `provider_test.go` metadata coverage | Provider boundary and metadata implemented; operational path uses Python reference bridge |
| `audio-to-srt-transcription` Grok | `internal/provider.GrokProvider` | `provider_test.go` | Direct HTTP implementation and cue conversion covered |
| `audio-to-srt-transcription` Vertex Gemini | `internal/provider.VertexGeminiProvider` | `provider_test.go` | Client boundary and response parsing covered; operational path uses Python reference bridge when no Go client is injected |
| `audio-to-srt-transcription` Sherpa Parakeet | `internal/provider.SherpaParakeetProvider` | `provider_test.go` | Cache, audio prep, runtime candidate, token/segment conversion covered; operational path uses Python reference bridge when no Go runtime is injected |
| `pipeline-orchestrator` | `internal/pipeline`, `cmd/video-to-srt` | `internal/pipeline/pipeline_test.go` | stage order, artifacts, progress, cleanup, failure behavior |
| `srt-validation` | `internal/srt` | `internal/srt/srt_test.go` | parseability, timestamps, encoding, indices, overlap, pure validation |
| `subtitle-improvement` | `internal/improve` | `internal/improve/improve_test.go` | invalid cue filtering, splitting, CPS/gap behavior, speaker labels, idempotence |
