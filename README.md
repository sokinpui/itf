# ITF: Insert To File (The "True Vibe Coding" Companion)

Tired of copying code from LLM Web interface.

I am too lazy to paste.

Don't have cash for Cursor AI...

`itf` parse LLM response directly into Neovim buffers

# Dependencies

- Neovim 0.9+
- Python 3.8+

# Installation

```
git clone https://github.com/sokinpui/itf.git itf
cd itf
pip install .
```

# Usage

ITF looks for an `itf.txt` file in your current directory by default, but it can also suck content straight from your clipboard directly.

```sh
# update buffer (not saved to disk)
itf

# Save to disk
itf --save

# parse from clipboard and save to disk
itf --save --clipboard

# help
itf --help
```

## format requirements

To use this tools, you should put a coment line that contain only the relative path to the file.
Also better for AI understanding which file you are providing if the file cannot be upload directly, Yes I am talking about you, AI studio.

Example:

```python
# src/main.py
.
.
.
```

or

```python
# src/itf/editor.py
```
