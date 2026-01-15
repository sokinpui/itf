package itf

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	stateDirName    = ".itf"
	stateFileName   = "states.itf"
	TrashDir        = "trash"
	BlobsDir        = "blobs"
	entrySeparator  = "\n===\n"
	opSeparator     = "\n---\n"
	none            = "-"
)

type Operation struct {
	Timestamp      int64
	Action         string
	Path           string
	OldContentHash string
	ContentHash    string
	NewPath        string
}

type HistoryEntry struct {
	Operations []Operation
}

type State struct {
	History      []HistoryEntry
	CurrentIndex int
}

type StateManager struct {
	statePath string
	state     *State
	StateDir  string
}

func findGitRoot() (string, error) {
	cmd := exec.Command("git", "rev-parse", "--show-toplevel")
	out, err := cmd.Output()
	if err != nil {
		return os.Getwd()
	}
	return strings.TrimSpace(string(out)), nil
}

func NewStateManager() (*StateManager, error) {
	root, _ := findGitRoot()
	dir := filepath.Join(root, stateDirName)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, err
	}
	m := &StateManager{statePath: filepath.Join(dir, stateFileName), StateDir: dir}
	m.state = &State{CurrentIndex: -1, History: []HistoryEntry{}}
	_ = m.load()
	return m, nil
}

func (m *StateManager) load() error {
	data, err := os.ReadFile(m.statePath)
	if err != nil {
		return err
	}

	blocks := strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), entrySeparator)
	if len(blocks) == 0 {
		return nil
	}

	idx, _ := strconv.Atoi(strings.TrimSpace(blocks[0]))
	m.state = &State{CurrentIndex: idx, History: []HistoryEntry{}}

	for _, b := range blocks[1:] {
		entry := HistoryEntry{}
		ops := strings.Split(strings.TrimSpace(b), opSeparator)
		for _, opBlock := range ops {
			lines := strings.Split(strings.TrimSpace(opBlock), "\n")
			if len(lines) < 6 {
				continue
			}

			val := func(s string) string {
				s = strings.TrimSpace(s)
				if s == none {
					return ""
				}
				return s
			}

			op := Operation{
				Timestamp:      parseTimestamp(lines[0]),
				Action:         val(lines[1]),
				Path:           val(lines[2]),
				OldContentHash: val(lines[3]),
				ContentHash:    val(lines[4]),
				NewPath:        val(lines[5]),
			}
			entry.Operations = append(entry.Operations, op)
		}
		m.state.History = append(m.state.History, entry)
	}
	return nil
}

func parseTimestamp(s string) int64 {
	ts, _ := strconv.ParseInt(strings.TrimSpace(s), 10, 64)
	return ts
}

func (m *StateManager) save() {
	var b strings.Builder
	fmt.Fprintf(&b, "%d", m.state.CurrentIndex)
	for _, e := range m.state.History {
		b.WriteString(entrySeparator)

		placeholder := func(s string) string {
			if s == "" {
				return none
			}
			return s
		}

		for i, op := range e.Operations {
			fmt.Fprintf(&b, "%d\n%s\n%s\n%s\n%s\n%s", op.Timestamp, placeholder(op.Action), placeholder(op.Path), placeholder(op.OldContentHash), placeholder(op.ContentHash), placeholder(op.NewPath))
			if i < len(e.Operations)-1 {
				b.WriteString(opSeparator)
			}
		}
	}
	_ = os.WriteFile(m.statePath, []byte(b.String()), 0644)
}

func (m *StateManager) Sync() {
	if m.state.CurrentIndex < 0 {
		return
	}

	for i := m.state.CurrentIndex; i >= 0; i-- {
		if m.matchState(i) {
			if i < m.state.CurrentIndex {
				m.state.History = m.state.History[:i+1]
				m.state.CurrentIndex = i
				m.save()
			}
			return
		}
	}

	m.state.History = []HistoryEntry{}
	m.state.CurrentIndex = -1
	m.save()
}

func (m *StateManager) matchState(idx int) bool {
	if idx < 0 || idx >= len(m.state.History) {
		return false
	}

	entry := m.state.History[idx]
	for _, op := range entry.Operations {
		path := op.Path
		if op.Action == "rename" {
			path = op.NewPath
		}
		
		currentHash, err := GetFileSHA256(path)
		if op.Action == "delete" {
			if err == nil {
				return false
			}
			continue
		}

		if err != nil || currentHash != op.ContentHash {
			return false
		}
	}
	return true
}

func (m *StateManager) Write(ops []Operation) {
	m.Sync()
	if m.state.CurrentIndex < len(m.state.History)-1 {
		m.state.History = m.state.History[:m.state.CurrentIndex+1]
	}
	m.state.History = append(m.state.History, HistoryEntry{Operations: ops})
	m.state.CurrentIndex++
	m.save()
}

func (m *StateManager) GetOperationsToUndo() []Operation {
	if m.state.CurrentIndex < 0 {
		return nil
	}
	ops := m.state.History[m.state.CurrentIndex].Operations
	m.state.CurrentIndex--
	m.save()
	return ops
}

func (m *StateManager) GetOperationsToRedo() []Operation {
	if m.state.CurrentIndex+1 >= len(m.state.History) {
		return nil
	}
	m.state.CurrentIndex++
	ops := m.state.History[m.state.CurrentIndex].Operations
	m.save()
	return ops
}

func (m *StateManager) CreateOperations(updated []string, actions map[string]string, renames []FileRename, oldHashes map[string]string) []Operation {
	var ops []Operation
	rm := make(map[string]string)
	for _, r := range renames {
		rm[r.OldPath] = r.NewPath
	}

	now := time.Now().UTC().Unix()
	for _, f := range updated {
		action := actions[f]
		checkPath, newPath := f, ""
		
		if action == "rename" {
			newPath = rm[f]
			checkPath = newPath
		} else if action == "delete" {
			rel, _ := filepath.Rel(".", f)
			checkPath = filepath.Join(m.StateDir, TrashDir, rel)
		}

		currentHash, _ := GetFileSHA256(checkPath)
		if action != "delete" && currentHash != "" {
			content, _ := os.ReadFile(checkPath)
			_ = WriteBlob(m.StateDir, currentHash, content)
		}

		ops = append(ops, Operation{
			Timestamp:      now,
			Path:           f,
			Action:         action,
			OldContentHash: oldHashes[f],
			ContentHash:    currentHash,
			NewPath:        newPath,
		})
	}
	sort.Slice(ops, func(i, j int) bool { return ops[i].Path < ops[j].Path })
	return ops
}
