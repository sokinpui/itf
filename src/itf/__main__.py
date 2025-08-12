# ./src/itf/__main__.py
import argparse
import os
import shutil
import subprocess
import sys

from .editor import NeovimManager
from .parser import parse_file_blocks

# MODIFIED: Import the new function and remove the old ones
from .patcher import extract_target_paths, generate_patched_contents
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


def get_clipboard_content() -> str:
    """
    Retrieves content from the system clipboard using platform-specific tools.
    """
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
            print_warning("Clipboard is empty. Nothing to process.")
            sys.exit(0)
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


def _handle_diff_mode(content: str, args):
    """Workflow for patching files based on diff blocks."""
    print_header("--- Parsing content as diffs and generating changes ---")
    if not shutil.which("patch"):
        print_error(
            "`patch` command not found. Please install it to use the --diff feature."
        )
        sys.exit(1)

    # Pre-scan for directory creation and action type, same as before.
    target_paths = list(extract_target_paths(content))
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
    _confirm_and_create_directories(directories_to_create)

    # MODIFIED: This section is now almost identical to _handle_block_mode.
    # It generates the content first, then applies it through Neovim.
    file_blocks = list(generate_patched_contents(content))
    if not file_blocks:
        print_warning("No valid changes were generated from the diff blocks.")
        sys.exit(0)

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
                f"Successfully loaded {len(updated_files)} change(s) into Neovim:",
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

    content = ""
    if args.clipboard:
        print_header("--- Parsing content from system clipboard ---")
        content = get_clipboard_content()
    else:
        source_path = os.path.join(os.getcwd(), SOURCE_FILE_NAME)
        if not os.path.exists(source_path):
            print_error(f"Source file '{SOURCE_FILE_NAME}' not found.")
            print_info(f"Use -c to read from clipboard or -d to apply patches.")
            sys.exit(1)

        print_header(f"--- Parsing content from '{source_path}' ---")
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                content = f.read()
        except IOError as e:
            print_error(f"Error reading source file: {e}")
            sys.exit(1)

    try:
        if args.diff:
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
