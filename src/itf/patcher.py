# ./src/itf/patcher.py
import os
import re
import subprocess
import tempfile
from typing import Iterator, List, Tuple

from .printer import print_error, print_info, print_success, print_warning

# Regex to find a complete markdown-style diff block.
DIFF_BLOCK_REGEX = re.compile(r"```diff\n(.*?)\n```", re.DOTALL)

# Regex to extract a file path from a '+++ b/...' line in a diff.
FILE_PATH_REGEX = re.compile(r"^\+\+\+ b/(?P<path>.*?)(\s|$)", re.MULTILINE)


def extract_target_paths(source_content: str) -> Iterator[str]:
    """
    Parses content for diff blocks and yields the target file paths without
    applying any changes.
    """
    for match in DIFF_BLOCK_REGEX.finditer(source_content):
        patch_content = match.group(1)
        path_match = FILE_PATH_REGEX.search(patch_content)
        if path_match:
            yield path_match.group("path").strip()


def generate_patched_contents(source_content: str) -> Iterator[Tuple[str, List[str]]]:
    """
    Finds diff blocks and yields the patched content without modifying disk files.

    For each diff, it reads the original file, applies the patch to a temporary
    copy, reads the result, and yields the final content lines.

    Yields:
        A tuple of (file_path, list_of_patched_content_lines).
    """
    diff_matches = list(DIFF_BLOCK_REGEX.finditer(source_content))
    if not diff_matches:
        print_warning("No '```diff' blocks found in the source content.")
        return

    print_info(f"Found {len(diff_matches)} diff block(s) to process.")

    for match in diff_matches:
        patch_content = match.group(1).strip()
        if not patch_content:
            continue
        if not patch_content.endswith("\n"):
            patch_content += "\n"

        path_match = FILE_PATH_REGEX.search(patch_content)
        if not path_match:
            print_warning(
                "  -> Found a diff block but could not extract a file path. Skipping."
            )
            print_warning(f"     Block starts with: '{patch_content.splitlines()}'")
            continue

        file_path = path_match.group("path").strip()
        abs_file_path = os.path.abspath(file_path)

        # Determine the source file for patching. If the target file doesn't exist,
        # patch will operate against an empty temporary file (like /dev/null).
        source_for_patch = abs_file_path
        dummy_path = None
        if not os.path.exists(source_for_patch):
            dummy_fd, dummy_path = tempfile.mkstemp()
            os.close(dummy_fd)
            source_for_patch = dummy_path

        # Create a temporary file to hold the output of the patch command.
        output_fd, output_path = tempfile.mkstemp()
        os.close(output_fd)

        try:
            # Command: patch -p1 -o <output_file> <source_file>
            # The patch content itself is piped to stdin.
            command = ["patch", "-p1", "-o", output_path, source_for_patch]
            result = subprocess.run(
                command,
                input=patch_content,
                text=True,
                capture_output=True,
                cwd=os.getcwd(),
            )

            if result.returncode != 0:
                print_error(f"  -> Failed to generate patch for: {file_path}")
                error_details = result.stderr.strip()
                print_error(f"     `patch` command failed:\n{error_details}")
                continue

            print_success(f"  -> Successfully generated patch for: {file_path}")
            if result.stdout:
                print_info(f"     {result.stdout.strip()}")

            with open(output_path, "r", encoding="utf-8") as f:
                patched_lines = [line.rstrip("\n") for line in f.readlines()]

            yield file_path, patched_lines

        finally:
            # Clean up temporary files.
            if dummy_path:
                os.remove(dummy_path)
            os.remove(output_path)
