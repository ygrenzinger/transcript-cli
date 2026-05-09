package pipeline

import (
	"context"
	"errors"
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

func TestPipelineResolvesInputSourceBeforeExtraction(t *testing.T) {
	dir := t.TempDir()
	downloaded := filepath.Join(dir, "downloaded.webm")
	if err := os.WriteFile(downloaded, []byte("video"), 0o644); err != nil {
		t.Fatal(err)
	}
	calls := []string{}
	r := provider.NewRegistry()
	r.Register(fakeProvider{name: "fake", calls: &calls})
	out, err := Run(context.Background(), Options{VideoPath: "https://youtu.be/abc123", Provider: "fake"}, Dependencies{
		Registry: r,
		Stderr:   &strings.Builder{},
		Resolve: func(ctx context.Context, input string) (string, error) {
			calls = append(calls, "resolve:"+input)
			return downloaded, nil
		},
		Audio: func(ctx context.Context, video, output string) (string, error) {
			calls = append(calls, "extract:"+video)
			audio := strings.TrimSuffix(video, filepath.Ext(video)) + ".mp3"
			return audio, os.WriteFile(audio, []byte("mp3"), 0o644)
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if want := filepath.Join(dir, "downloaded.fake.raw.srt"); out != want {
		t.Fatalf("out=%q want=%q", out, want)
	}
	wantCalls := []string{"resolve:https://youtu.be/abc123", "extract:" + downloaded, "transcribe"}
	if strings.Join(calls, "|") != strings.Join(wantCalls, "|") {
		t.Fatalf("calls=%v want=%v", calls, wantCalls)
	}
}

func TestPipelineStopsWhenInputSourceResolutionFails(t *testing.T) {
	want := errors.New("YouTube download failed")
	calls := []string{}
	r := provider.NewRegistry()
	r.Register(fakeProvider{name: "fake", calls: &calls})
	_, err := Run(context.Background(), Options{VideoPath: "https://youtu.be/abc123", Provider: "fake", Improve: true}, Dependencies{
		Registry: r,
		Stderr:   &strings.Builder{},
		Resolve: func(ctx context.Context, input string) (string, error) {
			return "", want
		},
		Audio: func(ctx context.Context, video, output string) (string, error) {
			calls = append(calls, "extract")
			return "", nil
		},
	})
	if !errors.Is(err, want) {
		t.Fatalf("expected resolver error, got %v", err)
	}
	if len(calls) != 0 {
		t.Fatalf("downstream stages should not run, calls=%v", calls)
	}
}
