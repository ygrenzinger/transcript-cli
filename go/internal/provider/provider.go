package provider

import (
	"archive/tar"
	"compress/bzip2"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"mime/multipart"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"time"

	sherpa "github.com/k2-fsa/sherpa-onnx-go/sherpa_onnx"

	"video-to-srt/internal/audio"
	"video-to-srt/internal/srt"
)

const (
	SherpaParakeetModelKey     = "parakeet-tdt-0.6b-v3-int8"
	SherpaParakeetModelDirname = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
	SherpaParakeetModelURL     = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2"
	SherpaParakeetCacheEnv     = "SHERPA_ONNX_PARAKEET_CACHE_DIR"
	SherpaONNXProviderEnv      = "SHERPA_ONNX_PROVIDER"
	SherpaONNXNumThreadsEnv    = "SHERPA_ONNX_NUM_THREADS"
)

var SherpaParakeetRequiredFiles = []string{"encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"}
var RetryDelays = []time.Duration{time.Second, 2 * time.Second, 4 * time.Second}

type Error struct {
	Message    string
	StatusCode int
	RetryAfter string
	Transient  bool
	Err        error
}

func (e *Error) Error() string { return e.Message }
func (e *Error) Unwrap() error { return e.Err }

type Metadata struct {
	Name            string   `json:"-"`
	Models          []string `json:"models"`
	DefaultModel    string   `json:"default_model"`
	RequiredEnvVars []string `json:"required_env_vars,omitempty"`
}

type Provider interface {
	Metadata() Metadata
	Transcribe(ctx context.Context, audioPath, outputPath, model, language string) error
}

type Registry struct{ providers map[string]Provider }

func DefaultRegistry() *Registry {
	r := NewRegistry()
	geminiSplitter := audio.DefaultSplitterConfig()
	geminiSplitter.TargetChunkDuration = 900
	parakeetSplitter := audio.DefaultSplitterConfig()
	parakeetSplitter.TargetChunkDuration = 30
	parakeetSplitter.OverlapDuration = 5
	parakeetSplitter.SearchWindow = 5
	r.Register(VoxtralProvider{URL: "https://api.mistral.ai/v1/audio/transcriptions", Client: http.DefaultClient})
	r.Register(GrokProvider{URL: "https://api.x.ai/v1/stt", Client: http.DefaultClient})
	r.Register(VertexGeminiProvider{Splitter: &geminiSplitter})
	r.Register(SherpaParakeetProvider{ModelURL: SherpaParakeetModelURL, Runner: ExecRunner{}, Runtime: SherpaONNXRuntime{Getenv: os.Getenv}, Splitter: &parakeetSplitter})
	return r
}

func NewRegistry() *Registry { return &Registry{providers: map[string]Provider{}} }

func (r *Registry) Register(p Provider) { r.providers[p.Metadata().Name] = p }

func (r *Registry) Get(name string) (Provider, error) {
	if p, ok := r.providers[name]; ok {
		return p, nil
	}
	return nil, &Error{Message: fmt.Sprintf("unknown provider '%s'. Available providers: %s", name, strings.Join(r.Names(), ", "))}
}

