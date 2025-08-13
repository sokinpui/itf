# ./src/itf/__main__.py
import argparse
import os
import shutil
import subprocess
import sys

from .diff_corrector import correct_diff
from .editor import NeovimManager
from .parser import parse_file_blocks
from .patcher import (
    DIFF_BLOCK_REGEX,
    FILE_PATH_REGEX,
    extract_target_paths,
    generate_patched_contents,
)
from .printer import (
    ProgressBar,
    print_error,
    print_header,
    print_info,
    print_path,
    print_success,
    print_warning,
    prompt_user,
)
from .state import STATE_FILE_NAME, read_last_run_state, write_last_run_state

SOURCE_FILE_NAME = "itf.txt"


def get_clipboard_content(exit_on_empty: bool = True) -> str:
    """
    Retrieves content from the system clipboard using platform-specific tools.
    """
    # The rest of the function remains the same...
    platform = sys.platform
    command = []

    if platform == "darwin":  # macOS
        command = ["pbpaste"]
    elif platform == "linux":
        if shutil.which("wl-paste"):
            command = ["wl-paste", "--no-newline"]
        elif shutil.which("xclip"):
            command = ["xclip", "-selection", "clipboard", "-o"]
        else:
            print_error(
                "Clipboard utility not found. Please install 'wl-clipboard' or 'xclip'."
            )
            sys.exit(1)
    elif platform == "win32":  # Windows
        command = ["powershell", "-command", "Get-Clipboard"]
    else:
        print_error(f"Unsupported platform for clipboard access: {platform}")
        sys.exit(1)

    try:
        content = subprocess.check_output(command, text=True, stderr=subprocess.PIPE)
        if not content.strip():
            if exit_on_empty:
                print_warning("Clipboard is empty. Nothing to process.")
                sys.exit(0)
            return ""
        return content
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print_error(f"Failed to get clipboard content using '{' '.join(command)}': {e}")
        sys.exit(1)


def _confirm_and_create_directories(dirs_to_create: set[str]):
    """Prompts the user to create directories and creates them if confirmed."""
    if not dirs_to_create:
        print_info("\nNo new directories need to be created.")
        return

    print_info("\nThe following directories need to be created:")
    for d in sorted(list(dirs_to_create)):
        print_path(f"- {d}")

    try:
        response = prompt_user(
            "Do you want to create all these directories? (y/N):"
        ).lower()
        if response != "y":
            print_warning("Directory creation declined. Exiting.")
            sys.exit(0)
    except (EOFError, KeyboardInterrupt):
        print_warning("\nOperation cancelled by user. Exiting.")
        sys.exit(0)

    print_info("\nCreating directories...")
    for d in sorted(list(dirs_to_create)):
        try:
            os.makedirs(d, exist_ok=True)
            print_success(f"  -> Created: {d}")
        except OSError as e:
            print_error(f"  -> Error creating directory '{d}': {e}")
            print_error("Aborting due to directory creation failure.")
            sys.exit(1)


