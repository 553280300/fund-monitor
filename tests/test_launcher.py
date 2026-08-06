from fund_monitor.launcher import Launcher
from fund_monitor.launcher import WindowsInstanceGuard


class ExistingInstance:
    def acquire(self) -> bool: return False
    def release(self) -> None: raise AssertionError("Existing instance must not be released")


def test_second_launch_opens_existing_panel_without_starting_server() -> None:
    opened = []
    launcher = Launcher(
        guard=ExistingInstance(),
        server_runner=lambda: (_ for _ in ()).throw(AssertionError("must not start")),
        browser_open=opened.append,
        panel_url="http://127.0.0.1:8420",
    )

    assert launcher.run() == 0
    assert opened == ["http://127.0.0.1:8420"]


class NewInstance:
    def __init__(self) -> None: self.released = False
    def acquire(self) -> bool: return True
    def release(self) -> None: self.released = True


def test_first_launch_starts_server_then_opens_healthy_panel() -> None:
    guard, events = NewInstance(), []
    launcher = Launcher(
        guard=guard, server_runner=lambda: events.append("server") or 0,
        browser_open=lambda url: events.append(url), panel_url="http://127.0.0.1:8420",
        wait_for_health=lambda url: True,
    )

    assert launcher.run() == 0
    assert "server" in events
    assert "http://127.0.0.1:8420" in events
    assert guard.released is True


def test_windows_instance_guard_rejects_second_instance() -> None:
    name = "Local\\FundMonitorTestMutex"
    first, second = WindowsInstanceGuard(name), WindowsInstanceGuard(name)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        second.release()
        first.release()
