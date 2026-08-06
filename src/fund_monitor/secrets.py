"""System credential-store wrapper for notification secrets."""

from __future__ import annotations

from typing import Protocol

import keyring


class KeyringBackend(Protocol):
    def set_password(self, service_name: str, username: str, password: str) -> None: ...
    def get_password(self, service_name: str, username: str) -> str | None: ...
    def delete_password(self, service_name: str, username: str) -> None: ...


class SecretStore:
    def __init__(self, *, service_name: str = "FundMonitor", backend: KeyringBackend | None = None) -> None:
        self._service_name = service_name
        self._backend = backend or keyring

    def set(self, reference: str, secret: str) -> None:
        if not reference or not secret:
            raise ValueError("secret reference and value must not be empty")
        self._backend.set_password(self._service_name, reference, secret)

    def get(self, reference: str) -> str | None:
        return self._backend.get_password(self._service_name, reference)

    def delete(self, reference: str) -> None:
        try:
            self._backend.delete_password(self._service_name, reference)
        except keyring.errors.PasswordDeleteError:
            return

    def reference(self, reference: str) -> str:
        return f"credential-store:{self._service_name}:{reference}"