def _apply_changes_in_nvim(
    file_blocks: list[tuple[str, list[str]]], file_actions: dict[str, str], args
):
    """Applies a list of file content changes through Neovim and handles saving."""
    file_actions = {
        os.path.abspath(fp): "create" if not os.path.exists(fp) else "modify"
        for fp, _ in file_blocks
    }
    directories_to_create = set()
    for file_path, _ in file_blocks:
        abs_file_path = os.path.abspath(file_path)
        target_dir = os.path.dirname(abs_file_path)
        if target_dir and not os.path.exists(target_dir):
            directories_to_create.add(target_dir)

    updated_files, failed_files = [], []
    with NeovimManager() as manager:
        progress_bar = ProgressBar(total=len(file_blocks), prefix="Updating buffers:")
        progress_bar.update(0)

        for file_path, content_lines in file_blocks:
            if manager.update_buffer(file_path, content_lines):
                updated_files.append(file_path)
            else:
                failed_files.append(file_path)
            progress_bar.update()
        progress_bar.finish()

        print_header("\n--- Update Summary ---", file=sys.stdout)
        if updated_files:
            print_success(
                f"Successfully updated {len(updated_files)} file(s) in Neovim:",
                file=sys.stdout,
            )
            for f in updated_files:
                print(f"  - {f}", file=sys.stdout)
        if failed_files:
            print_error(
                f"Failed to process {len(failed_files)} file(s):", file=sys.stdout
            )
            for f in failed_files:
                print(f"  - {f}", file=sys.stdout)

        if updated_files:
            if args.save:
                manager.save_all_buffers()
                successful_ops = [
                    {
                        "path": os.path.abspath(f),
                        "action": file_actions[os.path.abspath(f)],
                    }
                    for f in updated_files
                ]
                write_last_run_state(successful_ops)
            else:
                print_warning(
                    "\nChanges are not saved to disk. Use -s/--save to persist changes.",
                    file=sys.stdout,
                )
                print_warning(
                    "Revert will not be available for this operation.", file=sys.stdout
                )


def _handle_block_mode(content: str, args):
    """Workflow for replacing file contents based on code blocks."""
    file_blocks = list(parse_file_blocks(content))
    if not file_blocks:
        print_warning("No valid file blocks found to process.")
        sys.exit(0)

    # Determine actions and directories to create before any modifications
    file_actions = {
        os.path.abspath(fp): "create" if not os.path.exists(fp) else "modify"
        for fp, _ in file_blocks
    }
    directories_to_create = set()
    for file_path, _ in file_blocks:
        abs_file_path = os.path.abspath(file_path)
        target_dir = os.path.dirname(abs_file_path)
        if target_dir and not os.path.exists(target_dir):
            directories_to_create.add(target_dir)

    _confirm_and_create_directories(directories_to_create)

    _apply_changes_in_nvim(file_blocks, file_actions, args)


def _get_file_actions_and_dirs(
    target_paths: list[str],
) -> tuple[dict[str, str], set[str]]:
    """Computes file actions and directories to create from a list of paths."""
    file_actions = {
        os.path.abspath(fp): "create" if not os.path.exists(fp) else "modify"
        for fp in target_paths
    }
    directories_to_create = set()
    for file_path in target_paths:
        abs_file_path = os.path.abspath(file_path)
        target_dir = os.path.dirname(abs_file_path)
        if target_dir and not os.path.exists(target_dir):
            directories_to_create.add(target_dir)
    return file_actions, directories_to_create


def _handle_diff_mode(content: str, args):
    """Workflow for patching files based on diff blocks."""
    print_header("--- Parsing content as diffs and generating changes ---")
    if not shutil.which("patch"):
        print_error(
            "`patch` command not found. Please install it to use the --diff feature."
        )
        sys.exit(1)

    target_paths = list(extract_target_paths(content))
    if not target_paths:
        print_warning("No '```diff' blocks with file paths found. Nothing to do.")
        sys.exit(0)

    file_actions, directories_to_create = _get_file_actions_and_dirs(target_paths)
    _confirm_and_create_directories(directories_to_create)

    file_blocks = list(generate_patched_contents(content))
    if not file_blocks:
        print_warning("No valid changes were generated from the diff blocks.")
        sys.exit(0)

    _apply_changes_in_nvim(file_blocks, file_actions, args)


