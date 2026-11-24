from unittest import mock

import pytest
import requests

from netbox_compare_core import CredentialsError
from netbox_compare_vaultwarden.client import VaultwardenClient


def response(status, body):
    r = mock.Mock(status_code=status)
    r.json.return_value = body
    return r


def test_login_posts_client_credentials():
    session = mock.Mock()
    session.request.return_value = response(200, {"access_token": "t"})
    client = VaultwardenClient("https://vw/", "user.1", "sec", verify="/ca.crt", session=session)
    assert client.login() == {"access_token": "t"}
    method, url = session.request.call_args.args
    kwargs = session.request.call_args.kwargs
    assert (method, url) == ("POST", "https://vw/identity/connect/token")
    assert kwargs["data"]["grant_type"] == "client_credentials"
    assert kwargs["verify"] == "/ca.crt"


def test_device_id_is_stable():
    a = VaultwardenClient("https://vw", "user.1", "s", session=mock.Mock())
    b = VaultwardenClient("https://vw/", "user.1", "s", session=mock.Mock())
    assert a.device_id == b.device_id


def test_http_error_hides_secret():
    session = mock.Mock()
    session.request.return_value = response(400, {"error": "invalid_client"})
    client = VaultwardenClient("https://vw", "user.1", "topsecret", session=session)
    with pytest.raises(CredentialsError, match="invalid_client") as exc:
        client.login()
    assert "topsecret" not in str(exc.value)


def test_connection_error():
    session = mock.Mock()
    session.request.side_effect = requests.ConnectionError("boom")
    client = VaultwardenClient("https://vw", "user.1", "s", session=session)
    with pytest.raises(CredentialsError, match="unreachable"):
        client.login()
