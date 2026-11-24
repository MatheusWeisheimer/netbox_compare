"""Build encrypted Bitwarden payloads for tests, using the same primitives in reverse."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any

from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from netbox_compare_vaultwarden import crypto
from netbox_compare_vaultwarden.crypto import SymmetricKey

EMAIL = "Admin@Example.com"
MASTER_PASSWORD = "correct horse battery staple"
ITERATIONS = 1000


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def encrypt(plaintext: bytes, key: SymmetricKey) -> str:
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    enc = Cipher(algorithms.AES(key.enc), modes.CBC(iv)).encryptor()
    ct = enc.update(padded) + enc.finalize()
    mac = hmac.new(key.mac, iv + ct, hashlib.sha256).digest()
    return f"2.{b64(iv)}|{b64(ct)}|{b64(mac)}"


def new_key() -> SymmetricKey:
    return SymmetricKey.from_bytes(os.urandom(64))


def key_bytes(key: SymmetricKey) -> bytes:
    return key.enc + key.mac


class FakeVault:
    """Holds keys and produces token + sync payloads like Vaultwarden does (camelCase)."""

    def __init__(self, kdf: int = crypto.KDF_PBKDF2) -> None:
        self.kdf = kdf
        self.kdf_args: dict[str, Any] = (
            {"iterations": ITERATIONS}
            if kdf == crypto.KDF_PBKDF2
            else {"iterations": 2, "memory_mib": 8, "parallelism": 1}
        )
        master = crypto.derive_master_key(MASTER_PASSWORD, EMAIL, kdf, **self.kdf_args)
        self.stretched = crypto.stretch_master_key(master)
        self.user_key = new_key()
        self.rsa = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.orgs: dict[str, SymmetricKey] = {}
        self.ciphers: list[dict[str, Any]] = []

    def add_org(self, org_id: str) -> None:
        self.orgs[org_id] = new_key()

    def add_login(
        self,
        name: str,
        username: str | None,
        password: str | None,
        *,
        org_id: str | None = None,
        item_key: bool = False,
        deleted: bool = False,
        cipher_type: int = 1,
    ) -> str:
        key = self.orgs[org_id] if org_id else self.user_key
        cipher: dict[str, Any] = {"id": f"id-{len(self.ciphers)}", "type": cipher_type}
        if item_key:
            per_item = new_key()
            cipher["key"] = encrypt(key_bytes(per_item), key)
            key = per_item
        cipher["name"] = encrypt(name.encode(), key)
        cipher["login"] = {
            "username": encrypt(username.encode(), key) if username else None,
            "password": encrypt(password.encode(), key) if password else None,
        }
        cipher["organizationId"] = org_id
        cipher["deletedDate"] = "2026-01-01T00:00:00Z" if deleted else None
        self.ciphers.append(cipher)
        return cipher["id"]

    def token(self) -> dict[str, Any]:
        token = {
            "access_token": "tok",
            "Kdf": self.kdf,
            "KdfIterations": self.kdf_args["iterations"],
            "KdfMemory": self.kdf_args.get("memory_mib"),
            "KdfParallelism": self.kdf_args.get("parallelism"),
        }
        return token

    def sync(self) -> dict[str, Any]:
        der = self.rsa.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        oaep = asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA1()),  # noqa: S303
            algorithm=hashes.SHA1(),  # noqa: S303
            label=None,
        )
        orgs = [
            {"id": oid, "key": "4." + b64(self.rsa.public_key().encrypt(key_bytes(k), oaep))}
            for oid, k in self.orgs.items()
        ]
        return {
            "profile": {
                "key": encrypt(key_bytes(self.user_key), self.stretched),
                "privateKey": encrypt(der, self.user_key),
                "organizations": orgs,
            },
            "ciphers": self.ciphers,
        }


class FakeClient:
    def __init__(self, vault: FakeVault) -> None:
        self.vault = vault
        self.logins = 0
        self.fail: Exception | None = None

    def login(self):
        self.logins += 1
        if self.fail:
            raise self.fail
        return self.vault.token()

    def sync(self, access_token):
        return self.vault.sync()

    def prelogin(self, email):
        return self.vault.token()
