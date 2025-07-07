# ./src/itf/__main__.py
import argparse
import os
import sys

from .editor import NeovimManager
from .parser import parse_file_blocks
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

SOURCE_FILE_NAME = "itf.txt"


def main():
    """Main entry point for the 'itf' command-line tool."""
    parser = argparse.ArgumentParser(
        description=f"Parse '{SOURCE_FILE_NAME}' in the current directory and update Neovim buffers."
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save all modified buffers in Neovim after the update.",
    )
    args = parser.parse_args()

    source_path = os.path.join(os.getcwd(), SOURCE_FILE_NAME)

    if not os.path.exists(source_path):
        print_error(
            f"Error: Source file '{SOURCE_FILE_NAME}' not found in the current directory."
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

    try:
        with NeovimManager() as manager:
            progress_bar = ProgressBar(total=len(file_blocks))

            for file_path, content_lines in file_blocks:
                print_info(f"\nProcessing: {file_path}")
                manager.update_buffer(file_path, content_lines)
                progress_bar.update()

            progress_bar.finish()
            print_header(f"\n--- Buffer update complete ---")
            print_success(
                f"Successfully processed {len(file_blocks)} block(s) in Neovim."
            )

            if args.save:
                manager.save_all_buffers()

    except Exception as e:
        print_error(f"\nAn unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