def _handle_auto_mode(content: str, args):
    """Workflow for applying both file blocks and diffs from a single source."""
    print_header("--- Auto-detecting and applying changes ---")
    if not shutil.which("patch"):
        print_error("`patch` command not found. It is required for --auto mode.")
        sys.exit(1)

    # 1. Get all target paths and determine actions/directories first.
    diff_target_paths = list(extract_target_paths(content))
    normal_file_blocks_initial = list(parse_file_blocks(content))
    block_target_paths = [fp for fp, _ in normal_file_blocks_initial]

    all_target_paths = diff_target_paths + block_target_paths
    if not all_target_paths:
        print_warning("No valid file blocks or diffs found to process.")
        sys.exit(0)

    file_actions, directories_to_create = _get_file_actions_and_dirs(all_target_paths)
    _confirm_and_create_directories(directories_to_create)

    # 2. Generate/parse content.
    print_info("\nGenerating patched content from diffs...")
    diff_file_blocks = list(generate_patched_contents(content))
    normal_file_blocks = normal_file_blocks_initial  # Use cached result

    # 3. Combine, with warning for overwrites.
    paths_from_diffs = {os.path.abspath(fp) for fp, _ in diff_file_blocks}
    paths_from_blocks = {os.path.abspath(fp) for fp, _ in normal_file_blocks}
    intersection = paths_from_diffs.intersection(paths_from_blocks)

    if intersection:
        print_warning(
            "\nWarning: The following files are targeted by both a diff and a file block:"
        )
        for p in sorted(list(intersection)):
            print_path(f"- {p}")
        print_warning("The file block content will overwrite the diff patch result.")

    final_file_blocks_map = {}
    # Diffs go in first
    for fp, content_lines in diff_file_blocks:
        final_file_blocks_map[os.path.abspath(fp)] = (fp, content_lines)
    # Normal blocks go in second, overwriting any conflicts
    for fp, content_lines in normal_file_blocks:
        final_file_blocks_map[os.path.abspath(fp)] = (fp, content_lines)

    file_blocks = list(final_file_blocks_map.values())

    # 4. Apply changes.
    _apply_changes_in_nvim(file_blocks, file_actions, args)


def _handle_revert(args):
    """Workflow for reverting the last saved operation."""
    print_header("--- Reverting last operation ---")
    ops_to_revert = read_last_run_state()
    if not ops_to_revert:
        sys.exit(1)

    print_info(f"Found {len(ops_to_revert)} file(s) from the last operation to revert:")
    for op in ops_to_revert:
        print_path(f"- {op['path']} (action: {op['action']})")

    try:
        response = prompt_user("Do you want to revert these changes? (y/N):").lower()
        if response != "y":
            print_warning("Revert operation declined. Exiting.")
            sys.exit(0)
    except (EOFError, KeyboardInterrupt):
        print_warning("\nOperation cancelled by user. Exiting.")
        sys.exit(0)

    reverted_files, failed_files = [], []
    with NeovimManager() as manager:
        progress_bar = ProgressBar(total=len(ops_to_revert), prefix="Reverting files:")
        progress_bar.update(0)

        for op in ops_to_revert:
            if manager.revert_file(op["path"], op["action"]):
                reverted_files.append(op["path"])
            else:
                failed_files.append(op["path"])
            progress_bar.update()
        progress_bar.finish()

    print_header("\n--- Revert Summary ---", file=sys.stdout)
    if reverted_files:
        print_success(
            f"Successfully reverted {len(reverted_files)} file(s):", file=sys.stdout
        )
        for f in reverted_files:
            print(f"  - {f}", file=sys.stdout)
    if failed_files:
        print_error(f"Failed to revert {len(failed_files)} file(s):", file=sys.stdout)
        for f in failed_files:
            print(f"  - {f}", file=sys.stdout)

    if reverted_files and not failed_files:
        state_path = os.path.join(os.getcwd(), STATE_FILE_NAME)
        try:
            os.remove(state_path)
            print_info(
                f"\nSuccessfully reverted all changes and removed state file '{state_path}'."
            )
        except OSError as e:
            print_warning(f"Could not remove state file: {e}")


