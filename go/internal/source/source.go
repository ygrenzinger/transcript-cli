package source

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

type Downloader func(context.Context, string) (string, error)

func Resolve(ctx context.Context, input string, downloader Downloader) (string, error) {
	if isHTTPURL(input) {
		if !isYouTubeURL(input) {
			return "", fmt.Errorf("only local video files and YouTube URLs are supported: %s", input)
		}
		if downloader == nil {
			downloader = DownloadYouTube
		}
		return downloader(ctx, input)
	}
	if _, err := os.Stat(input); err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return "", fmt.Errorf("local file not found: %s", input)
		}
		return "", err
	}
	return input, nil
}

func DownloadYouTube(ctx context.Context, input string) (string, error) {
	if _, err := exec.LookPath("yt-dlp"); err != nil {
		return "", errors.New("yt-dlp is required for YouTube URLs")
	}
	cmd := exec.CommandContext(ctx, "yt-dlp", "--no-playlist", "--print", "after_move:filepath", "-o", "%(title)s [%(id)s].%(ext)s", input)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		message := strings.TrimSpace(stderr.String())
		if message == "" {
			message = err.Error()
		}
		return "", fmt.Errorf("YouTube download failed: %s", message)
	}
	lines := strings.Split(strings.TrimSpace(stdout.String()), "\n")
	if len(lines) == 0 {
		return "", errors.New("YouTube download failed: yt-dlp did not report an output file")
	}
	path := strings.TrimSpace(lines[len(lines)-1])
	if path == "" {
		return "", errors.New("YouTube download failed: yt-dlp did not report an output file")
	}
	if _, err := os.Stat(path); err != nil {
		return "", fmt.Errorf("YouTube download failed: downloaded file not found: %s", path)
	}
	return path, nil
}

func isHTTPURL(input string) bool {
	lower := strings.ToLower(input)
	return strings.HasPrefix(lower, "http://") || strings.HasPrefix(lower, "https://")
}

func isYouTubeURL(input string) bool {
	lower := strings.ToLower(input)
	return strings.HasPrefix(lower, "https://www.youtube.com/") ||
		strings.HasPrefix(lower, "http://www.youtube.com/") ||
		strings.HasPrefix(lower, "https://youtube.com/") ||
		strings.HasPrefix(lower, "http://youtube.com/") ||
		strings.HasPrefix(lower, "https://m.youtube.com/") ||
		strings.HasPrefix(lower, "http://m.youtube.com/") ||
		strings.HasPrefix(lower, "https://youtu.be/") ||
		strings.HasPrefix(lower, "http://youtu.be/")
}
