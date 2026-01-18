package itf

import (
	"fmt"
	"strings"
)

func getTargetBlock(diff []string) []string {
	var block []string
	for _, line := range diff {
		if strings.HasPrefix(line, "-") || strings.HasPrefix(line, " ") {
			block = append(block, line[1:])
		}
	}
	return block
}

func matchBlock(source, block []string, startLine int) (int, int) {
	if len(block) == 0 {
		return len(source) + 1, len(source)
	}

	startIdx := startLine - 1
	if startIdx < 0 {
		startIdx = 0
	}

	for i := startIdx; i <= len(source)-len(block); i++ {
		match := true
		for j := 0; j < len(block); j++ {
			if source[i+j] != block[j] {
				match = false
				break
			}
		}
		if match {
			return i + 1, i + len(block)
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
		os, me := matchBlock(sourceLines, getTargetBlock(h), last+1)
		if os == -1 {
			return "", fmt.Errorf("failed match")
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
