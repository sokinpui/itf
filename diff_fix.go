package itf

import (
	"fmt"
	"strings"
)

func getTargetBlock(diff []string) (block []string, deletedOnly []string, firstNonEmptyOffset int) {
	firstNonEmptyOffset = -1
	for i, line := range diff {
		if !strings.HasPrefix(line, "-") && !strings.HasPrefix(line, " ") {
			continue
		}

		content := line[1:]
		block = append(block, content)

		if strings.HasPrefix(line, "-") {
			deletedOnly = append(deletedOnly, content)
		}

		if firstNonEmptyOffset == -1 && strings.TrimSpace(content) != "" {
			firstNonEmptyOffset = i
		}
	}
	return block, deletedOnly, firstNonEmptyOffset
}

func matchBlock(source, block []string, startLine int) (int, int) {
	if len(block) == 0 {
		return len(source) + 1, len(source)
	}

	normalizedSource := normalizeLines(source)
	normalizedBlock := normalizeLines(block)
	startIndex := max(0, startLine-1)

	for i := startIndex; i <= len(normalizedSource)-len(normalizedBlock); i++ {
		if isMatch(normalizedSource[i:i+len(normalizedBlock)], normalizedBlock) {
			return i + 1, i + len(normalizedBlock)
		}
	}

	return -1, -1
}

func isMatch(source, target []string) bool {
	for i := range target {
		if source[i] != target[i] {
			return false
		}
	}
	return true
}

func correctDiffHunks(sourceLines []string, raw, path string) (string, error) {
	var hunks [][]string
	var ch []string
	for _, l := range strings.Split(raw, "\n") {
		if strings.HasPrefix(l, "---") || strings.HasPrefix(l, "+++") {
			continue
		}
		if strings.HasPrefix(l, "@@") {
			if len(ch) > 0 {
				hunks = append(hunks, ch)
			}
			ch = nil
			continue
		}
		if strings.HasPrefix(l, "+") || strings.HasPrefix(l, "-") || strings.HasPrefix(l, " ") {
			ch = append(ch, l)
		}
	}
	if len(ch) > 0 {
		hunks = append(hunks, ch)
	}

	if len(hunks) == 0 {
		return "", nil
	}

	var cp []string
	cp = append(cp, fmt.Sprintf("--- a/%s\n+++ b/%s\n", path, path))
	offset, last := 0, 0
	for _, h := range hunks {
		fullBlock, deletedOnly, firstOffset := getTargetBlock(h)

		os, me := matchBlock(sourceLines, fullBlock, last+1)

		if os == -1 {
			// Fallback: try to match only the deleted lines if the LLM hallucinated context
			os, me = matchBlock(sourceLines, deletedOnly, last+1)
		}

		if os == -1 {
			return "", fmt.Errorf("failed match")
		}

		// Adjust offset based on where the first non-empty line was in the original hunk
		// if we matched using fullBlock. If we matched deletedOnly, the logic is simpler
		// but this heuristic covers most LLM-generated diff cases.
		if firstOffset != -1 {
			os -= firstOffset
		}
		last = me

		ac, rc := 0, 0
		for _, l := range h {
			if strings.HasPrefix(l, "+") {
				ac++
			} else if strings.HasPrefix(l, "-") {
				rc++
			}
		}
		ol, nl := (len(h) - ac), (len(h) - rc)
		cp = append(cp, fmt.Sprintf("@@ -%d,%d +%d,%d @@\n", os, ol, os+offset, nl))
		for _, l := range h {
			cp = append(cp, l+"\n")
		}
		offset += nl - ol
	}
	return strings.Join(cp, ""), nil
}

func normalizeLines(lines []string) []string {
	normalized := make([]string, len(lines))
	for i, l := range lines {
		normalized[i] = strings.TrimRight(l, " \t\r\n")
	}
	return normalized
}
