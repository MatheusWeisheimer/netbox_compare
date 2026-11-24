"""Two ways to push item values into Zabbix trapper items.

* :class:`ApiTransport`: the JSON-RPC API's ``history.push`` (Zabbix 7.0+), over HTTP(S) with
  an API token. Reports which values were rejected.
* :class:`TrapperTransport`: the Zabbix sender protocol, over TCP to a server or proxy (port
  10051). Only reports how many values were rejected.
"""

from __future__ import annotations

import json
import re
import socket
import struct
from collections.abc import Sequence
from dataclasses import dataclass, field

import requests

from netbox_compare_core import NotificationError
from netbox_compare_zabbix.items import ItemValue


@dataclass
class PushResult:
    accepted: int = 0
    failed: int = 0
    # (host, key, error) per rejected value, when the transport knows which ones.
    errors: list[tuple[str, str, str]] = field(default_factory=list)


class ApiTransport:
    def __init__(
        self,
        url: str,
        token: str,
        verify: bool | str = True,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        url = url.rstrip("/")
        self.url = url if url.endswith("api_jsonrpc.php") else f"{url}/api_jsonrpc.php"
        self.token = token
        self.verify = verify
        self.timeout = timeout
        self.session = session or requests.Session()

    def push(self, values: Sequence[ItemValue]) -> PushResult:
        params = [
            {"host": v.host, "key": v.key, "value": str(v.value), "clock": v.clock} for v in values
        ]
        body = {"jsonrpc": "2.0", "method": "history.push", "params": params, "id": 1}
        try:
            response = self.session.post(
                self.url,
                json=body,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json-rpc",
                },
                verify=self.verify,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise NotificationError(f"Zabbix API unreachable at {self.url}: {exc}") from None
        if response.status_code != 200:
            raise NotificationError(f"Zabbix API returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise NotificationError("Zabbix API returned a non-JSON response") from None
        if "error" in payload:
            err = payload["error"]
            raise NotificationError(
                f"Zabbix API error: {err.get('message', '')} {err.get('data', '')}".strip()
            )
        data = (payload.get("result") or {}).get("data") or []
        if len(data) != len(values):
            raise NotificationError("Zabbix API returned an unexpected history.push result")
        result = PushResult()
        for value, item in zip(values, data, strict=True):
            if "error" in item:
                result.failed += 1
                result.errors.append((value.host, value.key, item["error"]))
            else:
                result.accepted += 1
        return result


_HEADER = b"ZBXD\x01"
_INFO = re.compile(r"processed:\s*(\d+);\s*failed:\s*(\d+)")


class TrapperTransport:
    def __init__(self, server: str, port: int = 10051, timeout: float = 10.0) -> None:
        self.server = server
        self.port = int(port)
        self.timeout = timeout

    def push(self, values: Sequence[ItemValue]) -> PushResult:
        request = {
            "request": "sender data",
            "data": [
                {"host": v.host, "key": v.key, "value": str(v.value), "clock": v.clock}
                for v in values
            ],
        }
        try:
            reply = self._exchange(json.dumps(request).encode())
        except OSError as exc:
            raise NotificationError(
                f"Zabbix trapper unreachable at {self.server}:{self.port}: {exc}"
            ) from None
        if reply.get("response") != "success":
            raise NotificationError(f"Zabbix trapper refused the data: {reply}")
        match = _INFO.search(reply.get("info", ""))
        if not match:
            raise NotificationError(f"Unexpected Zabbix trapper reply: {reply}")
        return PushResult(accepted=int(match[1]), failed=int(match[2]))

    def _exchange(self, data: bytes) -> dict:
        with socket.create_connection((self.server, self.port), timeout=self.timeout) as sock:
            sock.sendall(_HEADER + struct.pack("<Q", len(data)) + data)
            raw = b""
            while chunk := sock.recv(65536):
                raw += chunk
        if not raw.startswith(b"ZBXD") or len(raw) < 13:
            raise OSError("not a Zabbix reply")
        (length,) = struct.unpack("<I", raw[5:9])
        try:
            return json.loads(raw[13 : 13 + length])
        except ValueError:
            raise OSError("malformed Zabbix reply") from None
