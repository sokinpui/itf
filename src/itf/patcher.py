# ./src/itf/patcher.py
import os
import re
import subprocess
from typing import Iterator, Tuple

from .printer import print_error, print_info, print_success, print_warning

# Regex to find a complete markdown-style diff block.
DIFF_BLOCK_REGEX = re.compile(r"```diff\n(.*?)\n```", re.DOTALL)

# Regex to extract a file path from a '+++ b/...' line in a diff.
# It handles potential trailing metadata like timestamps.
FILE_PATH_REGEX = re.compile(r"^\+\+\+ b/(?P<path>.*?)(\s|$)")


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


def _apply_patch(patch_content: str, file_path_for_logging: str) -> bool:
    """
    Applies a single patch using the system's `patch` command.

    Args:
        patch_content: The full text of the diff to apply.
        file_path_for_logging: The path to the file used for logging messages.

    Returns:
        True if the patch was applied successfully, False otherwise.
    """
    try:
        # Use '-p1' to strip the 'a/' and 'b/' prefixes from paths.
        # '-N' ignores patches that seem to be already applied.
        # '--no-backup-if-mismatch' prevents creation of .rej/.orig files.
        command = ["patch", "-p1", "-N", "--no-backup-if-mismatch"]
        result = subprocess.run(
            command,
            input=patch_content,
            text=True,
            capture_output=True,
            cwd=os.getcwd(),  # Run from the current working directory
        )

        if result.returncode != 0:
            print_error(f"  -> Failed to patch: {file_path_for_logging}")
            error_details = result.stderr.strip()
            print_error(f"     `patch` command failed:\n{error_details}")
            return False

        print_success(f"  -> Successfully patched: {file_path_for_logging}")
        if result.stdout:
            print_info(f"     {result.stdout.strip()}")
        return True

    except FileNotFoundError:
        # This check is primarily done in __main__, but serves as a safeguard.
        print_error("`patch` command not found. It must be installed and in your PATH.")
        return False
    except Exception as e:
        print_error(f"An unexpected error occurred while running `patch`: {e}")
        return False


def find_and_apply_patches(source_content: str) -> Iterator[Tuple[str, bool]]:
    """
    Finds diff blocks, applies them via the `patch` command, and yields results.

    This function modifies files on the filesystem directly.

    Args:
        source_content: The string content containing one or more diff blocks.

    Yields:
        A tuple containing the file path and a boolean indicating success.
    """
    diff_matches = list(DIFF_BLOCK_REGEX.finditer(source_content))
    if not diff_matches:
        print_warning("No '```diff' blocks found in the source content.")
        return

    print_info(f"Found {len(diff_matches)} diff block(s) to apply.")

    for match in diff_matches:
        patch_content = match.group(1).strip()
        if not patch_content.endswith('\n'):
            patch_content += '\n'

        path_match = FILE_PATH_REGEX.search(patch_content)
        if not path_match:
            print_warning("  -> Found a diff block but could not extract a file path. Skipping.")
            print_warning(f"     Block starts with: '{patch_content.splitlines()[0]}'")
            continue

        file_path = path_match.group("path").strip()
        success = _apply_patch(patch_content, file_path)
        yield file_path, success

