import pytest

from netbox_compare_core import AmbiguousCredentials, Credentials, CredentialsError, DeviceIdentity
from netbox_compare_vaultwarden import crypto
from netbox_compare_vaultwarden.provider import VaultwardenProvider
from vaultfixtures import EMAIL, MASTER_PASSWORD, FakeClient, FakeVault

CONFIG = {
    "url": "https://vw.invalid",
    "client_id": "user.x",
    "client_secret": "s",
    "email": EMAIL,
    "master_password": MASTER_PASSWORD,
}


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make(vault, **extra):
    clock = Clock()
    client = FakeClient(vault)
    provider = VaultwardenProvider({**CONFIG, **extra}, client=client, clock=clock)
    return provider, client, clock


def dev(name="rt-01", host="192.0.2.1"):
    return DeviceIdentity(name=name, host=host, platform="vrp")


@pytest.mark.parametrize("kdf", [crypto.KDF_PBKDF2, crypto.KDF_ARGON2ID])
def test_resolves_personal_item(kdf):
    vault = FakeVault(kdf)
    vault.add_login("rt-01", "admin", "pw1")
    provider, _, _ = make(vault)
    assert provider.resolve(dev()) == Credentials("192.0.2.1", "admin", "pw1")


def test_resolves_org_item_with_item_key():
    vault = FakeVault()
    vault.add_org("org-1")
    vault.add_login("rt-01", "netops", "pw2", org_id="org-1", item_key=True)
    provider, _, _ = make(vault)
    assert provider.resolve(dev()) == Credentials("192.0.2.1", "netops", "pw2")


def test_no_match_and_no_host():
    vault = FakeVault()
    vault.add_login("rt-01", "admin", "pw")
    provider, client, _ = make(vault)
    assert provider.resolve(dev("other")) is None
    assert provider.resolve(dev(host=None)) is None


def test_ignores_deleted_and_non_login():
    vault = FakeVault()
    vault.add_login("rt-01", "a", "b", deleted=True)
    vault.add_login("rt-01", "a", "b", cipher_type=2)
    provider, _, _ = make(vault)
    assert provider.resolve(dev()) is None


def test_missing_password_is_none():
    vault = FakeVault()
    vault.add_login("rt-01", "admin", None)
    provider, _, _ = make(vault)
    assert provider.resolve(dev()) is None


def test_ambiguous():
    vault = FakeVault()
    vault.add_login("rt-01", "a", "1")
    vault.add_login("rt-01", "b", "2")
    provider, _, _ = make(vault)
    with pytest.raises(AmbiguousCredentials):
        provider.resolve(dev())


def test_wrong_master_password():
    vault = FakeVault()
    vault.add_login("rt-01", "a", "1")
    provider, _, _ = make(vault, master_password="wrong")
    with pytest.raises(CredentialsError, match="unlock") as exc:
        provider.resolve(dev())
    assert "wrong" not in str(exc.value).replace("wrong master password", "")


def test_missing_config():
    with pytest.raises(CredentialsError, match="master_password"):
        VaultwardenProvider({**CONFIG, "master_password": ""})


def test_cache_ttl():
    vault = FakeVault()
    vault.add_login("rt-01", "a", "1")
    provider, client, clock = make(vault, cache_ttl=60)
    provider.resolve(dev())
    clock.t = 59
    provider.resolve(dev())
    assert client.logins == 1
    clock.t = 61
    provider.resolve(dev())
    assert client.logins == 2


def test_failure_backoff():
    vault = FakeVault()
    vault.add_login("rt-01", "a", "1")
    provider, client, clock = make(vault, failure_backoff=30)
    client.fail = CredentialsError("down")
    for _ in range(3):
        with pytest.raises(CredentialsError):
            provider.resolve(dev())
    assert client.logins == 1
    client.fail = None
    clock.t = 31
    assert provider.resolve(dev()) is not None
