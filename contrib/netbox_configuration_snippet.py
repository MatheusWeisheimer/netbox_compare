# --- netbox-compare (development) ---------------------------------------------------------
# Secrets are read from the repo's git-ignored .env, never written into this file.
import os as _os
from pathlib import Path as _Path

_NBC_ENV = _Path("/caminho/para/netbox_compare/.env")  # ajuste para o seu clone
if _NBC_ENV.is_file():
    for _line in _NBC_ENV.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _v = _v.strip()
            # Remove one matching pair of surrounding quotes; everything inside is literal.
            if len(_v) >= 2 and _v[0] == _v[-1] and _v[0] in "'\"":
                _v = _v[1:-1]
            _os.environ.setdefault(_k.strip(), _v)

PLUGINS_CONFIG = {
    "netbox_compare": {
        "credentials": [
            {
                "module": "vaultwarden",
                "config": {
                    "url": _os.environ.get("NBC_VW_URL", "https://localhost:8443"),
                    "client_id": _os.environ.get("NBC_VW_CLIENT_ID", ""),
                    "client_secret": _os.environ.get("NBC_VW_CLIENT_SECRET", ""),
                    "email": _os.environ.get("NBC_VW_EMAIL", ""),
                    "master_password": _os.environ.get("NBC_VW_MASTER_PASSWORD", ""),
                    "verify": _os.environ.get("NBC_VW_VERIFY", True),
                },
            },
        ],
        "connections": [
            {
                "module": "napalm",
                "config": {
                    "platforms": {
                        "huawei-vrp": {"driver": "huawei_vrp", "timeout": 60},
                    },
                },
            },
        ],
        "notifications": [
            {
                "module": "zabbix",
                "config": {
                    "url": _os.environ.get("NBC_ZBX_URL", "http://localhost:8081"),
                    "token": _os.environ.get("NBC_ZBX_TOKEN", ""),
                },
            },
        ],
    },
}
# --- end netbox-compare ---------------------------------------------------------------------
