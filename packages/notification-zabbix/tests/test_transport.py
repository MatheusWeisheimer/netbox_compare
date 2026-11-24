import json
import socket
import struct
import threading
from unittest import mock

import pytest
import requests

from netbox_compare_core import NotificationError
from netbox_compare_zabbix.items import ItemValue
from netbox_compare_zabbix.transport import ApiTransport, TrapperTransport

VALUES = [
    ItemValue("r1", "netbox.compare.severity", 3, 100),
    ItemValue("ghost", "netbox.compare.severity", 1, 100),
]


def response(status, body):
    r = mock.Mock(status_code=status)
    r.json.return_value = body
    return r


def test_api_push_sends_history_push_with_bearer_token():
    session = mock.Mock()
    session.post.return_value = response(
        200,
        {
            "result": {
                "response": "success",
                "data": [{"itemid": 1}, {"error": "No permissions ... does not exist."}],
            }
        },
    )
    api = ApiTransport("http://zbx/", "tok", verify="/ca.crt", session=session)
    result = api.push(VALUES)
    url = session.post.call_args.args[0]
    kwargs = session.post.call_args.kwargs
    assert url == "http://zbx/api_jsonrpc.php"
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    assert kwargs["verify"] == "/ca.crt"
    assert kwargs["json"]["method"] == "history.push"
    assert kwargs["json"]["params"][0] == {
        "host": "r1",
        "key": "netbox.compare.severity",
        "value": "3",
        "clock": 100,
    }
    assert (result.accepted, result.failed) == (1, 1)
    assert result.errors[0][0] == "ghost"


def test_api_error_hides_token():
    session = mock.Mock()
    session.post.return_value = response(
        200, {"error": {"code": -32602, "message": "Invalid params.", "data": "Not authorized."}}
    )
    with pytest.raises(NotificationError, match="Not authorized") as exc:
        ApiTransport("http://zbx/api_jsonrpc.php", "secret-token", session=session).push(VALUES)
    assert "secret-token" not in str(exc.value)


def test_api_unreachable():
    session = mock.Mock()
    session.post.side_effect = requests.ConnectionError("refused")
    with pytest.raises(NotificationError, match="unreachable"):
        ApiTransport("http://zbx", "t", session=session).push(VALUES)


class FakeTrapper:
    """A one-shot Zabbix trapper on localhost that records the request."""

    def __init__(self, reply):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.reply = reply
        self.request = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        conn, _ = self.sock.accept()
        with conn:
            header = conn.recv(13)
            (length,) = struct.unpack("<Q", header[5:13])
            data = b""
            while len(data) < length:
                data += conn.recv(length - len(data))
            self.request = json.loads(data)
            body = json.dumps(self.reply).encode()
            conn.sendall(b"ZBXD\x01" + struct.pack("<II", len(body), 0) + body)
        self.sock.close()


def test_trapper_push():
    server = FakeTrapper(
        {"response": "success", "info": "processed: 1; failed: 1; total: 2; seconds spent: 0.1"}
    )
    result = TrapperTransport("127.0.0.1", server.port, timeout=5).push(VALUES)
    server.thread.join(5)
    assert server.request["request"] == "sender data"
    assert server.request["data"][1] == {
        "host": "ghost",
        "key": "netbox.compare.severity",
        "value": "1",
        "clock": 100,
    }
    assert (result.accepted, result.failed) == (1, 1)


def test_trapper_unreachable():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    with pytest.raises(NotificationError, match="unreachable"):
        TrapperTransport("127.0.0.1", port, timeout=2).push(VALUES)
