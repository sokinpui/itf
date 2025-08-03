# ITF: Insert To File

Tired of copying code from LLM Web interfaces.
Too lazy to paste into multiple files.
Don't have cash for Cursor AI.

`itf` is a command-line tool that parses LLM-generated code snippets from a local file or your clipboard and loads the content directly into Neovim buffers. It can handle both full file replacements and applying `diff` patches, streamlining the process of transferring code from a prompt to your project.

# Features

- **Clipboard & File Support**: Process content directly from your system clipboard (`--clipboard`) or from a local `itf.txt` file.
- **Seamless Neovim Integration**: Automatically connects to a running Neovim instance. If none is found, it transparently starts and manages a temporary headless instance.
- **Persistent Undo History**: Changes made by `itf` are integrated into Neovim's persistent undo tree. You can undo `itf`'s modifications just like any other change, directly within your editor.
- **Two Powerful Modes**:
  - **Block Mode**: Overwrite or create files using simple markdown code blocks.
  - **Diff Mode**: Apply targeted changes to existing files using standard `diff` patches.
- **Revert Last Operation**: A `--revert` command to safely undo the entire last set of changes that were saved to disk.
- **Automatic Directory Creation**: Prompts to create any necessary parent directories for new files, ensuring paths are valid before writing.
- **Cross-Platform**: Works on macOS, Linux (X11/Wayland), and Windows.

# Dependencies

- **Neovim** (v0.9+)
- **Python** (v3.8+) with the `pynvim` and `colorama` packages.
- **`patch`**: The standard command-line patch utility.
  - **Debian/Ubuntu**: `sudo apt install build-essential`
  - **macOS**: `xcode-select --install`
  - **Windows**: Use Linux or MacOS

# Installation

```bash
# Clone the repository
git clone https://github.com/sokinpui/itf.git itf
cd itf

# Install using pipx (recommended)
pipx install .
```

# Usage

`itf` can read from a local `itf.txt` file in the current directory or directly from the system clipboard.

```sh
# Update Neovim buffers from itf.txt (changes are not saved to disk)
itf

# Update buffers and save all changes to disk
itf --save

# Parse from clipboard and save to disk
itf --clipboard --save

# Apply patches from a diff in the clipboard and save changes
itf --diff --clipboard --save

# Revert the last change made with --save
itf --revert

# Show all available options
itf --help
```

# How It Works

1.  `itf` reads content from `itf.txt` or the clipboard.
2.  It parses the content for file blocks or diffs.
3.  It checks for any new directories that need to be created and asks for your confirmation.
4.  It connects to an existing Neovim instance or starts a temporary one.
5.  **In Block Mode**, it replaces the content of the corresponding Neovim buffers.
6.  **In Diff Mode**, it uses the `patch` command to modify the files on disk and then reloads them into Neovim.
7.  If `--save` is used, `itf` instructs Neovim to write all changes to disk and creates a `.itf_state.json` file to enable the revert feature.

# Input Format

`itf` supports two modes for processing input: **File Block Mode** (default) for full file content and **Diff/Patch Mode** (`--diff`) for applying patches.

## File Block Mode (Default)

The default mode expects one or more markdown code blocks. Each block will completely overwrite the content of its target file. The file path can be specified in one of two ways.

**1. Path in First Line Comment**

Place a comment on the first line of the code block containing the file path. This is the most explicit and recommended method. `itf` recognizes various comment styles (`#`, `//`, `/* ... */`, etc.).

_Example (`itf.txt`):_

```python
# src/main.py
import os

def main():
    print("Hello from main!")

if __name__ == "__main__":
    main()
```

```css
/* static/css/styles.css */
body {
  font-family: sans-serif;
  color: #333;
}
```

**2. Path Hint Before Code Block**

Place the file path in backticks on its own line immediately before the code block. `itf` will automatically add a commented header with the path to the file's content.

_Note: If a path is specified using both the hint and an in-block comment, the in-block comment takes precedence._

_Example (`itf.txt`):_

`src/utils/helpers.py`

```python
def helper_function():
    return "This is a helper."
```

## Diff/Patch Mode (`--diff`)

When using the `--diff` flag, `itf` looks for standard markdown diff blocks and applies them using the system `patch` command. This is ideal for making targeted changes to existing files.

The file path is automatically extracted from the `+++ b/path/to/your/file` line within the diff.

_Example (`itf.txt` with `--diff` flag):_

```diff
--- a/src/main.py
+++ b/src/main.py
@@ -1,7 +1,8 @@
 import os

 def main():
-    print("Hello from main!")
+    # A new, more welcoming message
+    print("Hello, world! Welcome to ITF.")

 if __name__ == "__main__":
     main()
```

# The Revert Feature

You can undo the last operation by running `itf --revert`.

- **Prerequisite**: The revert feature only works if the last command was run with `--save`, which creates a state file (`.itf_state.json`) in your project's root directory.
- **Functionality**: Revert will restore all files modified in the previous run to their prior state.
  - For files that were **modified**, their content is reverted using Neovim's undo history.
  - For files that were **created**, `itf` will delete them.
- **State File**: Upon a successful revert of all files, the `.itf_state.json` file is automatically deleted.
