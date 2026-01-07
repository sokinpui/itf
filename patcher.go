package itf

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"regexp"
	"strings"
)

var filePathRegex = regexp.MustCompile(`(?m)^\+\+\+ b/(?P<path>.*?)(\s|$)`)

func ExtractPathFromDiff(content string) string {
	if match := filePathRegex.FindStringSubmatch(content); len(match) > 1 {
		return strings.TrimSpace(match[1])
	}
	return ""
}

func GeneratePatchedContents(diffs []DiffBlock, resolver *PathResolver, extensions []string) ([]FileChange, []string, error) {
	var changes []FileChange
	var failed []string
	for _, d := range diffs {
		abs := resolver.Resolve(d.FilePath)
		if len(extensions) > 0 && !HasAllowedExtension(d.FilePath, extensions) {
			continue
		}

		patched, err := CorrectDiff(d, resolver, extensions)
		if err != nil {
			failed = append(failed, abs)
			continue
		}

		applied, err := applyPatch(d.FilePath, patched, resolver)
		if err != nil {
			failed = append(failed, abs)
			continue
		}

		changes = append(changes, FileChange{
			Path:     abs,
			Content:  applied,
			Source:   "diff",
			RawBlock: fmt.Sprintf("```diff\n%s\n```", d.RawContent),
		})
	}
	return changes, failed, nil
}

func CorrectDiff(diff DiffBlock, resolver *PathResolver, extensions []string) (string, error) {
	src := resolver.ResolveExisting(diff.FilePath)
	var lines []string
	if src != "" {
		if content, err := os.ReadFile(src); err == nil {
			lines = strings.Split(string(content), "\n")
		}
	}
	return correctDiffHunks(lines, diff.RawContent, diff.FilePath)
}

func applyPatch(path, patch string, resolver *PathResolver) ([]string, error) {
	src := resolver.ResolveExisting(path)
	if src == "" {
		tmp, _ := os.CreateTemp("", "itf-")
		src = tmp.Name()
		defer os.Remove(src)
		tmp.Close()
	}

	cmd := exec.Command("patch", "-s", "-p1", "--no-backup-if-mismatch", "-r", "/dev/null", "-o", "-", src)
	cmd.Stdin = strings.NewReader(patch)
	var out, serr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, &serr

	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("patch failed: %s", serr.String())
	}
	return strings.Split(strings.TrimSuffix(out.String(), "\n"), "\n"), nil
}
