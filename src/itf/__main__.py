# ./src/itf/__main__.py
import argparse
import os
import sys
import shutil
import subprocess

from .editor import NeovimManager
from .parser import parse_file_blocks
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


def main():
    """Main entry point for the 'itf' command-line tool."""
    parser = argparse.ArgumentParser(
        description=f"Parse '{SOURCE_FILE_NAME}' or clipboard content and update Neovim buffers."
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save all modified buffers in Neovim after the update.",
    )
    parser.add_argument(
        "-c", "--clipboard",
        action="store_true",
        help="Parse content directly from the system clipboard instead of itf.txt."
    )
    args = parser.parse_args()

    content = ""
    if args.clipboard:
        print_header("--- Parsing content from system clipboard ---")
        content = get_clipboard_content()
    else:
        source_path = os.path.join(os.getcwd(), SOURCE_FILE_NAME)
        if not os.path.exists(source_path):
            print_error(
                f"Error: Source file '{SOURCE_FILE_NAME}' not found. "
                f"(Use -c or --clipboard to read from clipboard)."
            )
            sys.exit(1)

        print_header(f"--- Starting Neovim buffer update from '{source_path}' ---")
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                content = f.read()
        except IOError as e:
            print_error(f"Error reading source file: {e}")
            sys.exit(1)

    file_blocks = list(parse_file_blocks(content))
    if not file_blocks:
        print_warning("No valid file blocks found to process.")
        sys.exit(0)

    # Pre-scan and confirm directory creation
    directories_to_create = set()
    for file_path, _ in file_blocks:
        abs_file_path = os.path.abspath(file_path)
        target_dir = os.path.dirname(abs_file_path)

        if target_dir and not os.path.exists(target_dir):
            directories_to_create.add(target_dir)

    if directories_to_create:
        print_info("\nThe following directories need to be created:")
        for d in sorted(list(directories_to_create)):
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
        for d in sorted(list(directories_to_create)):
            try:
                os.makedirs(d, exist_ok=True)
                print_success(f"  -> Created: {d}")
            except OSError as e:
                print_error(f"  -> Error creating directory '{d}': {e}")
                print_error("Aborting due to directory creation failure.")
                sys.exit(1)
    else:
        print_info("\nNo new directories need to be created.")

    # Collect results silently and print summary at the end
    updated_files = []
    failed_files = []
    try:
        with NeovimManager() as manager:
            progress_bar = ProgressBar(total=len(file_blocks))
            progress_bar.update(0) # Initialize the bar display

            for file_path, content_lines in file_blocks:
                success = manager.update_buffer(file_path, content_lines)
                if success:
                    updated_files.append(file_path)
                else:
                    failed_files.append(file_path)
                progress_bar.update()

            progress_bar.finish()

            # Print the final summary report
            print_header("\n--- Update Summary ---", file=sys.stdout)
            if updated_files:
                print_success(f"Successfully updated {len(updated_files)} file(s):", file=sys.stdout)
                for f in updated_files:
                    print(f"  - {f}", file=sys.stdout)

            if failed_files:
                print_error(f"Failed to process {len(failed_files)} file(s):", file=sys.stdout)
                for f in failed_files:
                    print(f"  - {f}", file=sys.stdout)

            if not updated_files and not failed_files:
                print_warning("No files were processed.", file=sys.stdout)


            if args.save:
                manager.save_all_buffers()

    except Exception as e:
        print_error(f"\nAn unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
