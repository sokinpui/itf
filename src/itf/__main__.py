# src/itf/__main__.py
import argparse
import os
import sys

from .editor import NeovimManager
from .parser import parse_file_blocks

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
        print(
            f"Error: Source file '{SOURCE_FILE_NAME}' not found in the current directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"--- Starting Neovim buffer update from '{source_path}' ---")
    try:
        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError as e:
        print(f"Error reading source file: {e}", file=sys.stderr)
        sys.exit(1)

    file_blocks = list(parse_file_blocks(content))
    if not file_blocks:
        print("No valid file blocks found to process.")
        sys.exit(0)

    try:
        with NeovimManager() as manager:
            for file_path, content_lines in file_blocks:
                print(f"Processing: {file_path}")
                manager.update_buffer(file_path, content_lines)

            print(f"\n--- Buffer update complete ---")
            print(f"Successfully processed {len(file_blocks)} block(s) in Neovim.")

            if args.save:
                manager.save_all_buffers()

    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
