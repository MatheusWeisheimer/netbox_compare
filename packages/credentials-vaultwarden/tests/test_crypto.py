import pytest

from netbox_compare_vaultwarden import crypto
from netbox_compare_vaultwarden.crypto import CryptoError, SymmetricKey
from vaultfixtures import encrypt, new_key


def test_roundtrip():
    key = new_key()
    assert crypto.decrypt_symmetric(encrypt(b"hello", key), key) == b"hello"


def test_wrong_key_fails_mac():
    with pytest.raises(CryptoError, match="MAC"):
        crypto.decrypt_symmetric(encrypt(b"hello", new_key()), new_key())


def test_tampered_ciphertext_fails_mac():
    key = new_key()
    enc_type, rest = encrypt(b"hello world, longer", key).split(".", 1)
    iv, ct, mac = rest.split("|")
    tampered = f"{enc_type}.{iv}|{'A' + ct[1:] if ct[0] != 'A' else 'B' + ct[1:]}|{mac}"
    with pytest.raises(CryptoError):
        crypto.decrypt_symmetric(tampered, key)


@pytest.mark.parametrize("bad", ["", "nodot", "0.abc|def", "2.onlyone", "x.a|b|c"])
def test_malformed(bad):
    with pytest.raises(CryptoError):
        crypto.decrypt_symmetric(bad, new_key())


def test_kdf_email_normalised():
    a = crypto.derive_master_key("pw", " User@Example.COM ", crypto.KDF_PBKDF2, 1000)
    b = crypto.derive_master_key("pw", "user@example.com", crypto.KDF_PBKDF2, 1000)
    assert a == b and len(a) == 32


def test_argon2_requires_params():
    with pytest.raises(CryptoError):
        crypto.derive_master_key("pw", "e", crypto.KDF_ARGON2ID, 3)


def test_stretch_matches_hkdf_expand_single_block():
    # HKDF-Expand with L == HashLen is T(1) = HMAC(PRK, info || 0x01)
    import hashlib
    import hmac

    mk = bytes(range(32))
    s = crypto.stretch_master_key(mk)
    assert s.enc == hmac.new(mk, b"enc\x01", hashlib.sha256).digest()
    assert s.mac == hmac.new(mk, b"mac\x01", hashlib.sha256).digest()


def test_key_repr_redacted():
    key = SymmetricKey.from_bytes(bytes(64))
    assert "redacted" in repr(key)
