# ./src/itf/__main__.py
import argparse
import sys
import traceback

from .app import ItfApp
from .printer import print_error


def main():
    """Main entry point for the 'itf' command-line tool."""
    parser = argparse.ArgumentParser(
        description="Parse clipboard content or 'itf.txt' to update files and load them into Neovim."
    )
    parser.add_argument(
        "-s",
        "--save",
        action="store_true",
        help="Save all modified buffers in Neovim after the update.",
    )
    parser.add_argument(
        "-c",
        "--clipboard",
        action="store_true",
        help="Parse content from the clipboard instead of 'itf.txt'.",
    )
    parser.add_argument(
        "-o",
        "--output-diff-fix",
        action="store_true",
        help="print the diff that corrected start and count",
    )
    parser.add_argument(
        "-l",
        "--lookup-dir",
        nargs="+",
        metavar="DIR",
        help="change directory to look for files (default: current directory).",
    )
    parser.add_argument(
        "-e",
        "--extension",
        nargs="+",
        metavar="EXT",
        help="Filter to process only files with the specified extensions (e.g., 'py', 'js').",
    )

    history_group = parser.add_mutually_exclusive_group()
    history_group.add_argument(
        "-r",
        "--revert",
        action="store_true",
        help="Revert the last operation. support undo tree, multiple levels of undo",
    )
    history_group.add_argument(
        "-R",
        "--redo",
        action="store_true",
        help="Redo the last reverted operation, support redo tree, multiple levels of redo",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "-f",
        "--file",
        action="store_true",
        help="ignore diff blocks, parse content files blocks only.",
    )
    mode_group.add_argument(
        "-d",
        "--diff",
        action="store_true",
        help="parse only diff blocks, ignore content file blocks.",
    )
    mode_group.add_argument(
        "-a",
        "--auto",
        action="store_true",
        help="parse both diff blocks and content file blocks.",
    )

    args = parser.parse_args()

    try:
        app = ItfApp(args)
        app.run()
    except Exception as e:
        print_error(f"\nAn unexpected error occurred: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
