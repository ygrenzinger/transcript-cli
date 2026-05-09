package audio

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

type Runner interface {
	Run(ctx context.Context, name string, args ...string) error
}
type ExecRunner struct{}

func (ExecRunner) Run(ctx context.Context, name string, args ...string) error {
	return exec.CommandContext(ctx, name, args...).Run()
}

func DefaultOutputPath(videoPath string) string {
	ext := filepath.Ext(videoPath)
	return strings.TrimSuffix(videoPath, ext) + ".mp3"
}

func Extract(ctx context.Context, videoPath, outputPath string, runner Runner) (string, error) {
	if _, err := os.Stat(videoPath); err != nil {
		return "", fmt.Errorf("file not found: %s", videoPath)
	}
	if outputPath == "" {
		outputPath = DefaultOutputPath(videoPath)
	}
	if info, err := os.Stat(outputPath); err == nil && info.Size() > 0 {
		return outputPath, nil
	}
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		return "", err
	}
	tmp, err := os.CreateTemp(filepath.Dir(outputPath), ".*.mp3")
	if err != nil {
		return "", err
	}
	tmpPath := tmp.Name()
	_ = tmp.Close()
	defer os.Remove(tmpPath)
	if runner == nil {
		runner = ExecRunner{}
	}
	args := []string{"-y", "-i", videoPath, "-vn", "-acodec", "libmp3lame", tmpPath}
	if err := runner.Run(ctx, "ffmpeg", args...); err != nil {
		return "", fmt.Errorf("audio extraction failed: %w", err)
	}
	info, err := os.Stat(tmpPath)
	if err != nil || info.Size() == 0 {
		return "", fmt.Errorf("extracted audio file is empty")
	}
	if err := os.Rename(tmpPath, outputPath); err != nil {
		return "", err
	}
	return outputPath, nil
}
