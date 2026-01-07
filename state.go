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
	stateDirName  = ".itf"
	stateFileName = "state.itf"
	TrashDir      = "trash"
)

type Operation struct {
	Path        string
	Action      string
	ContentHash string
	NewPath     string
}

type HistoryEntry struct {
	Timestamp  int64
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
	if err := m.load(); err != nil {
		m.state = &State{CurrentIndex: -1, History: []HistoryEntry{}}
	}
	return m, nil
}

func (m *StateManager) load() error {
	data, err := os.ReadFile(m.statePath)
	if err != nil {
		return err
	}

	blocks := strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n\n")
	if len(blocks) == 0 {
		return nil
	}

	idx, _ := strconv.Atoi(strings.TrimSpace(blocks[0]))
	m.state = &State{CurrentIndex: idx, History: []HistoryEntry{}}

	for _, b := range blocks[1:] {
		lines := strings.Split(strings.TrimSpace(b), "\n")
		if len(lines) == 0 {
			continue
		}
		ts, _ := strconv.ParseInt(lines[0], 10, 64)
		entry := HistoryEntry{Timestamp: ts}
		for i := 1; i < len(lines); {
			op := Operation{Action: lines[i], Path: lines[i+1], ContentHash: lines[i+2]}
			i += 3
			if op.Action == "rename" {
				op.NewPath = lines[i]
				i++
			}
			entry.Operations = append(entry.Operations, op)
		}
		m.state.History = append(m.state.History, entry)
	}
	return nil
}

func (m *StateManager) save() {
	var b strings.Builder
	b.WriteString(fmt.Sprintf("%d", m.state.CurrentIndex))
	for _, e := range m.state.History {
		b.WriteString(fmt.Sprintf("\n\n%d", e.Timestamp))
		for _, op := range e.Operations {
			b.WriteString(fmt.Sprintf("\n%s\n%s\n%s", op.Action, op.Path, op.ContentHash))
			if op.Action == "rename" {
				b.WriteString("\n" + op.NewPath)
			}
		}
	}
	os.WriteFile(m.statePath, []byte(b.String()), 0644)
}

func (m *StateManager) Write(ops []Operation) {
	if m.state.CurrentIndex < len(m.state.History)-1 {
		m.state.History = m.state.History[:m.state.CurrentIndex+1]
	}
	m.state.History = append(m.state.History, HistoryEntry{Timestamp: time.Now().UTC().Unix(), Operations: ops})
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

func (m *StateManager) CreateOperations(updated []string, actions map[string]string, renames []FileRename) []Operation {
	var ops []Operation
	rm := make(map[string]string)
	for _, r := range renames {
		rm[r.OldPath] = r.NewPath
	}

	for _, f := range updated {
		a := actions[f]
		pfh, np := f, ""
		if a == "delete" {
			rel, _ := filepath.Rel(".", f)
			pfh = filepath.Join(m.StateDir, TrashDir, rel)
		} else if a == "rename" {
			np = rm[f]
			pfh = np
		}
		h, _ := GetFileSHA256(pfh)
		ops = append(ops, Operation{Path: f, Action: a, ContentHash: h, NewPath: np})
	}
	sort.Slice(ops, func(i, j int) bool { return ops[i].Path < ops[j].Path })
	return ops
}
