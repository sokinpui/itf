# src/itf/diff_corrector.py
import sys
from typing import List

from .printer import print_warning


def get_target_block(diff: List[str]) -> List[str]:
    """
    Constructs the target code block from a diff hunk for matching.

    This block represents the "before" state of the change. It includes
    context lines (starting with ' ') and removed lines (starting with '-').
    """
    block = []
    for line in diff:
        if line.startswith("-"):
            block.append(line[1:])
        elif line.startswith("+"):
            continue
        else:
            block.append(line)
    return block


def match_block(source: List[str], block: List[str]) -> int:
    """
    Finds the starting line number of a block within the source code.

    It performs a line-by-line comparison after stripping whitespace from
    both source and block lines to be robust against formatting differences.
    Returns a 1-based line number for the match, or -1 if not found.
    """
    stripped_block = [line.strip() for line in block]
    stripped_source = [line.strip() for line in source]

    for i in range(len(stripped_source) - len(stripped_block) + 1):
        if stripped_source[i : i + len(stripped_block)] == stripped_block:
            return i + 1
    return -1


def build_hunk_header(
    old_start: int, old_count: int, new_start: int, new_count: int
) -> str:
    """Formats the '@@ ... @@' hunk header string."""
    return f"@@ -{old_start},{old_count} +{new_start},{new_count} @@\n"


def parse_diff_to_hunks(diff_lines: List[str]) -> List[List[str]]:
    """
    Splits a list of diff lines into separate hunks.

    It uses '@@' as a delimiter but discards the original, faulty hunk headers.
    It also filters out file headers ('---', '+++').
    """
    if not diff_lines:
        return []

    hunks = []
    current_hunk = []
    lines_to_process = [
        line
        for line in diff_lines
        if not (line.startswith("---") or line.startswith("+++"))
    ]

    for line in lines_to_process:
        if line.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = []
        elif line.startswith(("+", "-", " ", "\n")):
            current_hunk.append(line)

    if current_hunk:
        hunks.append(current_hunk)

    return hunks


def correct_diff(
    source_lines: List[str], raw_diff_content: str, source_file_path: str
) -> str:
    """
    Takes source file content and a faulty diff string, and returns a
    corrected, valid unified diff string.
    """
    diff_lines = [line + "\n" for line in raw_diff_content.splitlines()]
    sub_hunks = parse_diff_to_hunks(diff_lines)
    if not sub_hunks:
        return ""

    line_diff_offset = 0
    corrected_diff_parts = [
        f"--- a/{source_file_path}\n",
        f"+++ b/{source_file_path}\n",
    ]

    for hunk_lines in sub_hunks:
        if not hunk_lines:
            continue

        hunk_lines_no_newline = [line.rstrip("\n") for line in hunk_lines]
        target_block = get_target_block(hunk_lines_no_newline)
        old_start = match_block(source_lines, target_block)

        if old_start == -1:
            print_warning(
                f"  -> Could not find matching block for a hunk in '{source_file_path}'. Skipping hunk."
            )
            continue

        add_count = sum(1 for line in hunk_lines_no_newline if line.startswith("+"))
        remove_count = sum(1 for line in hunk_lines_no_newline if line.startswith("-"))
        context_count = len(hunk_lines_no_newline) - add_count - remove_count

        old_count = context_count + remove_count
        new_count = context_count + add_count
        new_start = old_start + line_diff_offset

        header = build_hunk_header(old_start, old_count, new_start, new_count)
        corrected_diff_parts.append(header)
        corrected_diff_parts.extend(hunk_lines)

        line_diff_offset += new_count - old_count

    return "".join(corrected_diff_parts)
