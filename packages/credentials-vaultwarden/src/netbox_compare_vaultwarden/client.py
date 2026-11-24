"""Minimal HTTP client for the Bitwarden API as served by Vaultwarden."""

from __future__ import annotations

import uuid
from typing import Any

import requests

from netbox_compare_core import CredentialsError

# Bitwarden "SDK" device type; Vaultwarden accepts any known type.
DEVICE_TYPE = 21
DEVICE_NAME = "netbox-compare"


class VaultwardenClient:
    def __init__(
        self,
        url: str,
        client_id: str,
        client_secret: str,
        *,
        verify: bool | str = True,
        timeout: float = 10.0,
        device_id: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.verify = verify
        self.timeout = timeout
        # A stable identifier keeps Vaultwarden from registering a new device on every login.
        self.device_id = device_id or str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.url}#{client_id}"))
        self.session = session or requests.Session()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.session.request(
                method, f"{self.url}{path}", verify=self.verify, timeout=self.timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise CredentialsError(
                f"Vaultwarden unreachable at {self.url}: {type(exc).__name__}"
            ) from exc
        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                detail = body.get("error_description") or body.get("error") or ""
            except ValueError:
                pass
            raise CredentialsError(
                f"Vaultwarden {method} {path} returned HTTP {response.status_code}"
                + (f": {detail}" if detail else "")
            )
        try:
            return response.json()
        except ValueError as exc:
            raise CredentialsError(f"Vaultwarden {path} returned invalid JSON") from exc

    def login(self) -> dict[str, Any]:
        """Authenticate with the personal API key. Returns the token response, which also
        carries the KDF parameters and the encrypted user key."""
        return self._request(
            "POST",
            "/identity/connect/token",
            data={
                "grant_type": "client_credentials",
                "scope": "api",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "deviceType": DEVICE_TYPE,
                "deviceIdentifier": self.device_id,
                "deviceName": DEVICE_NAME,
            },
        )

    def prelogin(self, email: str) -> dict[str, Any]:
        return self._request("POST", "/identity/accounts/prelogin", json={"email": email})

    def sync(self, access_token: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/sync",
            params={"excludeDomains": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
