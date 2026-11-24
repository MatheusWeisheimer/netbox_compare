"""Turn a Bitwarden sync payload into decrypted Login items."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from netbox_compare_vaultwarden import crypto
from netbox_compare_vaultwarden.crypto import CryptoError, SymmetricKey

logger = logging.getLogger(__name__)

CIPHER_TYPE_LOGIN = 1


def _get(obj: dict[str, Any] | None, name: str, default: Any = None) -> Any:
    """Read a field that may be camelCase (current API) or PascalCase (older servers)."""
    if not obj:
        return default
    if name in obj:
        return obj[name]
    return obj.get(name[0].upper() + name[1:], default)


@dataclass(frozen=True)
class LoginItem:
    id: str
    name: str
    username: str | None
    password: str | None = field(repr=False)


def kdf_params(source: dict[str, Any]) -> dict[str, Any] | None:
    """Extract KDF parameters from a token or prelogin response, if present."""
    kdf = _get(source, "kdf")
    iterations = _get(source, "kdfIterations")
    if kdf is None or iterations is None:
        return None
    return {
        "kdf": int(kdf),
        "iterations": int(iterations),
        "memory_mib": _get(source, "kdfMemory"),
        "parallelism": _get(source, "kdfParallelism"),
    }


def unlock_user_key(
    encrypted_user_key: str, master_password: str, email: str, kdf: dict[str, Any]
) -> SymmetricKey:
    master_key = crypto.derive_master_key(master_password, email, **kdf)
    stretched = crypto.stretch_master_key(master_key)
    try:
        return SymmetricKey.from_bytes(crypto.decrypt_symmetric(encrypted_user_key, stretched))
    except CryptoError as exc:
        raise CryptoError("could not unlock the vault (wrong master password or email?)") from exc


def organization_keys(profile: dict[str, Any], user_key: SymmetricKey) -> dict[str, SymmetricKey]:
    orgs = _get(profile, "organizations") or []
    encrypted_private_key = _get(profile, "privateKey")
    if not orgs or not encrypted_private_key:
        return {}
    private_key_der = crypto.decrypt_symmetric(encrypted_private_key, user_key)
    keys: dict[str, SymmetricKey] = {}
    for org in orgs:
        org_id, org_key = _get(org, "id"), _get(org, "key")
        if not org_id or not org_key:
            continue
        try:
            keys[org_id] = SymmetricKey.from_bytes(crypto.decrypt_rsa(org_key, private_key_der))
        except CryptoError:
            logger.warning("Could not decrypt key of organization %s; skipping it", org_id)
    return keys


def _decrypt_str(value: str | None, key: SymmetricKey) -> str | None:
    if not value:
        return None
    return crypto.decrypt_symmetric(value, key).decode("utf-8")


def decrypt_logins(sync: dict[str, Any], user_key: SymmetricKey) -> list[LoginItem]:
    org_keys = organization_keys(_get(sync, "profile") or {}, user_key)
    items: list[LoginItem] = []
    for cipher in _get(sync, "ciphers") or []:
        if _get(cipher, "type") != CIPHER_TYPE_LOGIN or _get(cipher, "deletedDate"):
            continue
        cipher_id = _get(cipher, "id", "?")
        org_id = _get(cipher, "organizationId")
        key = org_keys.get(org_id) if org_id else user_key
        if key is None:
            logger.warning("No key for organization of item %s; skipping it", cipher_id)
            continue
        try:
            item_key = _get(cipher, "key")
            if item_key:
                key = SymmetricKey.from_bytes(crypto.decrypt_symmetric(item_key, key))
            login = _get(cipher, "login") or {}
            items.append(
                LoginItem(
                    id=cipher_id,
                    name=_decrypt_str(_get(cipher, "name"), key) or "",
                    username=_decrypt_str(_get(login, "username"), key),
                    password=_decrypt_str(_get(login, "password"), key),
                )
            )
        except (CryptoError, UnicodeDecodeError):
            logger.warning("Could not decrypt item %s; skipping it", cipher_id)
    return items
