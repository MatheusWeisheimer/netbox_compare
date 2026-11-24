"""Per-driver corrections applied after the generic NAPALM getter conversion.

Some community drivers return values that are wrong for drift detection. A fixup may run extra
read-only commands, and must set a field to NOT_OBSERVED rather than leave a value it knows is
wrong.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from netbox_compare_core import NOT_OBSERVED, Snapshot, Value

logger = logging.getLogger(__name__)


def _cli(device: Any, command: str) -> str | None:
    try:
        return device.cli([command])[command]
    except Exception as exc:
        logger.warning("Command %r failed: %s: %s", command, type(exc).__name__, exc)
        return None


def parse_vrp_admin_state(output: str) -> dict[str, bool]:
    """``display interface brief`` -> {interface: administratively enabled}.

    The PHY column reads ``*down`` for an interface shut down by configuration.
    """
    states: dict[str, bool] = {}
    in_table = False
    for line in output.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        if not in_table:
            in_table = tokens[0] == "Interface" and "PHY" in tokens
            continue
        if len(tokens) >= 3:
            states.setdefault(tokens[0], not tokens[1].startswith("*"))
    return states


_MANUFACTURE_ROW = re.compile(r"^\s*\d+\s+-\s+(?P<serial>\S+)\s", re.M)


def parse_vrp_manufacture_info(output: str) -> Value:
    """``display device manufacture-info`` -> the chassis serial, if there is exactly one."""
    serials = _MANUFACTURE_ROW.findall(output)
    return serials[0] if len(serials) == 1 else NOT_OBSERVED


def huawei_vrp(device: Any, snapshot: Snapshot, wanted: set[str]) -> None:
    if snapshot.interfaces:
        for record in snapshot.interfaces.values():
            # The driver keeps the quotes VRP prints around descriptions with spaces.
            d = record.description
            if isinstance(d, str) and len(d) >= 2 and d[0] == d[-1] == '"':
                record.description = d[1:-1]

        if "interface.enabled" in wanted:
            # The driver derives is_enabled from the physical state, so a port without a
            # link reads as disabled. Take the administrative state from the brief instead.
            output = _cli(device, "display interface brief")
            admin = parse_vrp_admin_state(output) if output else {}
            for name, record in snapshot.interfaces.items():
                record.enabled = admin.get(name, NOT_OBSERVED)

    if "device.serial_number" in wanted and snapshot.device.serial_number is NOT_OBSERVED:
        # The driver reads `display esn`, which not every VRP release has.
        output = _cli(device, "display device manufacture-info")
        if output:
            snapshot.device.serial_number = parse_vrp_manufacture_info(output)


FIXUPS: dict[str, Callable[[Any, Snapshot, set[str]], None]] = {
    "huawei_vrp": huawei_vrp,
}
