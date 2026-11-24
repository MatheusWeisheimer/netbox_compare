#!/usr/bin/env bash
# Install the netbox-compare packages (editable) into the local NetBox venv and point
# NetBox's configuration at them. Run with: sudo scripts/install-netbox-dev.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
NETBOX=/opt/netbox
PIP="$NETBOX/venv/bin/pip"
CONF="$NETBOX/netbox/netbox/configuration.py"

# Packages from earlier attempts; they also provide a `netbox_compare` module.
"$PIP" uninstall -y netbox-compare-plugin netbox-compare-access || true

"$PIP" install \
    -e "$REPO/packages/core" \
    -e "$REPO/packages/credentials-vaultwarden" \
    -e "$REPO/packages/connection-napalm[vrp]" \
    -e "$REPO/packages/notification-zabbix" \
    -e "$REPO/packages/plugin"

# Replace the PLUGINS_CONFIG block (from "PLUGINS_CONFIG = {" to the next "}" at column 0).
cp "$CONF" "$CONF.bak.$(date +%Y%m%d%H%M%S)"
"$NETBOX/venv/bin/python" - "$CONF" "$REPO/contrib/netbox_configuration_snippet.py" <<'PY'
import re, sys
conf_path, snippet_path = sys.argv[1], sys.argv[2]
conf = open(conf_path).read()
snippet = open(snippet_path).read().rstrip() + "\n"
marker = re.compile(r"# --- netbox-compare.*?# --- end netbox-compare -+\n", re.S)
block = re.compile(r"^PLUGINS_CONFIG = \{.*?^\}\n", re.S | re.M)
if marker.search(conf):
    conf = marker.sub(lambda _: snippet, conf, count=1)
elif block.search(conf):
    conf = block.sub(lambda _: snippet, conf, count=1)
else:
    conf += "\n" + snippet
open(conf_path, "w").write(conf)
PY

grep -q '"netbox_compare"' "$CONF" || echo 'WARNING: add "netbox_compare" to PLUGINS in' "$CONF"
sudo -u "${SUDO_USER:-root}" "$NETBOX/venv/bin/python" "$NETBOX/netbox/manage.py" migrate netbox_compare
echo "Done. Fill in $REPO/.env (see .env.example; single-quote values with special characters), then restart NetBox and its rqworker."
