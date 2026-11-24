"""Bitwarden client-side cryptography (the subset needed to read Login items).

Key hierarchy:
    master password + email --KDF--> master key --HKDF-expand--> stretched key (enc, mac)
    stretched key decrypts the user key (64 bytes: enc || mac)
    user key decrypts the RSA private key; the private key decrypts organization keys
    user/org key decrypts cipher fields (or a per-cipher key, if present)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

KDF_PBKDF2 = 0
KDF_ARGON2ID = 1

ENC_AES_CBC_HMAC = 2
ENC_RSA_OAEP_SHA1 = 4


class CryptoError(Exception):
    """Decryption failed. Never carries key or plaintext material."""


@dataclass(frozen=True)
class SymmetricKey:
    enc: bytes
    mac: bytes

    def __repr__(self) -> str:
        return "SymmetricKey(<redacted>)"

    @classmethod
    def from_bytes(cls, raw: bytes) -> SymmetricKey:
        if len(raw) != 64:
            raise CryptoError(f"expected a 64-byte symmetric key, got {len(raw)} bytes")
        return cls(raw[:32], raw[32:])


def derive_master_key(
    password: str,
    email: str,
    kdf: int,
    iterations: int,
    memory_mib: int | None = None,
    parallelism: int | None = None,
) -> bytes:
    email = email.strip().lower()
    if kdf == KDF_PBKDF2:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), email.encode(), iterations, 32)
    if kdf == KDF_ARGON2ID:
        if not memory_mib or not parallelism:
            raise CryptoError("Argon2id KDF requires memory and parallelism parameters")
        return hash_secret_raw(
            secret=password.encode(),
            salt=hashlib.sha256(email.encode()).digest(),
            time_cost=iterations,
            memory_cost=memory_mib * 1024,
            parallelism=parallelism,
            hash_len=32,
            type=Type.ID,
        )
    raise CryptoError(f"unsupported KDF type {kdf}")


def _hkdf_expand(key: bytes, info: bytes) -> bytes:
    return HKDFExpand(algorithm=hashes.SHA256(), length=32, info=info).derive(key)


def stretch_master_key(master_key: bytes) -> SymmetricKey:
    return SymmetricKey(_hkdf_expand(master_key, b"enc"), _hkdf_expand(master_key, b"mac"))


def _b64(data: str) -> bytes:
    try:
        return base64.b64decode(data, validate=True)
    except ValueError as exc:
        raise CryptoError("malformed base64 in encrypted string") from exc


def _parse(enc_string: str) -> tuple[int, list[str]]:
    head, sep, body = enc_string.partition(".")
    if not sep or not head.isdigit():
        raise CryptoError("malformed encrypted string")
    return int(head), body.split("|")


def decrypt_symmetric(enc_string: str, key: SymmetricKey) -> bytes:
    enc_type, parts = _parse(enc_string)
    if enc_type != ENC_AES_CBC_HMAC or len(parts) != 3:
        raise CryptoError(f"unsupported symmetric encryption type {enc_type}")
    iv, ct, mac = (_b64(p) for p in parts)
    expected = hmac.new(key.mac, iv + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, mac):
        raise CryptoError("MAC verification failed (wrong key or tampered data)")
    decryptor = Cipher(algorithms.AES(key.enc), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    try:
        return unpadder.update(padded) + unpadder.finalize()
    except ValueError as exc:
        raise CryptoError("invalid padding") from exc


def decrypt_rsa(enc_string: str, private_key_der: bytes) -> bytes:
    enc_type, parts = _parse(enc_string)
    if enc_type != ENC_RSA_OAEP_SHA1 or len(parts) != 1:
        raise CryptoError(f"unsupported asymmetric encryption type {enc_type}")
    private_key = serialization.load_der_private_key(private_key_der, password=None)
    try:
        return private_key.decrypt(  # type: ignore[union-attr]
            _b64(parts[0]),
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA1()),  # noqa: S303 - Bitwarden format
                algorithm=hashes.SHA1(),  # noqa: S303
                label=None,
            ),
        )
    except ValueError as exc:
        raise CryptoError("RSA decryption failed") from exc
