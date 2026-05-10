package provider

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"video-to-srt/internal/srt"
)

type flakyProvider struct {
	failures int
	err      error
	calls    int
}

func (f *flakyProvider) Metadata() Metadata {
	return Metadata{Name: "fake", Models: []string{"m"}, DefaultModel: "m"}
}
func (f *flakyProvider) Transcribe(context.Context, string, string, string, string) error {
	f.calls++
	if f.calls <= f.failures {
		return f.err
	}
	return nil
}

func TestRegistryModelEnvAndDiscovery(t *testing.T) {
	r := DefaultRegistry()
	for _, name := range []string{"voxtral", "grok", "vertex-gemini", "sherpa-parakeet"} {
		if _, err := r.Get(name); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := r.Get("bad"); err == nil || !strings.Contains(err.Error(), "Available providers") {
		t.Fatalf("bad provider err = %v", err)
	}
	if _, err := ResolveModel(Metadata{Name: "voxtral", Models: []string{"voxtral-mini-2602"}, DefaultModel: "voxtral-mini-2602"}, "bad"); err == nil || !strings.Contains(err.Error(), "Available models") {
		t.Fatalf("bad model err = %v", err)
	}
	if _, _, err := r.ValidateReady("grok", "", func(string) string { return "" }); err == nil || !strings.Contains(err.Error(), "XAI_API_KEY") {
		t.Fatalf("missing env err = %v", err)
	}
	out, err := r.ListJSON()
	if err != nil {
		t.Fatal(err)
	}
	var parsed map[string]map[string]any
	if err := json.Unmarshal([]byte(out), &parsed); err != nil || parsed["vertex-gemini"]["default_model"] != "gemini-2.5-flash" {
		t.Fatalf("bad discovery: %s %v", out, err)
	}
}

func TestRetryPolicy(t *testing.T) {
	delays := []time.Duration{}
	err := &Error{Message: "rate", StatusCode: 429, RetryAfter: "3"}
	f := &flakyProvider{failures: 1, err: err}
	if err := TranscribeWithRetries(context.Background(), f, "", "", "", "", func(d time.Duration) { delays = append(delays, d) }); err != nil {
		t.Fatal(err)
	}
	if f.calls != 2 || delays[0] != 3*time.Second {
		t.Fatalf("calls=%d delays=%v", f.calls, delays)
	}
	f = &flakyProvider{failures: 4, err: &Error{Message: "server", StatusCode: 500}}
	delays = nil
	if err := TranscribeWithRetries(context.Background(), f, "", "", "", "", func(d time.Duration) { delays = append(delays, d) }); err == nil {
		t.Fatal("expected exhaustion")
	}
	if f.calls != 4 || len(delays) != 3 {
		t.Fatalf("calls=%d delays=%v", f.calls, delays)
	}
	f = &flakyProvider{failures: 1, err: &Error{Message: "bad"}}
	if err := TranscribeWithRetries(context.Background(), f, "", "", "", "", nil); err == nil || f.calls != 1 {
		t.Fatalf("non-transient calls=%d err=%v", f.calls, err)
	}
	future := time.Now().Add(2 * time.Second).UTC().Format(http.TimeFormat)
	d := RetryDelay(&Error{StatusCode: 429, RetryAfter: future}, time.Second, time.Now)
	if d <= 0 || d > 3*time.Second {
		t.Fatalf("date retry delay = %v", d)
	}
}

func TestGrokHTTPAndCueConversion(t *testing.T) {
	dir := t.TempDir()
	audio := filepath.Join(dir, "a.mp3")
	out := filepath.Join(dir, "out.srt")
	if err := os.WriteFile(audio, []byte("audio"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("XAI_API_KEY", "key")
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.Header.Get("Authorization") != "Bearer key" {
			t.Fatalf("bad request: %s %s", r.Method, r.Header.Get("Authorization"))
		}
		if err := r.ParseMultipartForm(1 << 20); err != nil {
			t.Fatal(err)
		}
		if r.FormValue("model") != "grok-transcribe-1" || r.FormValue("language") != "fr" {
			t.Fatalf("bad form: %v", r.Form)
		}
		_, _, err := r.FormFile("file")
		if err != nil {
			t.Fatal(err)
		}
		_, _ = w.Write([]byte(`{"words":[{"word":"hello","start":1.25,"end":1.5},{"word":"world.","start":1.5,"end":2.48}]}`))
	}))
	defer server.Close()
	if err := (GrokProvider{URL: server.URL, Client: server.Client()}).Transcribe(context.Background(), audio, out, "", "fr"); err != nil {
		t.Fatal(err)
	}
	cues, err := srt.ParseFile(out)
	if err != nil || len(cues) != 1 || cues[0].StartMS != 1250 || cues[0].EndMS != 2480 {
		t.Fatalf("cues=%#v err=%v", cues, err)
	}
	if _, err := GrokResultToCues(map[string]any{"segments": []any{map[string]any{"start": 0.0, "end": 1.0, "text": "hi", "speaker_id": 2.0}}}); err != nil {
		t.Fatal(err)
	}
	if _, err := GrokResultToCues(map[string]any{}); err == nil {
		t.Fatal("expected empty result error")
	}
}

