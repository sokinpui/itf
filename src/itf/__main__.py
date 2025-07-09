# ./src/itf/__main__.py
import argparse
import os
import sys
import shutil
import subprocess

from .editor import NeovimManager
from .parser import parse_file_blocks
from .patcher import find_and_apply_patches, extract_target_paths
from .printer import (
    print_header, print_info, print_success, print_error,
    print_warning, prompt_user, print_path, ProgressBar
)


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
            print_error("Clipboard utility not found. Please install 'wl-clipboard' or 'xclip'.")
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
        response = prompt_user("Do you want to create all these directories? (y/N):").lower()
        if response != 'y':
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

    directories_to_create = set()
    for file_path, _ in file_blocks:
        abs_file_path = os.path.abspath(file_path)
        target_dir = os.path.dirname(abs_file_path)
        if target_dir and not os.path.exists(target_dir):
            directories_to_create.add(target_dir)

    _confirm_and_create_directories(directories_to_create)

    updated_files, failed_files = [], []
    with NeovimManager() as manager:
        progress_bar = ProgressBar(total=len(file_blocks), prefix='Updating buffers:')
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
            print_success(f"Successfully updated {len(updated_files)} file(s):", file=sys.stdout)
            for f in updated_files:
                print(f"  - {f}", file=sys.stdout)
        if failed_files:
            print_error(f"Failed to process {len(failed_files)} file(s):", file=sys.stdout)
            for f in failed_files:
                print(f"  - {f}", file=sys.stdout)
        if args.save:
            manager.save_all_buffers()


def _handle_diff_mode(content: str, args):
    """Workflow for patching files based on diff blocks."""
    print_header("--- Parsing content as diffs and patching files ---")
    if not shutil.which("patch"):
        print_error("`patch` command not found. Please install it to use the --diff feature.")
        sys.exit(1)

    # Pre-scan for directory creation
    directories_to_create = set()
    for file_path in extract_target_paths(content):
        abs_file_path = os.path.abspath(file_path)
        target_dir = os.path.dirname(abs_file_path)
        if target_dir and not os.path.exists(target_dir):
            directories_to_create.add(target_dir)
    _confirm_and_create_directories(directories_to_create)

    print_info("\nApplying patches...")
    patched_files, failed_patches = [], []
    for file_path, success in find_and_apply_patches(content):
        if success:
            patched_files.append(file_path)
        else:
            failed_patches.append(file_path)

    if not patched_files:
        print_warning("No files were successfully patched.")
        if failed_patches:
             print_error(f"{len(failed_patches)} patch(es) failed to apply. See logs above.")
        sys.exit(0 if not failed_patches else 1)

    print_header("\n--- Loading patched files into Neovim ---")
    updated_files, failed_loading = [], []
    with NeovimManager() as manager:
        progress_bar = ProgressBar(total=len(patched_files), prefix='Loading files:  ')
        progress_bar.update(0)
        for file_path in patched_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    file_content_lines = [line.rstrip('\n') for line in f.readlines()]
                if manager.update_buffer(file_path, file_content_lines):
                    updated_files.append(file_path)
                else:
                    failed_loading.append(file_path)
            except IOError as e:
                print_error(f"\nError reading patched file '{file_path}': {e}")
                failed_loading.append(file_path)
            progress_bar.update()
        progress_bar.finish()

        print_header("\n--- Update Summary ---", file=sys.stdout)
        if updated_files:
            print_success(f"Successfully patched and loaded {len(updated_files)} file(s):", file=sys.stdout)
            for f in updated_files: print(f"  - {f}", file=sys.stdout)
        if failed_patches:
            print_error(f"Failed to apply patch for {len(failed_patches)} file(s):", file=sys.stdout)
            for f in failed_patches: print(f"  - {f}", file=sys.stdout)
        if failed_loading:
            print_warning(f"Patched but failed to load {len(failed_loading)} file(s) into Neovim:", file=sys.stdout)
            for f in failed_loading: print(f"  - {f}", file=sys.stdout)
        if args.save:
            manager.save_all_buffers()


def main():
    """Main entry point for the 'itf' command-line tool."""
    parser = argparse.ArgumentParser(
        description=f"Parse '{SOURCE_FILE_NAME}' or clipboard content and update files, then load into Neovim."
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save all modified buffers in Neovim after the update.",
    )
    parser.add_argument(
        "-c", "--clipboard",
        action="store_true",
        help=f"Parse content from the clipboard instead of '{SOURCE_FILE_NAME}'.",
    )
    parser.add_argument(
        "-d", "--diff",
        action="store_true",
        help="Parse content as diffs and apply them as patches.",
    )
    args = parser.parse_args()

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
