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
        help="Save all modified buffers in Neovim after the update. Required to enable -r/--revert.",
    )
    parser.add_argument(
        "-c",
        "--clipboard",
        action="store_true",
        help="Parse content from the clipboard instead of 'itf.txt'.",
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
    parser.add_argument(
        "-l",
        "--lookup-dir",
        nargs="+",
        metavar="DIR",
        help="One or more directories to search for files. New files are created in the first directory.",
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
