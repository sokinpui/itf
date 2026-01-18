package itf

import (
	"fmt"
	"os"
	"regexp"
	"strconv"
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

		applied := applyPatch(d.FilePath, patched, resolver)

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

func applyPatch(path, patch string, resolver *PathResolver) []string {
	var sourceLines []string
	srcPath := resolver.ResolveExisting(path)
	if srcPath != "" {
		if content, err := os.ReadFile(srcPath); err == nil {
			if len(content) > 0 {
				sourceLines = strings.Split(strings.TrimSuffix(string(content), "\n"), "\n")
			}
		}
	}
	return applyUnifiedDiff(sourceLines, patch)
}

func applyUnifiedDiff(source []string, patch string) []string {
	patchLines := strings.Split(patch, "\n")
	var result []string
	srcIdx := 0

	for i := 0; i < len(patchLines); i++ {
		line := patchLines[i]
		if !strings.HasPrefix(line, "@@ -") {
			continue
		}

		parts := strings.Split(line, " ")
		if len(parts) < 2 {
			continue
		}

		rangePart := strings.TrimPrefix(parts[1], "-")
		rangeSplit := strings.Split(rangePart, ",")
		if len(rangeSplit) == 0 || rangeSplit[0] == "" {
			continue
		}
		start, _ := strconv.Atoi(rangeSplit[0])

		startIdx := start - 1
		if startIdx < 0 {
			startIdx = 0
		}

		for srcIdx < startIdx && srcIdx < len(source) {
			result = append(result, source[srcIdx])
			srcIdx++
		}

		i++
		for i < len(patchLines) {
			hunkLine := patchLines[i]
			if strings.HasPrefix(hunkLine, "@@") || strings.HasPrefix(hunkLine, "---") || strings.HasPrefix(hunkLine, "+++") {
				i--
				break
			}

			if strings.HasPrefix(hunkLine, "+") {
				result = append(result, hunkLine[1:])
			} else if strings.HasPrefix(hunkLine, "-") {
				srcIdx++
			} else if strings.HasPrefix(hunkLine, " ") {
				result = append(result, hunkLine[1:])
				srcIdx++
			}
			i++
		}
	}

	for srcIdx < len(source) {
		result = append(result, source[srcIdx])
		srcIdx++
	}

	return result
}
