package source

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestResolveLocalPath(t *testing.T) {
	dir := t.TempDir()
	video := filepath.Join(dir, "clip.mp4")
	if err := os.WriteFile(video, []byte("video"), 0o644); err != nil {
		t.Fatal(err)
	}
	called := false
	got, err := Resolve(context.Background(), video, func(context.Context, string) (string, error) {
		called = true
		return "", nil
	})
	if err != nil || got != video {
		t.Fatalf("got=%q err=%v", got, err)
	}
	if called {
		t.Fatal("downloader should not be called for local paths")
	}
}

func TestResolveMissingLocalPath(t *testing.T) {
	_, err := Resolve(context.Background(), filepath.Join(t.TempDir(), "missing.mp4"), nil)
	if err == nil || !strings.Contains(err.Error(), "local file not found") {
		t.Fatalf("expected local file error, got %v", err)
	}
}

func TestResolveYouTubeURL(t *testing.T) {
	dir := t.TempDir()
	downloaded := filepath.Join(dir, "downloaded.webm")
	if err := os.WriteFile(downloaded, []byte("video"), 0o644); err != nil {
		t.Fatal(err)
	}
	got, err := Resolve(context.Background(), "https://youtu.be/abc123", func(ctx context.Context, input string) (string, error) {
		if input != "https://youtu.be/abc123" {
			t.Fatalf("bad input %q", input)
		}
		return downloaded, nil
	})
	if err != nil || got != downloaded {
		t.Fatalf("got=%q err=%v", got, err)
	}
}

func TestResolveUnsupportedHTTPURL(t *testing.T) {
	called := false
	_, err := Resolve(context.Background(), "https://example.com/video.mp4", func(context.Context, string) (string, error) {
		called = true
		return "", nil
	})
	if err == nil || !strings.Contains(err.Error(), "only local video files and YouTube URLs are supported") {
		t.Fatalf("expected unsupported URL error, got %v", err)
	}
	if called {
		t.Fatal("downloader should not be called for unsupported URLs")
	}
}

func TestResolveYouTubeDownloadFailure(t *testing.T) {
	want := errors.New("YouTube download failed")
	_, err := Resolve(context.Background(), "https://www.youtube.com/watch?v=abc123", func(context.Context, string) (string, error) {
		return "", want
	})
	if !errors.Is(err, want) {
		t.Fatalf("expected download error, got %v", err)
	}
}
