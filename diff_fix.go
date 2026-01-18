package itf

import (
	"fmt"
	"strings"
)

func getTargetBlock(diff []string) ([]string, int) {
	var block []string
	firstNonEmptyOffset := -1
	for i, line := range diff {
		if strings.HasPrefix(line, "-") || strings.HasPrefix(line, " ") {
			content := line[1:]
			trimmed := strings.TrimSpace(content)
			if trimmed != "" {
				if firstNonEmptyOffset == -1 {
					firstNonEmptyOffset = i
				}
				block = append(block, content)
			}
		}
	}
	return block, firstNonEmptyOffset
}

func normalizeLineForMatching(line string) string {
	return strings.Join(strings.Fields(line), " ")
}

func matchBlock(source, block []string, startLine int) (int, int) {
	if len(block) == 0 {
		return len(source) + 1, len(source)
	}

	nb := make([]string, len(block))
	for i, l := range block {
		nb[i] = normalizeLineForMatching(l)
	}

	var fs []string
	var ol []int
	for i, l := range source {
		nl := normalizeLineForMatching(l)
		if nl != "" {
			fs = append(fs, nl)
			ol = append(ol, i+1)
		}
	}

	si := 0
	if startLine > 1 {
		for i, ln := range ol {
			if ln >= startLine {
				si = i
				break
			}
		}
	}

	for i := si; i <= len(fs)-len(nb); i++ {
		match := true
		for j := 0; j < len(nb); j++ {
			if fs[i+j] != nb[j] {
				match = false
				break
			}
		}
		if match {
			return ol[i], ol[i+len(nb)-1]
		}
	}
	return -1, -1
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
		target, firstOffset := getTargetBlock(h)
		os, me := matchBlock(sourceLines, target, last+1)
		if os == -1 {
			return "", fmt.Errorf("failed match")
		}

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
		ol, nl := (len(h)-ac), (len(h)-rc)
		cp = append(cp, fmt.Sprintf("@@ -%d,%d +%d,%d @@\n", os, ol, os+offset, nl))
		for _, l := range h {
			cp = append(cp, l+"\n")
		}
		offset += nl - ol
	}
	return strings.Join(cp, ""), nil
}
