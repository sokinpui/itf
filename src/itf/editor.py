# ./src/itf/editor.py
import os
import shutil
import subprocess
import sys
import tempfile
import time
from types import TracebackType
from typing import Optional, Type

import pynvim

from .printer import print_error, print_info, print_success, print_warning

# Define the standard undo directory path to ensure undo history is preserved
# when using a temporary Neovim instance. This path is a common default
# based on the XDG Base Directory Specification.
UNDO_DIR = os.path.expanduser("~/.local/state/nvim/undo/")


class NeovimManager:
    """
    Manages the connection to a Neovim instance.

    Acts as a context manager to find a running instance or start a temporary
    headless one, ensuring cleanup on exit.
    """

    def __init__(self):
        self.nvim: Optional[pynvim.Nvim] = None
        self._socket_path: Optional[str] = None
        self._temp_dir: Optional[str] = None
        self._is_self_started: bool = False
        self._nvim_process: Optional[subprocess.Popen] = None

    def __enter__(self) -> "NeovimManager":
        self._connect()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self._is_self_started and self._nvim_process:
            print_info("-> Closing temporary Neovim instance...")
            try:
                if self.nvim:
                    self.nvim.close()
            except Exception as e:
                print_warning(f"Warning: Error closing pynvim connection: {e}")

            self._nvim_process.terminate()
            try:
                self._nvim_process.wait(timeout=1)
                print_success("-> Temporary Neovim instance terminated.")
            except subprocess.TimeoutExpired:
                print_warning(
                    "-> Warning: Neovim process did not terminate gracefully. Killing..."
                )
                self._nvim_process.kill()
                self._nvim_process.wait()

        if self._temp_dir:
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _connect(self) -> None:
        try:
            serverlist_raw = subprocess.check_output(
                ["nvim", "--serverlist"], text=True, stderr=subprocess.PIPE
            )
            servers = serverlist_raw.strip().split("\n")
            for server_path in filter(None, servers):
                try:
                    self.nvim = pynvim.attach("socket", path=server_path)
                    self.nvim.api.get_mode()
                    print_info(
                        f"-> Connected to running Neovim instance at '{server_path}'"
                    )
                    return
                except (
                    pynvim.NvimError,
                    FileNotFoundError,
                    ConnectionRefusedError,
                    BrokenPipeError,
                ):
                    continue
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        print_info("-> No running Neovim instance found. Starting a temporary one...")
        self._temp_dir = tempfile.mkdtemp(prefix="itf-nvim-")
        self._socket_path = os.path.join(self._temp_dir, "nvim.sock")

        try:
            # Create the undo directory if it doesn't exist to ensure undofile works.

            self._nvim_process = subprocess.Popen(
                ["nvim", "--headless", "--clean", "--listen", self._socket_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid,
            )

            max_attempts = 10
            for i in range(max_attempts):
                if os.path.exists(self._socket_path):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError(
                    f"Neovim socket '{self._socket_path}' did not appear."
                )

            self.nvim = pynvim.attach("socket", path=self._socket_path)
            self._is_self_started = True

            # Configure the temporary instance for persistent undo history. This makes
            # its changes compatible with the user's main editor session.
            print_info("-> Configuring temporary instance for persistent undo...")
            self.nvim.command("set undofile")
            escaped_undo_dir = self.nvim.api.call_function("fnameescape", [UNDO_DIR])
            self.nvim.command(f"set undodir={escaped_undo_dir}")
            self.nvim.command("set noswapfile")

            print_success(
                f"-> Started temporary instance with socket '{self._socket_path}'"
            )
        except (FileNotFoundError, pynvim.NvimError, RuntimeError) as e:
            print_error("Fatal: Could not start or connect to a Neovim instance.")
            print_error(f"Error: {e}")
            print_info("Hint: Is 'nvim' in your system's PATH and executable?")
            sys.exit(1)

    def update_buffer(self, file_path: str, content_lines: list[str]) -> bool:
        """
        Updates a buffer silently and returns a status.
        Returns: True on success, False on failure.
        """
        if not self.nvim:
            raise ConnectionError("Not connected to any Neovim instance.")

        abs_file_path = os.path.abspath(file_path)

        try:
            target_buf = None
            for buf in self.nvim.api.list_bufs():
                buf_name = self.nvim.api.buf_get_name(buf)
                if buf_name and os.path.abspath(buf_name) == abs_file_path:
                    target_buf = buf
                    break

            if not target_buf:
                escaped_path = self.nvim.api.call_function(
                    "fnameescape", [abs_file_path]
                )
                self.nvim.command(f"edit {escaped_path}")
                target_buf = self.nvim.api.get_current_buf()

            # Ensure we are operating on the correct buffer
            self.nvim.api.set_current_buf(target_buf)
            self.nvim.api.buf_set_lines(target_buf, 0, -1, True, content_lines)
            return True
        except pynvim.NvimError as e:
            # Log the specific error to stderr for immediate visibility if needed
            print_error(f"\nError processing '{file_path}': {e}")
            return False

    def save_all_buffers(self) -> None:
        if not self.nvim:
            raise ConnectionError("Not connected to any Neovim instance.")

        print_info("\nSaving all modified buffers...")
        try:
            # Removed 'noa' to allow autocommands like BufWritePost to run.
            # This is required for the 'undofile' feature to save the undo history,
            # ensuring changes are integrated into the user's persistent undo tree.
            self.nvim.command("wa!")
            print_success("Save complete.")
        except pynvim.NvimError as e:
            print_error(f"  -> Neovim API Error saving buffers: {e}")

    def revert_file(self, file_path: str, action: str) -> bool:
        """
        Opens a file, applies one undo operation, and saves it. If the action
        was 'create', it deletes the file if it becomes empty after undo.
        """
        if not self.nvim:
            raise ConnectionError("Not connected to any Neovim instance.")

        abs_file_path = os.path.abspath(file_path)
        if not os.path.exists(abs_file_path) and action == "modify":
            print_warning(
                f"\nFile '{file_path}' does not exist. Cannot revert modification."
            )
            return False  # Or True if we consider it a "successful" no-op revert

        try:
            escaped_path = self.nvim.api.call_function("fnameescape", [abs_file_path])
            # Open the file, discarding any unsaved changes in the buffer.
            self.nvim.command(f"edit! {escaped_path}")
            target_buf = self.nvim.api.get_current_buf()

            self.nvim.command("undo")

            # For 'create' actions, if undo results in an empty buffer, delete the file.
            if action == "create":
                # An empty buffer returns [] for its lines.
                lines = self.nvim.api.buf_get_lines(target_buf, 0, -1, False)
                if not lines:
                    # Wipe the buffer from memory and delete the file from disk.
                    self.nvim.command("bwipeout!")
                    try:
                        os.remove(abs_file_path)
                    except FileNotFoundError:
                        pass  # File already gone, which is fine.
                    except OSError as e:
                        print_error(
                            f"\nFailed to delete reverted file '{file_path}': {e}"
                        )
                        return False
                    return True

            # For 'modify' actions or non-empty 'create' reverts, save the undone state.
            self.nvim.command("write")
            return True
        except pynvim.NvimError as e:
            print_error(f"\nError reverting '{file_path}': {e}")
            return False

    def redo_file(self, file_path: str, action: str) -> bool:
        """
        Opens a file, applies one redo operation, and saves it.
        """
        if not self.nvim:
            raise ConnectionError("Not connected to any Neovim instance.")

        abs_file_path = os.path.abspath(file_path)

        try:
            escaped_path = self.nvim.api.call_function("fnameescape", [abs_file_path])
            # Open the file, discarding any unsaved changes in the buffer.
            # This is crucial to ensure we are redoing relative to the on-disk state.
            self.nvim.command(f"edit! {escaped_path}")

            self.nvim.command("redo")
            self.nvim.command("write")
            return True
        except pynvim.NvimError as e:
            print_error(f"\nError redoing '{file_path}': {e}")
            return False
