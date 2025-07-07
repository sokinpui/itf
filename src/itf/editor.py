# ./src/itf/editor.py
import os
import subprocess
import sys
import tempfile
import time
import shutil
from types import TracebackType
from typing import Optional, Type

import pynvim
from .printer import print_info, print_success, print_warning, print_error


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
                print_warning("-> Warning: Neovim process did not terminate gracefully. Killing...")
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
                    print_info(f"-> Connected to running Neovim instance at '{server_path}'")
                    return
                except (pynvim.NvimError, FileNotFoundError, ConnectionRefusedError, BrokenPipeError):
                    continue
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        print_info("-> No running Neovim instance found. Starting a temporary one...")
        self._temp_dir = tempfile.mkdtemp(prefix="itf-nvim-")
        self._socket_path = os.path.join(self._temp_dir, "nvim.sock")

        try:
            self._nvim_process = subprocess.Popen(
                ["nvim", "--headless", "--clean", "--listen", self._socket_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid
            )

            max_attempts = 10
            for i in range(max_attempts):
                if os.path.exists(self._socket_path):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError(f"Neovim socket '{self._socket_path}' did not appear.")

            self.nvim = pynvim.attach("socket", path=self._socket_path)
            self._is_self_started = True
            self.nvim.command("set noswapfile")
            print_success(f"-> Started temporary instance with socket '{self._socket_path}'")
        except (FileNotFoundError, pynvim.NvimError, RuntimeError) as e:
            print_error("Fatal: Could not start or connect to a Neovim instance.")
            print_error(f"Error: {e}")
            print_info("Hint: Is 'nvim' in your system's PATH and executable?")
            sys.exit(1)

    def update_buffer(self, file_path: str, content_lines: list[str]) -> None:
        if not self.nvim:
            raise ConnectionError("Not connected to any Neovim instance.")

        abs_file_path = os.path.abspath(file_path)

        target_buf = None
        for buf in self.nvim.api.list_bufs():
            if self.nvim.api.buf_get_name(buf) == abs_file_path:
                target_buf = buf
                break

        if not target_buf:
            print_info(f"  -> File not open. Creating new buffer for '{file_path}'...")
            escaped_path = self.nvim.api.call_function("fnameescape", [abs_file_path])
            self.nvim.command(f"edit {escaped_path}")
            target_buf = self.nvim.api.get_current_buf()

        try:
            self.nvim.api.buf_set_lines(target_buf, 0, -1, True, content_lines)
            print_success(f"  -> Successfully updated buffer {target_buf.handle}.")
        except pynvim.NvimError as e:
            print_error(f"  -> Neovim API Error updating buffer: {e}")

    def save_all_buffers(self) -> None:
        if not self.nvim:
            raise ConnectionError("Not connected to any Neovim instance.")

        print_info("\nSaving all modified buffers (without running autocommands)...")
        try:
            self.nvim.command("noa wa!")
            print_success("Save complete.")
        except pynvim.NvimError as e:
            print_error(f"  -> Neovim API Error saving buffers: {e}")
