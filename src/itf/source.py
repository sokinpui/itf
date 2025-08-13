# src/itf/source.py
import argparse
import os
import shutil
import subprocess
import sys

from .printer import print_error, print_header, print_info, print_warning

SOURCE_FILE_NAME = "itf.txt"


class SourceProvider:
    def __init__(self, args: argparse.Namespace):
        self.args = args

    def get_content(self) -> str:
        content = ""
        is_auto_or_fix = self.args.auto or self.args.output_diff_fix

        if is_auto_or_fix:
            if not self.args.output_diff_fix:
                print_header("--- Auto mode: searching for content ---")

            clipboard_content = self._get_clipboard_content(exit_on_empty=False)
            if clipboard_content.strip():
                content = clipboard_content
                print_info("-> Found content in clipboard.")
            else:
                source_path = os.path.join(os.getcwd(), SOURCE_FILE_NAME)
                if os.path.exists(source_path):
                    print_info(
                        f"-> Clipboard is empty, falling back to '{SOURCE_FILE_NAME}'."
                    )
                    try:
                        with open(source_path, "r", encoding="utf-8") as f:
                            content = f.read()
                    except IOError as e:
                        print_error(f"Error reading source file: {e}")
                        return ""
                elif not self.args.output_diff_fix:
                    print_warning(
                        f"Clipboard is empty and '{SOURCE_FILE_NAME}' not found. Nothing to do."
                    )
                    return ""
        elif self.args.clipboard:
            content = self._get_clipboard_content()
        else:
            source_path = os.path.join(os.getcwd(), SOURCE_FILE_NAME)
            if not os.path.exists(source_path):
                print_error(f"Source file '{SOURCE_FILE_NAME}' not found.")
                print_info("Use -c to read from clipboard or -a for auto-detection.")
                return ""
            with open(source_path, "r", encoding="utf-8") as f:
                content = f.read()

        if not content.strip():
            print_warning("Source is empty. Nothing to process.")
            return ""
        return content

    @staticmethod
    def _get_clipboard_content(exit_on_empty: bool = True) -> str:
        platform = sys.platform
        command = []

        if platform == "darwin":
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
        elif platform == "win32":
            command = ["powershell", "-command", "Get-Clipboard"]
        else:
            print_error(f"Unsupported platform for clipboard access: {platform}")
            sys.exit(1)

        try:
            content = subprocess.check_output(
                command, text=True, stderr=subprocess.PIPE
            )
            if not content.strip() and exit_on_empty:
                print_warning("Clipboard is empty. Nothing to process.")
                sys.exit(0)
            return content
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print_error(
                f"Failed to get clipboard content using '{' '.join(command)}': {e}"
            )
            sys.exit(1)
