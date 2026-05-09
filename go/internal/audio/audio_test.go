package audio

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

type fakeRunner struct {
	err  error
	args []string
}

func (f *fakeRunner) Run(ctx context.Context, name string, args ...string) error {
	f.args = append([]string{name}, args...)
	if f.err != nil {
		return f.err
	}
	return os.WriteFile(args[len(args)-1], []byte("mp3"), 0o644)
}

func TestExtractMissingCacheCommandFailureAndDefaultPath(t *testing.T) {
	dir := t.TempDir()
	if _, err := Extract(context.Background(), filepath.Join(dir, "missing.mp4"), "", nil); err == nil {
		t.Fatal("expected missing input error")
	}
	video := filepath.Join(dir, "clip.mp4")
	if err := os.WriteFile(video, []byte("video"), 0o644); err != nil {
		t.Fatal(err)
	}
	cached := DefaultOutputPath(video)
	if err := os.WriteFile(cached, []byte("cached"), 0o644); err != nil {
		t.Fatal(err)
	}
	runner := &fakeRunner{}
	got, err := Extract(context.Background(), video, "", runner)
	if err != nil || got != cached || len(runner.args) != 0 {
		t.Fatalf("cache Extract() = %q, %v, runner=%v", got, err, runner.args)
	}
	if err := os.Remove(cached); err != nil {
		t.Fatal(err)
	}
	runner = &fakeRunner{err: errors.New("no audio")}
	if _, err := Extract(context.Background(), video, "", runner); err == nil {
		t.Fatal("expected ffmpeg failure")
	}
	if _, err := os.Stat(cached); !os.IsNotExist(err) {
		t.Fatal("partial output exists after failure")
	}
	runner = &fakeRunner{}
	got, err = Extract(context.Background(), video, "", runner)
	if err != nil || got != cached {
		t.Fatalf("Extract() = %q, %v", got, err)
	}
	if !reflect.DeepEqual(runner.args[:4], []string{"ffmpeg", "-y", "-i", video}) {
		t.Fatalf("unexpected ffmpeg args: %v", runner.args)
	}
}
