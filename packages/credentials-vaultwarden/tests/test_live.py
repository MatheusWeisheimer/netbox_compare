"""Live test against a real Vaultwarden. Run with: uv run pytest -m live

Needs NBC_VW_URL, NBC_VW_CLIENT_ID, NBC_VW_CLIENT_SECRET, NBC_VW_EMAIL, NBC_VW_MASTER_PASSWORD,
optionally NBC_VW_VERIFY (CA path), and NBC_VW_TEST_ITEM: the name of a Login item that exists.
"""

import os

import pytest

from netbox_compare_core import DeviceIdentity
from netbox_compare_vaultwarden.provider import VaultwardenProvider

pytestmark = pytest.mark.live

ENV = {
    "url": "NBC_VW_URL",
    "client_id": "NBC_VW_CLIENT_ID",
    "client_secret": "NBC_VW_CLIENT_SECRET",
    "email": "NBC_VW_EMAIL",
    "master_password": "NBC_VW_MASTER_PASSWORD",
}


def test_resolve_live():
    missing = [v for v in [*ENV.values(), "NBC_VW_TEST_ITEM"] if not os.environ.get(v)]
    if missing:
        pytest.skip(f"missing env vars: {missing}")
    config = {k: os.environ[v] for k, v in ENV.items()}
    config["verify"] = os.environ.get("NBC_VW_VERIFY", True)
    creds = VaultwardenProvider(config).resolve(
        DeviceIdentity(os.environ["NBC_VW_TEST_ITEM"], "192.0.2.1")
    )
    assert creds is not None and creds.username and creds.password
