"""Credentials module: resolve a device to the Vaultwarden Login item named after it."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Mapping
from typing import Any

from netbox_compare_core import (
    AmbiguousCredentials,
    Credentials,
    CredentialsError,
    CredentialsProvider,
    DeviceIdentity,
)
from netbox_compare_vaultwarden.client import VaultwardenClient
from netbox_compare_vaultwarden.crypto import CryptoError
from netbox_compare_vaultwarden.vault import (
    LoginItem,
    _get,
    decrypt_logins,
    kdf_params,
    unlock_user_key,
)

logger = logging.getLogger(__name__)

REQUIRED_KEYS = ("url", "client_id", "client_secret", "email", "master_password")


class VaultwardenProvider(CredentialsProvider):
    """Configuration keys:

    url, client_id, client_secret, email, master_password  (required)
    verify          TLS verification: bool or path to a CA bundle (default True)
    timeout         HTTP timeout in seconds (default 10)
    cache_ttl       seconds a decrypted vault snapshot is reused (default 300)
    failure_backoff seconds to wait before retrying after a failure (default 30)
    device_id       Bitwarden device identifier (default: derived from url + client_id)

    Decrypted secrets are held only in this process's memory.
    """

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        client: VaultwardenClient | None = None,
        clock: Any = time.monotonic,
    ) -> None:
        super().__init__(config)
        missing = [k for k in REQUIRED_KEYS if not config.get(k)]
        if missing:
            raise CredentialsError(f"Vaultwarden module is missing config keys: {missing}")
        self.client = client or VaultwardenClient(
            config["url"],
            config["client_id"],
            config["client_secret"],
            verify=config.get("verify", True),
            timeout=float(config.get("timeout", 10)),
            device_id=config.get("device_id"),
        )
        self.cache_ttl = float(config.get("cache_ttl", 300))
        self.failure_backoff = float(config.get("failure_backoff", 30))
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[str, list[LoginItem]] | None = None
        self._loaded_at = 0.0
        self._failure: CredentialsError | None = None
        self._failed_at = 0.0

    def _load(self) -> dict[str, list[LoginItem]]:
        token = self.client.login()
        access_token = _get(token, "access_token")
        if not access_token:
            raise CredentialsError("Vaultwarden login response has no access token")
        sync = self.client.sync(access_token)
        profile = _get(sync, "profile") or {}
        encrypted_user_key = _get(profile, "key") or _get(token, "key")
        if not encrypted_user_key:
            raise CredentialsError("Vaultwarden returned no encrypted user key")
        kdf = kdf_params(token) or kdf_params(self.client.prelogin(self.config["email"]))
        if kdf is None:
            raise CredentialsError("Vaultwarden returned no KDF parameters")
        try:
            user_key = unlock_user_key(
                encrypted_user_key, self.config["master_password"], self.config["email"], kdf
            )
            logins = decrypt_logins(sync, user_key)
        except CryptoError as exc:
            raise CredentialsError(f"Vaultwarden decryption failed: {exc}") from exc
        by_name: dict[str, list[LoginItem]] = {}
        for item in logins:
            by_name.setdefault(item.name, []).append(item)
        logger.info("Loaded %d login items from Vaultwarden", len(logins))
        return by_name

    def _snapshot(self) -> dict[str, list[LoginItem]]:
        with self._lock:
            now = self._clock()
            if self._items is not None and now - self._loaded_at < self.cache_ttl:
                return self._items
            if self._failure is not None and now - self._failed_at < self.failure_backoff:
                raise self._failure
            try:
                self._items = self._load()
            except CredentialsError as exc:
                self._failure, self._failed_at = exc, now
                raise
            self._loaded_at, self._failure = now, None
            return self._items

    def invalidate(self) -> None:
        with self._lock:
            self._items = None
            self._failure = None

    def resolve(self, device: DeviceIdentity) -> Credentials | None:
        if not device.host:
            return None
        matches = self._snapshot().get(device.name, [])
        if not matches:
            return None
        if len(matches) > 1:
            raise AmbiguousCredentials(
                f"{len(matches)} Vaultwarden items are named {device.name!r}: "
                + ", ".join(m.id for m in matches)
            )
        item = matches[0]
        if not item.username or not item.password:
            logger.warning("Vaultwarden item %s has no username or password", item.id)
            return None
        return Credentials(device.host, item.username, item.password)
