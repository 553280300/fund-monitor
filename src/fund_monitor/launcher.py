from collections.abc import Callable, Sequence
import ctypes
import threading
import time
import traceback
from urllib.request import urlopen
import webbrowser


class WindowsInstanceGuard:
    """Named mutex guard shared by all launches of the installed app."""

    def __init__(self, name: str = "Local\\FundMonitorDesktop") -> None:
        self._name = name
        self._handle: int | None = None

    def acquire(self) -> bool:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        create_mutex.restype = ctypes.c_void_p
        handle = create_mutex(None, False, self._name)
        if not handle:
            raise OSError("Could not create application mutex")
        self._handle = handle
        return ctypes.get_last_error() != 183

    def release(self) -> None:
        if self._handle is not None:
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self._handle)
            self._handle = None


class Launcher:
    def __init__(
        self, *, guard, server_runner: Callable[[], int], browser_open: Callable[[str], object], panel_url: str,
        wait_for_health: Callable[[str], bool] | None = None,
    ) -> None:
        self._guard = guard
        self._server_runner = server_runner
        self._browser_open = browser_open
        self._panel_url = panel_url
        self._wait_for_health = wait_for_health or self._default_wait_for_health

    def run(self) -> int:
        if not self._guard.acquire():
            self._browser_open(self._panel_url)
            return 0
        try:
            result: list[int] = [1]

            def run_server() -> None:
                try:
                    result[0] = self._server_runner()
                except Exception:
                    traceback.print_exc()
                    result[0] = 1

            thread = threading.Thread(target=run_server, daemon=False)
            thread.start()
            if self._wait_for_health(f"{self._panel_url}/api/health"):
                self._browser_open(self._panel_url)
            thread.join()
            return result[0]
        finally:
            self._guard.release()

    @staticmethod
    def _default_wait_for_health(url: str) -> bool:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with urlopen(url, timeout=1) as response:
                    if response.status == 200:
                        return True
            except OSError:
                time.sleep(0.25)
        return False


def main(argv: Sequence[str] | None = None) -> int:
    """Start the loopback server for development and packaged use."""
    del argv
    from fund_monitor.server import run_local_server

    return Launcher(
        guard=WindowsInstanceGuard(),
        server_runner=run_local_server,
        browser_open=webbrowser.open,
        panel_url="http://127.0.0.1:8420",
    ).run()
