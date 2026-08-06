from fund_monitor.secrets import SecretStore


class FakeKeyring:
    def __init__(self) -> None:
        self.values = {}

    def set_password(self, service, username, value) -> None:
        self.values[(service, username)] = value

    def get_password(self, service, username):
        return self.values.get((service, username))

    def delete_password(self, service, username) -> None:
        del self.values[(service, username)]


def test_secret_store_keeps_secret_outside_configuration() -> None:
    backend = FakeKeyring()
    store = SecretStore(backend=backend)

    store.set("channel:4", "super-secret-token")

    assert store.get("channel:4") == "super-secret-token"
    assert "super-secret-token" not in store.reference("channel:4")
    assert backend.values[("FundMonitor", "channel:4")] == "super-secret-token"