func (r *Registry) Names() []string {
	names := make([]string, 0, len(r.providers))
	for name := range r.providers {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func (r *Registry) ValidateReady(name, model string, getenv func(string) string) (Provider, string, error) {
	p, err := r.Get(name)
	if err != nil {
		return nil, "", err
	}
	resolved, err := ResolveModel(p.Metadata(), model)
	if err != nil {
		return nil, "", err
	}
	if getenv == nil {
		getenv = os.Getenv
	}
	for _, key := range p.Metadata().RequiredEnvVars {
		if getenv(key) == "" {
			return nil, "", &Error{Message: "missing required environment variable: " + key}
		}
	}
	return p, resolved, nil
}

func ResolveModel(meta Metadata, model string) (string, error) {
	key := model
	if key == "" {
		key = meta.DefaultModel
	}
	for _, available := range meta.Models {
		if key == available {
			return key, nil
		}
	}
	return "", &Error{Message: fmt.Sprintf("unsupported model '%s' for provider '%s'. Available models: %s", key, meta.Name, strings.Join(meta.Models, ", "))}
}

func (r *Registry) ListJSON() (string, error) {
	type payload struct {
		DefaultModel string   `json:"default_model"`
		Models       []string `json:"models"`
	}
	out := map[string]payload{}
	for _, name := range r.Names() {
		meta := r.providers[name].Metadata()
		models := append([]string(nil), meta.Models...)
		sort.Strings(models)
		out[name] = payload{DefaultModel: meta.DefaultModel, Models: models}
	}
	data, err := json.MarshalIndent(out, "", "  ")
	return string(data), err
}

type Sleeper func(time.Duration)

type SingleTranscriber func(ctx context.Context, audioPath, outputPath, model, language string) error

func TranscribeWithRetries(ctx context.Context, p Provider, audioPath, outputPath, model, language string, sleep Sleeper) error {
	if sleep == nil {
		sleep = time.Sleep
	}
	for attempt := 0; ; attempt++ {
		err := p.Transcribe(ctx, audioPath, outputPath, model, language)
		if err == nil {
			return nil
		}
		if attempt == len(RetryDelays) || !IsRetryable(err) {
			return err
		}
		sleep(RetryDelay(err, RetryDelays[attempt], time.Now))
	}
}

func TranscribeOneWithRetries(ctx context.Context, transcribeOne SingleTranscriber, audioPath, outputPath, model, language string, sleep Sleeper) error {
	if sleep == nil {
		sleep = time.Sleep
	}
	for attempt := 0; ; attempt++ {
		err := transcribeOne(ctx, audioPath, outputPath, model, language)
		if err == nil {
			return nil
		}
		if attempt == len(RetryDelays) || !IsRetryable(err) {
			return err
		}
		sleep(RetryDelay(err, RetryDelays[attempt], time.Now))
	}
}

func TranscribeWithSplitter(ctx context.Context, transcribeOne SingleTranscriber, audioPath, outputPath, model, language string, config audio.SplitterConfig, sleep Sleeper) error {
	if err := config.Validate(); err != nil {
		return err
	}
	workDir, err := os.MkdirTemp("", "video-to-srt-chunks-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(workDir)
	splitter, err := audio.NewSplitter(config, nil)
	if err != nil {
		return err
	}
	logProviderProgress("SPLIT", map[string]any{"status": "START", "input": audioPath, "target_chunk_seconds": config.TargetChunkDuration, "overlap_seconds": config.OverlapDuration})
	chunks, err := splitter.Split(ctx, audioPath, workDir)
	if err != nil {
		logProviderProgress("SPLIT", map[string]any{"status": "FAIL", "input": audioPath, "error": fmt.Sprintf("%T", err)})
		return err
	}
	logProviderProgress("SPLIT", map[string]any{"status": "DONE", "input": audioPath, "chunks": len(chunks), "duration_seconds": chunkSetDuration(chunks)})
	if len(chunks) == 1 && chunks[0].Path == audioPath {
		logProviderProgress("SPLIT", map[string]any{"status": "SKIP", "input": audioPath, "reason": "below_chunk_capacity"})
		if err := TranscribeOneWithRetries(ctx, transcribeOne, audioPath, outputPath, model, language, sleep); err != nil {
			return &Error{Message: fmt.Sprintf("chunk transcription failed for %s: %v", audioPath, err)}
		}
		return nil
	}
	return TranscribeChunks(ctx, transcribeOne, chunks, outputPath, model, language, workDir, config.SimilarityThreshold, sleep)
}

func TranscribeChunks(ctx context.Context, transcribeOne SingleTranscriber, chunks []audio.Chunk, outputPath, model, language, workDir string, similarityThreshold float64, sleep Sleeper) error {
	srtPaths := make([]string, 0, len(chunks))
	for _, chunk := range chunks {
		chunkSRT := filepath.Join(workDir, fmt.Sprintf("chunk%03d.srt", chunk.Index))
		logProviderProgress("CHUNK", map[string]any{"status": "START", "index": chunk.Index + 1, "total": len(chunks), "input": chunk.Path, "start_seconds": chunk.StartTime, "end_seconds": chunk.EndTime})
		if err := TranscribeOneWithRetries(ctx, transcribeOne, chunk.Path, chunkSRT, model, language, sleep); err != nil {
			logProviderProgress("CHUNK", map[string]any{"status": "FAIL", "index": chunk.Index + 1, "total": len(chunks), "input": chunk.Path, "error": fmt.Sprintf("%T", err)})
			return &Error{Message: fmt.Sprintf("chunk transcription failed for chunk %d at %s: %v", chunk.Index, chunk.Path, err)}
		}
		logProviderProgress("CHUNK", map[string]any{"status": "DONE", "index": chunk.Index + 1, "total": len(chunks), "artifact": chunkSRT})
		srtPaths = append(srtPaths, chunkSRT)
	}
	logProviderProgress("MERGE", map[string]any{"status": "START", "chunks": len(chunks), "output": outputPath})
	if err := audio.MergeChunkSRTs(chunks, srtPaths, outputPath, similarityThreshold); err != nil {
		logProviderProgress("MERGE", map[string]any{"status": "FAIL", "chunks": len(chunks), "output": outputPath, "error": fmt.Sprintf("%T", err)})
		return err
	}
	logProviderProgress("MERGE", map[string]any{"status": "DONE", "chunks": len(chunks), "artifact": outputPath})
	return nil
}

func logProviderProgress(event string, fields map[string]any) {
	keys := providerLogKeys(fields)
	parts := make([]string, 0, len(keys))
	for _, key := range keys {
		parts = append(parts, fmt.Sprintf("%s=%s", key, formatProviderLogValue(fields[key])))
	}
	fmt.Fprintln(os.Stderr, event+" "+strings.Join(parts, " "))
}

func providerLogKeys(fields map[string]any) []string {
	keys := make([]string, 0, len(fields))
	for key := range fields {
		keys = append(keys, key)
	}
	order := map[string]int{"status": 0, "index": 1, "total": 2, "input": 3, "output": 4, "artifact": 5, "target_chunk_seconds": 6, "overlap_seconds": 7, "chunks": 8, "duration_seconds": 9, "start_seconds": 10, "end_seconds": 11, "reason": 12, "error": 13}
	sort.SliceStable(keys, func(i, j int) bool {
		return providerLogOrder(keys[i], order) < providerLogOrder(keys[j], order)
	})
	return keys
}

func providerLogOrder(key string, order map[string]int) int {
	if value, ok := order[key]; ok {
		return value
	}
	return 1000 + len(key)
}

func formatProviderLogValue(value any) string {
	escaped := strings.ReplaceAll(fmt.Sprint(value), `\`, `\\`)
	escaped = strings.ReplaceAll(escaped, `"`, `\"`)
	return `"` + escaped + `"`
}

func chunkSetDuration(chunks []audio.Chunk) float64 {
	duration := 0.0
	for _, chunk := range chunks {
		if chunk.EndTime > duration {
			duration = chunk.EndTime
		}
	}
	return duration
}

func IsRetryable(err error) bool {
	var pe *Error
	if errors.As(err, &pe) {
		return pe.Transient || pe.StatusCode == 429 || (pe.StatusCode >= 500 && pe.StatusCode <= 599)
	}
	return false
}

func RetryDelay(err error, def time.Duration, now func() time.Time) time.Duration {
	var pe *Error
	if !errors.As(err, &pe) || pe.StatusCode != 429 || pe.RetryAfter == "" {
		return def
	}
	if seconds, parseErr := strconv.ParseFloat(pe.RetryAfter, 64); parseErr == nil {
		if seconds < 0 {
			seconds = 0
		}
		return time.Duration(seconds * float64(time.Second))
	}
	if t, parseErr := http.ParseTime(pe.RetryAfter); parseErr == nil {
		d := t.Sub(now())
		if d < 0 {
			return 0
		}
		return d
	}
	return def
}

type GrokProvider struct {
	URL      string
	Client   *http.Client
	Splitter *audio.SplitterConfig
}

func (GrokProvider) Metadata() Metadata {
	return Metadata{Name: "grok", Models: []string{"grok-transcribe-1"}, DefaultModel: "grok-transcribe-1", RequiredEnvVars: []string{"XAI_API_KEY"}}
}

func (p GrokProvider) Transcribe(ctx context.Context, audioPath, outputPath, model, language string) error {
	if p.Splitter != nil {
		return TranscribeWithSplitter(ctx, p.transcribeSingle, audioPath, outputPath, model, language, *p.Splitter, nil)
	}
	return p.transcribeSingle(ctx, audioPath, outputPath, model, language)
}

func (p GrokProvider) transcribeSingle(ctx context.Context, audioPath, outputPath, model, language string) error {
	modelID, err := ResolveModel(p.Metadata(), model)
	if err != nil {
		return err
	}
	apiKey := os.Getenv("XAI_API_KEY")
	if apiKey == "" {
		return &Error{Message: "missing required environment variable: XAI_API_KEY"}
	}
	bodyReader, bodyWriter := io.Pipe()
	mw := multipart.NewWriter(bodyWriter)
	go func() {
		defer bodyWriter.Close()
		defer mw.Close()
		_ = mw.WriteField("model", modelID)
		_ = mw.WriteField("response_format", "verbose_json")
		_ = mw.WriteField("timestamp_granularities[]", "word")
		if language != "" {
			_ = mw.WriteField("language", language)
		}
		file, openErr := os.Open(audioPath)
		if openErr != nil {
			_ = bodyWriter.CloseWithError(openErr)
			return
		}
		defer file.Close()
		part, createErr := mw.CreateFormFile("file", filepath.Base(audioPath))
		if createErr != nil {
			_ = bodyWriter.CloseWithError(createErr)
			return
		}
		_, _ = io.Copy(part, file)
	}()
	client := p.Client
	if client == nil {
		client = http.DefaultClient
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, p.URL, bodyReader)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	resp, err := client.Do(req)
	if err != nil {
		return &Error{Message: "grok transcription failed: " + err.Error(), Transient: true, Err: err}
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		return &Error{Message: fmt.Sprintf("grok transcription failed: HTTP %d", resp.StatusCode), StatusCode: resp.StatusCode, RetryAfter: resp.Header.Get("Retry-After")}
	}
	var result map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return &Error{Message: "grok transcription response was not JSON", Err: err}
	}
	cues, err := GrokResultToCues(result)
	if err != nil {
		return err
	}
	return srt.AtomicWriteFile(outputPath, cues)
}

func GrokResultToCues(result map[string]any) ([]srt.Cue, error) {
	if raw, ok := result["segments"].([]any); ok {
		cues := []srt.Cue{}
		for _, item := range raw {
			segment, ok := item.(map[string]any)
			if !ok {
				continue
			}
			text := strings.TrimSpace(fmt.Sprint(segment["text"]))
			if text == "" || text == "<nil>" {
				continue
			}
			start, ok1 := numberMS(segment["start"])
			end, ok2 := numberMS(segment["end"])
			if !ok1 || !ok2 {
				return nil, &Error{Message: "grok returned a segment with invalid timestamp"}
			}
			speaker := ""
			if v, ok := segment["speaker"]; ok && v != nil {
				speaker = "Speaker " + fmt.Sprint(v)
			} else if v, ok := segment["speaker_id"]; ok && v != nil {
				speaker = "Speaker " + fmt.Sprint(v)
			}
			cues = append(cues, srt.Cue{Index: len(cues) + 1, StartMS: start, EndMS: end, Speaker: speaker, Text: text})
		}
		if len(cues) == 0 {
			return nil, &Error{Message: "grok returned no timestamped transcription cues"}
		}
		return cues, nil
	}
	if raw, ok := result["words"].([]any); ok {
		words := []map[string]any{}
		for _, item := range raw {
			if word, ok := item.(map[string]any); ok {
				words = append(words, word)
			}
		}
		cues := WordsToCues(words)
		if len(cues) == 0 {
			return nil, &Error{Message: "grok returned no timestamped transcription cues"}
		}
		return cues, nil
	}
	return nil, &Error{Message: "grok returned no timestamped transcription cues"}
}

func WordsToCues(words []map[string]any) []srt.Cue {
	cues := []srt.Cue{}
	current := []map[string]any{}
	flush := func() {
		if len(current) == 0 {
			return
		}
		cues = append(cues, cueFromWords(len(cues)+1, current))
		current = nil
	}
	for _, word := range words {
		text := strings.TrimSpace(firstString(word["word"], word["text"]))
		if text == "" {
			continue
		}
		word["text"] = text
		if len(current) > 0 {
			start, _ := numberSeconds(current[0]["start"])
			end, _ := numberSeconds(word["end"])
			speakerChanged := fmt.Sprint(word["speaker"]) != fmt.Sprint(current[0]["speaker"])
			tooLong := end-start > 7
			texts := []string{}
			for _, w := range append(current, word) {
				texts = append(texts, fmt.Sprint(w["text"]))
			}
			tooManyChars := len(strings.Join(texts, " ")) > 84
			sentenceDone := strings.HasSuffix(strings.TrimRight(fmt.Sprint(current[len(current)-1]["text"]), " "), ".") || strings.HasSuffix(fmt.Sprint(current[len(current)-1]["text"]), "?") || strings.HasSuffix(fmt.Sprint(current[len(current)-1]["text"]), "!")
			if speakerChanged || tooLong || tooManyChars || sentenceDone {
				flush()
			}
		}
		current = append(current, word)
	}
	flush()
	return cues
}

func cueFromWords(index int, words []map[string]any) srt.Cue {
	start, _ := numberMS(words[0]["start"])
	end, _ := numberMS(words[len(words)-1]["end"])
	texts := []string{}
	for _, word := range words {
		texts = append(texts, fmt.Sprint(word["text"]))
	}
	speaker := ""
	if v, ok := words[0]["speaker"]; ok && v != nil {
		speaker = "Speaker " + fmt.Sprint(v)
	}
	return srt.Cue{Index: index, StartMS: start, EndMS: end, Speaker: speaker, Text: strings.Join(texts, " ")}
}

type VoxtralProvider struct {
	URL    string
	Client *http.Client
}

func (VoxtralProvider) Metadata() Metadata {
	return Metadata{Name: "voxtral", Models: []string{"voxtral-mini-2602"}, DefaultModel: "voxtral-mini-2602", RequiredEnvVars: []string{"MISTRAL_API_KEY"}}
}

func (p VoxtralProvider) Transcribe(ctx context.Context, audioPath, outputPath, model, language string) error {
	modelID, err := ResolveModel(p.Metadata(), model)
	if err != nil {
		return err
	}
	apiKey := os.Getenv("MISTRAL_API_KEY")
	if apiKey == "" {
		return &Error{Message: "missing required environment variable: MISTRAL_API_KEY"}
	}
	bodyReader, bodyWriter := io.Pipe()
	mw := multipart.NewWriter(bodyWriter)
	go func() {
		defer bodyWriter.Close()
		defer mw.Close()
		_ = mw.WriteField("model", modelID)
		_ = mw.WriteField("timestamp_granularities", "segment")
		if language != "" {
			_ = mw.WriteField("language", language)
		}
		file, openErr := os.Open(audioPath)
		if openErr != nil {
			_ = bodyWriter.CloseWithError(openErr)
			return
		}
		defer file.Close()
		part, createErr := mw.CreateFormFile("file", filepath.Base(audioPath))
		if createErr != nil {
			_ = bodyWriter.CloseWithError(createErr)
			return
		}
		_, _ = io.Copy(part, file)
	}()
	client := p.Client
	if client == nil {
		client = http.DefaultClient
	}
	url := p.URL
	if url == "" {
		url = "https://api.mistral.ai/v1/audio/transcriptions"
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bodyReader)
	if err != nil {
		return err
	}
	req.Header.Set("x-api-key", apiKey)
	req.Header.Set("Content-Type", mw.FormDataContentType())
	resp, err := client.Do(req)
	if err != nil {
		return &Error{Message: "voxtral transcription failed: " + err.Error(), Transient: true, Err: err}
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		return &Error{Message: fmt.Sprintf("voxtral transcription failed: HTTP %d", resp.StatusCode), StatusCode: resp.StatusCode, RetryAfter: resp.Header.Get("Retry-After")}
	}
	var result map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return &Error{Message: "voxtral transcription response was not JSON", Err: err}
	}
	cues, err := VoxtralResultToCues(result)
	if err != nil {
		return err
	}
	return srt.AtomicWriteFile(outputPath, cues)
}

func VoxtralResultToCues(result map[string]any) ([]srt.Cue, error) {
	if raw, ok := result["segments"].([]any); ok {
		cues := []srt.Cue{}
		for _, item := range raw {
			segment, ok := item.(map[string]any)
			if !ok {
				continue
			}
			text := strings.TrimSpace(fmt.Sprint(segment["text"]))
			if text == "" || text == "<nil>" {
				continue
			}
			start, ok1 := numberMS(segment["start"])
			end, ok2 := numberMS(segment["end"])
			if !ok1 || !ok2 {
				return nil, &Error{Message: "voxtral returned a segment with invalid timestamp"}
			}
			if end <= start {
				return nil, &Error{Message: "voxtral returned a non-positive-duration segment"}
			}
			speaker := ""
			if v, ok := segment["speaker"]; ok && v != nil {
				speaker = "Speaker " + fmt.Sprint(v)
			} else if v, ok := segment["speaker_id"]; ok && v != nil {
				speaker = "Speaker " + fmt.Sprint(v)
			}
			cues = append(cues, srt.Cue{Index: len(cues) + 1, StartMS: start, EndMS: end, Speaker: speaker, Text: text})
		}
		if len(cues) > 0 {
			return cues, nil
		}
	}
	text := strings.TrimSpace(fmt.Sprint(result["text"]))
	if text == "" || text == "<nil>" {
		return nil, &Error{Message: "voxtral returned no transcription text"}
	}
	return []srt.Cue{{Index: 1, StartMS: 0, EndMS: max(1000, len(text)*1000/15), Text: text}}, nil
}

type VertexGeminiProvider struct {
	Client   VertexClient
	Splitter *audio.SplitterConfig
}
type VertexClient interface {
	Generate(ctx context.Context, audio []byte, model, language string) (any, error)
}

func (VertexGeminiProvider) Metadata() Metadata {
	return Metadata{Name: "vertex-gemini", Models: []string{"gemini-2.5-flash", "gemini-2.5-pro"}, DefaultModel: "gemini-2.5-flash", RequiredEnvVars: []string{"GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"}}
}

func (p VertexGeminiProvider) Transcribe(ctx context.Context, audioPath, outputPath, model, language string) error {
	if p.Client == nil {
		return &Error{Message: "vertex-gemini native client is not configured"}
	}
	if p.Splitter != nil {
		return TranscribeWithSplitter(ctx, p.transcribeSingle, audioPath, outputPath, model, language, *p.Splitter, nil)
	}
	return p.transcribeSingle(ctx, audioPath, outputPath, model, language)
}

func (p VertexGeminiProvider) transcribeSingle(ctx context.Context, audioPath, outputPath, model, language string) error {
	modelID, err := ResolveModel(p.Metadata(), model)
	if err != nil {
		return err
	}
	audio, err := os.ReadFile(audioPath)
	if err != nil {
		return err
	}
	response, err := p.Client.Generate(ctx, audio, modelID, language)
	if err != nil {
		return &Error{Message: "vertex-gemini transcription failed: " + err.Error(), Err: err}
	}
	cues, err := VertexGeminiResponseToCues(response)
	if err != nil {
		return err
	}
	return srt.AtomicWriteFile(outputPath, cues)
}

func VertexGeminiResponseToCues(response any) ([]srt.Cue, error) {
	switch v := response.(type) {
	case string:
		var result map[string]any
		if err := json.Unmarshal([]byte(strings.TrimSpace(v)), &result); err != nil {
			return nil, &Error{Message: "vertex-gemini transcription response was not JSON", Err: err}
		}
		return VertexGeminiResultToCues(result)
	case map[string]any:
		return VertexGeminiResultToCues(v)
	default:
		return nil, &Error{Message: "vertex-gemini transcription response had unexpected shape"}
	}
}

func VertexGeminiResultToCues(result map[string]any) ([]srt.Cue, error) {
	raw, ok := result["segments"].([]any)
	if !ok || len(raw) == 0 {
		return nil, &Error{Message: "vertex-gemini returned no timestamped transcription segments"}
	}
	cues := []srt.Cue{}
	previousStart := -1
	for _, item := range raw {
		segment, ok := item.(map[string]any)
		if !ok {
			return nil, &Error{Message: "vertex-gemini transcription segment had unexpected shape"}
		}
		text := strings.TrimSpace(fmt.Sprint(segment["text"]))
		if text == "" || text == "<nil>" {
			continue
		}
		start, ok1 := numberMS(segment["start"])
		end, ok2 := numberMS(segment["end"])
		if !ok1 {
			return nil, &Error{Message: "vertex-gemini returned a segment with invalid start timestamp"}
		}
		if !ok2 {
			return nil, &Error{Message: "vertex-gemini returned a segment with invalid end timestamp"}
		}
		if end <= start {
			return nil, &Error{Message: "vertex-gemini returned a non-positive-duration segment"}
		}
		if start < previousStart {
			return nil, &Error{Message: "vertex-gemini returned out-of-order segments"}
		}
		previousStart = start
		cues = append(cues, srt.Cue{Index: len(cues) + 1, StartMS: start, EndMS: end, Text: text})
	}
	if len(cues) == 0 {
		return nil, &Error{Message: "vertex-gemini returned no transcription text"}
	}
	return cues, nil
}

type CommandRunner interface {
	Run(ctx context.Context, name string, args ...string) error
}
type ExecRunner struct{}

func (ExecRunner) Run(ctx context.Context, name string, args ...string) error {
	return exec.CommandContext(ctx, name, args...).Run()
}

type SherpaParakeetProvider struct {
	ModelURL string
	Runner   CommandRunner
	Runtime  SherpaRuntime
	Splitter *audio.SplitterConfig
}
type SherpaRuntime interface {
	Recognize(ctx context.Context, modelDir, wavPath string) ([]srt.Cue, error)
}

type SherpaONNXRuntime struct {
	Getenv func(string) string
}

func (r SherpaONNXRuntime) Recognize(ctx context.Context, modelDir, wavPath string) ([]srt.Cue, error) {
	getenv := r.Getenv
	if getenv == nil {
		getenv = os.Getenv
	}
	wave := sherpa.ReadWave(wavPath)
	if wave == nil {
		return nil, fmt.Errorf("failed to read prepared WAV audio")
	}
	var lastErr error
	for _, runtimeProvider := range SherpaRuntimeCandidates(getenv) {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		cues, err := recognizeSherpaWave(modelDir, wave, runtimeProvider, SherpaNumThreads(getenv))
		if err == nil {
			return cues, nil
		}
		lastErr = err
		if runtimeProvider == "cpu" {
			break
		}
	}
	return nil, lastErr
}

func (SherpaParakeetProvider) Metadata() Metadata {
	return Metadata{Name: "sherpa-parakeet", Models: []string{SherpaParakeetModelKey}, DefaultModel: SherpaParakeetModelKey}
}

func (p SherpaParakeetProvider) Transcribe(ctx context.Context, audioPath, outputPath, model, language string) error {
	if p.Runtime == nil {
		return &Error{Message: "sherpa-parakeet native runtime is not configured"}
	}
	if p.Splitter != nil {
		return TranscribeWithSplitter(ctx, p.transcribeSingle, audioPath, outputPath, model, language, *p.Splitter, nil)
	}
	return p.transcribeSingle(ctx, audioPath, outputPath, model, language)
}

func (p SherpaParakeetProvider) transcribeSingle(ctx context.Context, audioPath, outputPath, model, language string) error {
	if _, err := ResolveModel(p.Metadata(), model); err != nil {
		return err
	}
	modelDir, err := EnsureSherpaParakeetModel(p.ModelURL, os.Getenv, http.DefaultClient)
	if err != nil {
		return err
	}
	tmp, err := os.MkdirTemp("", "sherpa-parakeet-")
	if err != nil {
		return err
	}
	defer os.RemoveAll(tmp)
	wav := filepath.Join(tmp, strings.TrimSuffix(filepath.Base(audioPath), filepath.Ext(audioPath))+".wav")
	if err := PrepareSherpaAudio(ctx, audioPath, wav, p.Runner); err != nil {
		return err
	}
	cues, err := p.Runtime.Recognize(ctx, modelDir, wav)
	if err != nil {
		return &Error{Message: "sherpa-parakeet transcription failed: " + err.Error(), Err: err}
	}
	return srt.AtomicWriteFile(outputPath, cues)
}

func SherpaParakeetCacheRoot(getenv func(string) string) string {
	if v := getenv(SherpaParakeetCacheEnv); v != "" {
		return expandHome(v)
	}
	if v := getenv("XDG_CACHE_HOME"); v != "" {
		return filepath.Join(expandHome(v), "video-to-srt")
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".cache", "video-to-srt")
}

func SherpaParakeetModelDir(getenv func(string) string) string {
	return filepath.Join(SherpaParakeetCacheRoot(getenv), SherpaParakeetModelDirname)
}

func EnsureSherpaParakeetModel(modelURL string, getenv func(string) string, client *http.Client) (string, error) {
	if modelURL == "" {
		modelURL = SherpaParakeetModelURL
	}
	modelDir := SherpaParakeetModelDir(getenv)
	if SherpaParakeetModelIsValid(modelDir) {
		return modelDir, nil
	}
	if err := os.MkdirAll(filepath.Dir(modelDir), 0o755); err != nil {
		return "", err
	}
	tmp, err := os.MkdirTemp(filepath.Dir(modelDir), "sherpa-parakeet-download-")
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(tmp)
	archivePath := filepath.Join(tmp, "model.tar.bz2")
	resp, err := client.Get(modelURL)
	if err != nil {
		return "", &Error{Message: "sherpa-parakeet model cache failed: " + err.Error(), Err: err}
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		return "", &Error{Message: fmt.Sprintf("sherpa-parakeet model cache failed: HTTP %d", resp.StatusCode), StatusCode: resp.StatusCode}
	}
	archive, err := os.Create(archivePath)
	if err != nil {
		return "", err
	}
	if _, err := io.Copy(archive, resp.Body); err != nil {
		archive.Close()
		return "", &Error{Message: "sherpa-parakeet model cache failed: " + err.Error(), Err: err}
	}
	archive.Close()
	if err := SafeExtractTarBZ2(archivePath, tmp); err != nil {
		return "", err
	}
	extracted := filepath.Join(tmp, SherpaParakeetModelDirname)
	if !SherpaParakeetModelIsValid(extracted) {
		return "", &Error{Message: "sherpa-parakeet model cache failed: downloaded archive missing required model files"}
	}
	_ = os.RemoveAll(modelDir)
	if err := os.Rename(extracted, modelDir); err != nil {
		return "", err
	}
	return modelDir, nil
}

func SherpaParakeetModelIsValid(modelDir string) bool {
	for _, name := range SherpaParakeetRequiredFiles {
		info, err := os.Stat(filepath.Join(modelDir, name))
		if err != nil || info.IsDir() {
			return false
		}
	}
	return true
}

func SafeExtractTarBZ2(archivePath, destination string) error {
	dest, _ := filepath.Abs(destination)
	file, err := os.Open(archivePath)
	if err != nil {
		return err
	}
	defer file.Close()
	tr := tar.NewReader(bzip2.NewReader(file))
	for {
		header, err := tr.Next()
		if errors.Is(err, io.EOF) {
			return nil
		}
		if err != nil {
			return &Error{Message: "sherpa-parakeet model cache failed: " + err.Error(), Err: err}
		}
		target, _ := filepath.Abs(filepath.Join(destination, header.Name))
		if target != dest && !strings.HasPrefix(target, dest+string(os.PathSeparator)) {
			return &Error{Message: "sherpa-parakeet model cache failed: archive contains unsafe paths"}
		}
		switch header.Typeflag {
		case tar.TypeDir:
			if err := os.MkdirAll(target, 0o755); err != nil {
				return err
			}
		case tar.TypeReg:
			if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
				return err
			}
			out, err := os.Create(target)
			if err != nil {
				return err
			}
			_, copyErr := io.Copy(out, tr)
			closeErr := out.Close()
			if copyErr != nil {
				return copyErr
			}
			if closeErr != nil {
				return closeErr
			}
		}
	}
}

func PrepareSherpaAudio(ctx context.Context, audioPath, wavPath string, runner CommandRunner) error {
	if runner == nil {
		runner = ExecRunner{}
	}
	if err := os.MkdirAll(filepath.Dir(wavPath), 0o755); err != nil {
		return err
	}
	if err := runner.Run(ctx, "ffmpeg", "-y", "-i", audioPath, "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le", wavPath); err != nil {
		_ = os.Remove(wavPath)
		return &Error{Message: "sherpa-parakeet audio preparation failed: " + err.Error(), Err: err}
	}
	info, err := os.Stat(wavPath)
	if err != nil || info.Size() == 0 {
		_ = os.Remove(wavPath)
		return &Error{Message: "sherpa-parakeet audio preparation failed: converted audio file is empty"}
	}
	return nil
}

func SherpaRuntimeCandidates(getenv func(string) string) []string {
	if configured := getenv(SherpaONNXProviderEnv); configured != "" {
		if configured == "cpu" {
			return []string{"cpu"}
		}
		return []string{configured, "cpu"}
	}
	candidates := []string{"cuda"}
	if runtime.GOOS == "darwin" && (runtime.GOARCH == "arm64" || runtime.GOARCH == "aarch64") {
		candidates = append([]string{"coreml"}, candidates...)
	}
	return append(candidates, "cpu")
}

func SherpaNumThreads(getenv func(string) string) int {
	value := getenv(SherpaONNXNumThreadsEnv)
	if value == "" {
		return 2
	}
	n, err := strconv.Atoi(value)
	if err != nil || n < 1 {
		return 2
	}
	return n
}

func recognizeSherpaWave(modelDir string, wave *sherpa.Wave, runtimeProvider string, numThreads int) ([]srt.Cue, error) {
	config := sherpa.OfflineRecognizerConfig{
		FeatConfig: sherpa.FeatureConfig{SampleRate: 16000, FeatureDim: 80},
		ModelConfig: sherpa.OfflineModelConfig{
			Transducer: sherpa.OfflineTransducerModelConfig{
				Encoder: filepath.Join(modelDir, "encoder.int8.onnx"),
				Decoder: filepath.Join(modelDir, "decoder.int8.onnx"),
				Joiner:  filepath.Join(modelDir, "joiner.int8.onnx"),
			},
			Tokens:     filepath.Join(modelDir, "tokens.txt"),
			NumThreads: numThreads,
			Provider:   runtimeProvider,
			ModelType:  "nemo_transducer",
		},
		DecodingMethod: "greedy_search",
	}
	recognizer := sherpa.NewOfflineRecognizer(&config)
	if recognizer == nil {
		return nil, fmt.Errorf("failed to create %s recognizer", runtimeProvider)
	}
	defer sherpa.DeleteOfflineRecognizer(recognizer)
	stream := sherpa.NewOfflineStream(recognizer)
	if stream == nil {
		return nil, fmt.Errorf("failed to create %s stream", runtimeProvider)
	}
	defer sherpa.DeleteOfflineStream(stream)
	stream.AcceptWaveform(wave.SampleRate, wave.Samples)
	logProviderProgress("PARAKEET", map[string]any{"status": "START", "runtime": runtimeProvider})
	decodeStart := time.Now()
	recognizer.Decode(stream)
	logProviderProgress("PARAKEET", map[string]any{
		"status":           "DONE",
		"runtime":          runtimeProvider,
		"duration_seconds": math.Round(time.Since(decodeStart).Seconds()*1000) / 1000,
	})
	return SherpaRecognizerResultToCues(stream.GetResult())
}

func SherpaRecognizerResultToCues(result *sherpa.OfflineRecognizerResult) ([]srt.Cue, error) {
	if result == nil {
		return nil, &Error{Message: "sherpa-parakeet returned no transcription text"}
	}
	if len(result.Tokens) > 0 && len(result.Timestamps) > 0 {
		timestamps := make([]any, len(result.Timestamps))
		for i, timestamp := range result.Timestamps {
			timestamps[i] = timestamp
		}
		return SherpaTokensToCues(result.Tokens, timestamps)
	}
	text := strings.TrimSpace(result.Text)
	if text != "" {
		return []srt.Cue{{Index: 1, StartMS: 0, EndMS: max(1000, len(text)*1000/15), Text: text}}, nil
	}
	return nil, &Error{Message: "sherpa-parakeet returned no transcription text"}
}

func SherpaSegmentsToCues(segments []map[string]any) ([]srt.Cue, error) {
	cues := []srt.Cue{}
	for _, segment := range segments {
		text := strings.TrimSpace(firstString(segment["text"], segment["segment"]))
		if text == "" {
			continue
		}
		start, ok1 := numberMS(segment["start"])
		end, ok2 := numberMS(segment["end"])
		if !ok1 || !ok2 {
			return nil, &Error{Message: "sherpa-parakeet returned a segment with invalid timestamp"}
		}
		if end <= start {
			return nil, &Error{Message: "sherpa-parakeet returned a non-positive-duration segment"}
		}
		cues = append(cues, srt.Cue{Index: len(cues) + 1, StartMS: start, EndMS: end, Text: text})
	}
	if len(cues) == 0 {
		return nil, &Error{Message: "sherpa-parakeet returned no transcription text"}
	}
	return cues, nil
}

func SherpaTokensToCues(tokens []string, timestamps []any) ([]srt.Cue, error) {
	cues := []srt.Cue{}
	current := []string{}
	currentStart := -1
	previousStart := -1
	usable := min(len(tokens), len(timestamps))
	for i := 0; i < usable; i++ {
		if tokens[i] == "" {
			continue
		}
		start, ok := numberMS(timestamps[i])
		if !ok {
			return nil, &Error{Message: "sherpa-parakeet returned an invalid token timestamp"}
		}
		if start < previousStart {
			return nil, &Error{Message: "sherpa-parakeet returned out-of-order timestamps"}
		}
		previousStart = start
		if currentStart < 0 {
			currentStart = start
		}
		current = append(current, tokens[i])
		text := NormalizeSherpaText(strings.Join(current, ""))
		next := SherpaNextTimestampMS(timestamps, i, start)
		if next-currentStart >= 7000 || len(text) > 84 || strings.HasSuffix(text, ".") || strings.HasSuffix(text, "?") || strings.HasSuffix(text, "!") {
			cues = append(cues, srt.Cue{Index: len(cues) + 1, StartMS: currentStart, EndMS: max(next, currentStart+1), Text: text})
			current = nil
			currentStart = -1
		}
	}
	if len(current) > 0 && currentStart >= 0 {
		text := NormalizeSherpaText(strings.Join(current, ""))
		end := SherpaNextTimestampMS(timestamps, usable-1, currentStart)
		cues = append(cues, srt.Cue{Index: len(cues) + 1, StartMS: currentStart, EndMS: max(end, currentStart+1000), Text: text})
	}
	if len(cues) == 0 {
		return nil, &Error{Message: "sherpa-parakeet returned no transcription text"}
	}
	return cues, nil
}

func SherpaNextTimestampMS(timestamps []any, index, fallback int) int {
	if index+1 >= len(timestamps) {
		return fallback + 500
	}
	if ms, ok := numberMS(timestamps[index+1]); ok {
		return ms
	}
	return fallback + 500
}

func NormalizeSherpaText(text string) string {
	text = strings.Join(strings.Fields(text), " ")
	for _, mark := range []string{",", ".", ";", ":", "!", "?"} {
		text = strings.ReplaceAll(text, " "+mark, mark)
	}
	return text
}

func numberSeconds(v any) (float64, bool) {
	switch n := v.(type) {
	case float64:
		return n, true
	case float32:
		return float64(n), true
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	case json.Number:
		f, err := n.Float64()
		return f, err == nil
	default:
		f, err := strconv.ParseFloat(fmt.Sprint(v), 64)
		return f, err == nil
	}
}

func numberMS(v any) (int, bool) {
	f, ok := numberSeconds(v)
	if !ok {
		return 0, false
	}
	return int(f*1000 + mathSign(f)*0.5), true
}

func mathSign(v float64) float64 {
	if v < 0 {
		return -1
	}
	return 1
}
func firstString(values ...any) string {
	for _, v := range values {
		if v != nil {
			s := fmt.Sprint(v)
			if s != "<nil>" {
				return s
			}
		}
	}
	return ""
}
func expandHome(path string) string {
	if strings.HasPrefix(path, "~/") {
		home, _ := os.UserHomeDir()
		return filepath.Join(home, path[2:])
	}
	return path
}