def _handle_output_diff_fix(content: str):
    """
    Parses content for diff blocks, corrects them, and prints the
    corrected diffs to stdout.
    """
    corrected_diffs = []
    for match in DIFF_BLOCK_REGEX.finditer(content):
        patch_content_raw = match.group(1).strip()
        if not patch_content_raw:
            continue

        path_match = FILE_PATH_REGEX.search(patch_content_raw)
        if not path_match:
            continue

        file_path = path_match.group("path").strip()
        abs_file_path = os.path.abspath(file_path)

        source_lines = []
        if os.path.exists(abs_file_path):
            try:
                with open(abs_file_path, "r", encoding="utf-8") as f:
                    source_lines = [line.rstrip("\n") for line in f.readlines()]
            except IOError:
                source_lines = []

        corrected_patch = correct_diff(
            source_lines, patch_content_raw, file_path
        )

        if corrected_patch:
            corrected_diffs.append(corrected_patch)

    if corrected_diffs:
        print("".join(corrected_diffs), end="")


def main():
    """Main entry point for the 'itf' command-line tool."""
    parser = argparse.ArgumentParser(
        description=f"Parse '{SOURCE_FILE_NAME}' or clipboard content and update files, then load into Neovim."
    )
    parser.add_argument(
        "-s",
        "--save",
        action="store_true",
        help="Save all modified buffers in Neovim after the update. Required to enable -r/--revert.",
    )
    parser.add_argument(
        "-c",
        "--clipboard",
        action="store_true",
        help=f"Parse content from the clipboard instead of '{SOURCE_FILE_NAME}'.",
    )
    parser.add_argument(
        "-d",
        "--diff",
        action="store_true",
        help="Parse content as diffs and apply them as patches.",
    )
    parser.add_argument(
        "-a",
        "--auto",
        action="store_true",
        help="Smart mode. Reads from clipboard or itf.txt and processes both file blocks and diffs.",
    )
    parser.add_argument(
        "-o",
        "--output-diff-fix",
        action="store_true",
        help="Corrects diffs from input and prints them to stdout. Overrides other actions.",
    )
    parser.add_argument(
        "-r",
        "--revert",
        action="store_true",
        help="Revert the last change made with -s/--save.",
    )
    args = parser.parse_args()

    # Handle revert as a standalone action
    if args.revert:
        _handle_revert(args)
        sys.exit(0)

    source_description = ""
    content = ""

    if args.auto:
        print_header("--- Auto mode: searching for content ---")
        # Try clipboard first, but don't exit if it's empty.
        clipboard_content = get_clipboard_content(exit_on_empty=False)
        if clipboard_content.strip():
            content = clipboard_content
            source_description = "from system clipboard"
            print_info("-> Found content in clipboard.")
        else:
            # Fallback to file
            source_path = os.path.join(os.getcwd(), SOURCE_FILE_NAME)
            if os.path.exists(source_path):
                print_info(
                    f"-> Clipboard is empty, falling back to '{SOURCE_FILE_NAME}'."
                )
                try:
                    with open(source_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    source_description = f"from '{source_path}'"
                except IOError as e:
                    print_error(f"Error reading source file: {e}")
                    sys.exit(1)
            else:
                print_warning(
                    f"Clipboard is empty and '{SOURCE_FILE_NAME}' not found. Nothing to do."
                )
                sys.exit(0)
    elif args.clipboard:
        source_description = "from system clipboard"
        content = get_clipboard_content()
    else:
        source_path = os.path.join(os.getcwd(), SOURCE_FILE_NAME)
        source_description = f"from '{source_path}'"
        if not os.path.exists(source_path):
            print_error(f"Source file '{SOURCE_FILE_NAME}' not found.")
            print_info(f"Use -c to read from clipboard or -a for auto-detection.")
            sys.exit(1)
        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()

    # Handle special action that outputs to stdout and exits.
    if args.output_diff_fix:
        _handle_output_diff_fix(content)
        sys.exit(0)

    try:
        if args.auto:
            _handle_auto_mode(content, args)
        elif args.diff:
            _handle_diff_mode(content, args)
        else:
            _handle_block_mode(content, args)
    except Exception as e:
        print_error(f"\nAn unexpected error occurred during processing: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
