import pytest

from netbox_compare_core import Credentials, CredentialsProvider, DeviceIdentity


def test_password_not_in_repr():
    creds = Credentials("10.0.0.1", "admin", "s3cr3t-value")
    assert "s3cr3t-value" not in repr(creds)
    assert "admin" in repr(creds)


def test_provider_is_abstract():
    with pytest.raises(TypeError):
        CredentialsProvider({})  # type: ignore[abstract]


def test_provider_subclass():
    class Static(CredentialsProvider):
        def resolve(self, device):
            return Credentials(device.host, self.config["u"], self.config["p"])

    creds = Static({"u": "a", "p": "b"}).resolve(DeviceIdentity("r1", "192.0.2.1"))
    assert creds == Credentials("192.0.2.1", "a", "b")