func TestVoxtralHTTPAndCueConversion(t *testing.T) {
	dir := t.TempDir()
	audio := filepath.Join(dir, "a.mp3")
	out := filepath.Join(dir, "out.srt")
	if err := os.WriteFile(audio, []byte("audio"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("MISTRAL_API_KEY", "key")
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.Header.Get("x-api-key") != "key" {
			t.Fatalf("bad request: %s %s", r.Method, r.Header.Get("x-api-key"))
		}
		if err := r.ParseMultipartForm(1 << 20); err != nil {
			t.Fatal(err)
		}
		if r.FormValue("model") != "voxtral-mini-2602" || r.FormValue("language") != "fr" || r.FormValue("timestamp_granularities") != "segment" {
			t.Fatalf("bad form: %v", r.Form)
		}
		_, _, err := r.FormFile("file")
		if err != nil {
			t.Fatal(err)
		}
		_, _ = w.Write([]byte(`{"segments":[{"text":"bonjour","start":0.5,"end":1.25,"speaker_id":1}]}`))
	}))
	defer server.Close()
	if err := (VoxtralProvider{URL: server.URL, Client: server.Client()}).Transcribe(context.Background(), audio, out, "", "fr"); err != nil {
		t.Fatal(err)
	}
	cues, err := srt.ParseFile(out)
	if err != nil || len(cues) != 1 || cues[0].StartMS != 500 || cues[0].EndMS != 1250 || cues[0].Speaker != "Speaker 1" {
		t.Fatalf("cues=%#v err=%v", cues, err)
	}
	if cues, err := VoxtralResultToCues(map[string]any{"text": "plain transcript"}); err != nil || len(cues) != 1 || cues[0].EndMS < 1000 {
		t.Fatalf("fallback cues=%#v err=%v", cues, err)
	}
	if _, err := VoxtralResultToCues(map[string]any{}); err == nil {
		t.Fatal("expected empty result error")
	}
}

func TestVertexAndSherpaConversions(t *testing.T) {
	if err := (VertexGeminiProvider{}).Transcribe(context.Background(), "in.mp3", "out.srt", "", ""); err == nil || !strings.Contains(err.Error(), "native client is not configured") {
		t.Fatalf("expected native vertex client error, got %v", err)
	}
	if err := (SherpaParakeetProvider{}).Transcribe(context.Background(), "in.mp3", "out.srt", "", ""); err == nil || !strings.Contains(err.Error(), "native runtime is not configured") {
		t.Fatalf("expected native sherpa runtime error, got %v", err)
	}
	cues, err := VertexGeminiResponseToCues(`{"segments":[{"start":0,"end":1.2,"text":"hi"}]}`)
	if err != nil || cues[0].EndMS != 1200 {
		t.Fatalf("vertex cues=%#v err=%v", cues, err)
	}
	for _, payload := range []any{`bad`, map[string]any{"segments": []any{map[string]any{"start": 2.0, "end": 1.0, "text": "bad"}}}, map[string]any{"segments": []any{map[string]any{"start": 2.0, "end": 3.0, "text": "a"}, map[string]any{"start": 1.0, "end": 2.0, "text": "b"}}}} {
		if _, err := VertexGeminiResponseToCues(payload); err == nil {
			t.Fatalf("expected vertex error for %#v", payload)
		}
	}
	if got := SherpaRuntimeCandidates(func(k string) string {
		if k == SherpaONNXProviderEnv {
			return "coreml"
		}
		return ""
	}); len(got) != 2 || got[1] != "cpu" {
		t.Fatalf("candidates=%v", got)
	}
	if SherpaNumThreads(func(string) string { return "bad" }) != 2 || SherpaNumThreads(func(string) string { return "8" }) != 8 {
		t.Fatal("bad thread parsing")
	}
	segments, err := SherpaSegmentsToCues([]map[string]any{{"start": 0.0, "end": 1.0, "text": "hi"}})
	if err != nil || len(segments) != 1 {
		t.Fatalf("segments=%#v err=%v", segments, err)
	}
	tokens, err := SherpaTokensToCues([]string{"hello", " ", "world."}, []any{0.0, 0.5, 1.0})
	if err != nil || len(tokens) != 1 || tokens[0].Text != "hello world." {
		t.Fatalf("tokens=%#v err=%v", tokens, err)
	}
}

type sherpaRunner struct{ err error }

func (s sherpaRunner) Run(ctx context.Context, name string, args ...string) error {
	if s.err != nil {
		return s.err
	}
	return os.WriteFile(args[len(args)-1], []byte("wav"), 0o644)
}

func TestSherpaCacheAndAudioPrep(t *testing.T) {
	dir := t.TempDir()
	getenv := func(k string) string {
		if k == SherpaParakeetCacheEnv {
			return dir
		}
		return ""
	}
	modelDir := SherpaParakeetModelDir(getenv)
	if err := os.MkdirAll(modelDir, 0o755); err != nil {
		t.Fatal(err)
	}
	for _, name := range SherpaParakeetRequiredFiles {
		if err := os.WriteFile(filepath.Join(modelDir, name), []byte("x"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	got, err := EnsureSherpaParakeetModel("http://invalid", getenv, http.DefaultClient)
	if err != nil || got != modelDir {
		t.Fatalf("cache=%q err=%v", got, err)
	}
	audio := filepath.Join(dir, "a.mp3")
	wav := filepath.Join(dir, "a.wav")
	_ = os.WriteFile(audio, []byte("mp3"), 0o644)
	if err := PrepareSherpaAudio(context.Background(), audio, wav, sherpaRunner{}); err != nil {
		t.Fatal(err)
	}
	if err := PrepareSherpaAudio(context.Background(), audio, filepath.Join(dir, "bad.wav"), sherpaRunner{err: errors.New("ffmpeg")}); err == nil {
		t.Fatal("expected conversion failure")
	}
}
