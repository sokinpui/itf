# src/itf/editor.py
import os
import shutil
import subprocess
import sys
import tempfile
import time
from types import TracebackType
from typing import Optional, Type

import pynvim


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
        self._nvim_process: Optional[subprocess.Popen] = (
            None  # Store the Popen object for direct control
        )

    def __enter__(self) -> "NeovimManager":
        """Finds or starts a Neovim instance and establishes a connection."""
        self._connect()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Cleans up the Neovim instance if it was started by this manager."""
        if self._is_self_started and self._nvim_process:
            print("-> Closing temporary Neovim instance...", file=sys.stderr)
            try:
                # Attempt to close the pynvim connection cleanly first
                if self.nvim:
                    self.nvim.close()
            except Exception as e:
                print(f"Warning: Error closing pynvim connection: {e}", file=sys.stderr)

            # Terminate the actual Neovim process using its Popen object
            self._nvim_process.terminate()
            try:
                self._nvim_process.wait(
                    timeout=1
                )  # Give it 1 second to terminate gracefully
                print("-> Temporary Neovim instance terminated.")
            except subprocess.TimeoutExpired:
                print(
                    "-> Warning: Neovim process did not terminate gracefully. Killing...",
                    file=sys.stderr,
                )
                self._nvim_process.kill()  # Force kill if it doesn't terminate
                self._nvim_process.wait()  # Wait for it to be killed after forceful termination

        # Clean up the temporary directory if it was created
        if self._temp_dir:
            shutil.rmtree(self._temp_dir, ignore_errors=True)

    def _connect(self) -> None:
        """Connects to an existing Nvim instance or starts a new one."""
        try:
            # First, try to find an existing Neovim instance by listing servers
            serverlist_raw = subprocess.check_output(
                ["nvim", "--serverlist"], text=True, stderr=subprocess.PIPE
            )
            servers = serverlist_raw.strip().split("\n")
            for server_path in filter(None, servers):
                try:
                    self.nvim = pynvim.attach("socket", path=server_path)
                    # Test connection to ensure it's live (e.g., get mode)
                    self.nvim.api.get_mode()
                    print(
                        f"-> Connected to running Neovim instance at '{server_path}'",
                        file=sys.stderr,
                    )
                    return
                except (
                    pynvim.NvimError,
                    FileNotFoundError,
                    ConnectionRefusedError,
                    BrokenPipeError,
                ):
                    # If connection fails (e.g., stale socket or instance died), try next or start new
                    continue
        except (subprocess.CalledProcessError, FileNotFoundError):
            # 'nvim --serverlist' command failed (e.g., nvim not in PATH) or no servers found
            pass

        # If no running instance was found, start a new temporary one
        print(
            "-> No running Neovim instance found. Starting a temporary one...",
            file=sys.stderr,
        )
        self._temp_dir = tempfile.mkdtemp(prefix="itf-nvim-")
        self._socket_path = os.path.join(self._temp_dir, "nvim.sock")

        try:
            # Start Neovim in headless mode, with a clean config (no plugins/init.vim/init.lua)
            # and detach it from the current process group using preexec_fn=os.setsid.
            self._nvim_process = subprocess.Popen(
                ["nvim", "--headless", "--clean", "--listen", self._socket_path],
                stdout=subprocess.DEVNULL,  # Suppress stdout
                stderr=subprocess.DEVNULL,  # Suppress stderr
                preexec_fn=os.setsid,  # Detach from parent process group
            )

            # Poll for the socket file to appear, giving Neovim time to start up
            max_attempts = 10
            for i in range(max_attempts):
                if os.path.exists(self._socket_path):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError(
                    f"Neovim socket '{self._socket_path}' did not appear after {max_attempts*0.1} seconds."
                )

            self.nvim = pynvim.attach("socket", path=self._socket_path)
            self._is_self_started = True
            print(
                f"-> Started temporary instance with socket '{self._socket_path}'",
                file=sys.stderr,
            )
        except (FileNotFoundError, pynvim.NvimError, RuntimeError) as e:
            print(
                "Fatal: Could not start or connect to a Neovim instance.",
                file=sys.stderr,
            )
            print(f"Error: {e}", file=sys.stderr)
            print(
                "Hint: Is 'nvim' in your system's PATH and executable?", file=sys.stderr
            )
            sys.exit(1)

    def update_buffer(self, file_path: str, content_lines: list[str]) -> None:
        """Updates or creates a buffer with the given content."""
        if not self.nvim:
            raise ConnectionError("Not connected to any Neovim instance.")

        abs_file_path = os.path.abspath(file_path)
        target_dir = os.path.dirname(abs_file_path)

        # Check if the target directory exists. If not, prompt user to create it.
        # An empty target_dir implies the file is in the current working directory,
        # which is assumed to exist.
        if target_dir and not os.path.exists(target_dir):
            print(f"  -> Directory '{target_dir}' does not exist.", file=sys.stderr)
            try:
                response = (
                    input(f"  -> Do you want to create it? (y/N): ").strip().lower()
                )
                if response != "y":
                    print(
                        f"  -> Skipping '{file_path}' (directory creation declined).",
                        file=sys.stderr,
                    )
                    return
                os.makedirs(
                    target_dir, exist_ok=True
                )  # exist_ok=True prevents error if dir created concurrently
                print(f"  -> Directory '{target_dir}' created successfully.")
            except OSError as e:
                print(
                    f"  -> Error creating directory '{target_dir}': {e}",
                    file=sys.stderr,
                )
                print(f"  -> Skipping '{file_path}'.", file=sys.stderr)
                return
            except (
                EOFError
            ):  # Handles case where input stream is closed (e.g., piped input)
                print(
                    f"  -> No input provided for directory creation. Skipping '{file_path}'.",
                    file=sys.stderr,
                )
                return

        # Check if buffer for this file already exists
        target_buf = None
        for buf in self.nvim.api.list_bufs():
            if self.nvim.api.buf_get_name(buf) == abs_file_path:
                target_buf = buf
                break

        # If no buffer exists, create one by opening the file
        if not target_buf:
            print(f"  -> File not open. Creating new buffer for '{file_path}'...")
            escaped_path = self.nvim.api.call_function("fnameescape", [abs_file_path])
            self.nvim.command(f"edit {escaped_path}")
            target_buf = self.nvim.api.get_current_buf()

        try:
            self.nvim.api.buf_set_lines(target_buf, 0, -1, True, content_lines)
            print(f"  -> Successfully updated buffer {target_buf.handle}.")
        except pynvim.NvimError as e:
            print(f"  -> Neovim API Error updating buffer: {e}", file=sys.stderr)

    def save_all_buffers(self) -> None:
        """Saves all modified buffers without triggering autocommands."""
        if not self.nvim:
            raise ConnectionError("Not connected to any Neovim instance.")

        print("\nSaving all modified buffers (without running autocommands)...")
        try:
            # Use 'noa wa!' to write all modified buffers without autocommands
            self.nvim.command("noa wa!")
            print("Save complete.")
        except pynvim.NvimError as e:
            print(f"  -> Neovim API Error saving buffers: {e}", file=sys.stderr)
