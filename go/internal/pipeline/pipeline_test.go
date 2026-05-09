package pipeline

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"video-to-srt/internal/provider"
	"video-to-srt/internal/srt"
)

type fakeProvider struct {
	name  string
	fail  bool
	calls *[]string
}

func (f fakeProvider) Metadata() provider.Metadata {
	return provider.Metadata{Name: f.name, Models: []string{"m"}, DefaultModel: "m"}
}
func (f fakeProvider) Transcribe(ctx context.Context, audio, output, model, language string) error {
	*f.calls = append(*f.calls, "transcribe")
	if f.fail {
		return &provider.Error{Message: "provider failed"}
	}
	return srt.AtomicWriteFile(output, []srt.Cue{{Index: 1, StartMS: 0, EndMS: 1000, Text: "hello"}})
}

func TestPipelineRawImprovedFailureAndProgress(t *testing.T) {
	dir := t.TempDir()
	video := filepath.Join(dir, "clip.mp4")
	_ = os.WriteFile(video, []byte("video"), 0o644)
	calls := []string{}
	r := provider.NewRegistry()
	r.Register(fakeProvider{name: "fake", calls: &calls})
	progress := &strings.Builder{}
	out, err := Run(context.Background(), Options{VideoPath: video, Provider: "fake"}, Dependencies{Registry: r, Stderr: progress, Audio: func(ctx context.Context, video, output string) (string, error) {
		calls = append(calls, "extract")
		audio := strings.TrimSuffix(video, filepath.Ext(video)) + ".mp3"
		return audio, os.WriteFile(audio, []byte("mp3"), 0o644)
	}})
	if err != nil || !strings.HasSuffix(out, ".fake.raw.srt") {
		t.Fatalf("out=%q err=%v", out, err)
	}
	if _, err := os.Stat(strings.TrimSuffix(video, filepath.Ext(video)) + ".mp3"); !os.IsNotExist(err) {
		t.Fatal("audio not removed after success")
	}
	if strings.Count(progress.String(), "PROGRESS") != 4 || !strings.Contains(progress.String(), `stage="1/2"`) {
		t.Fatalf("bad progress:\n%s", progress.String())
	}
	calls = nil
	progress.Reset()
	out, err = Run(context.Background(), Options{VideoPath: video, Provider: "fake", Improve: true}, Dependencies{Registry: r, Stderr: progress, Audio: func(ctx context.Context, video, output string) (string, error) {
		calls = append(calls, "extract")
		audio := strings.TrimSuffix(video, filepath.Ext(video)) + ".mp3"
		return audio, os.WriteFile(audio, []byte("mp3"), 0o644)
	}})
	if err != nil || !strings.HasSuffix(out, ".fake.improved.srt") {
		t.Fatalf("improved out=%q err=%v", out, err)
	}
	if strings.Count(progress.String(), "PROGRESS") != 6 || !strings.Contains(progress.String(), `stage="3/3"`) {
		t.Fatalf("bad improved progress:\n%s", progress.String())
	}
	failingCalls := []string{}
	r = provider.NewRegistry()
	r.Register(fakeProvider{name: "fake", fail: true, calls: &failingCalls})
	_, err = Run(context.Background(), Options{VideoPath: video, Provider: "fake", Improve: true}, Dependencies{Registry: r, Stderr: &strings.Builder{}, Audio: func(ctx context.Context, video, output string) (string, error) {
		audio := strings.TrimSuffix(video, filepath.Ext(video)) + ".mp3"
		return audio, os.WriteFile(audio, []byte("mp3"), 0o644)
	}})
	if err == nil {
		t.Fatal("expected transcription failure")
	}
	if _, err := os.Stat(strings.TrimSuffix(video, filepath.Ext(video)) + ".mp3"); err != nil {
		t.Fatal("audio should be retained on transcription failure")
	}
}
