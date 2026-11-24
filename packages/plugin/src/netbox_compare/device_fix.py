"""Whether a divergence can be fixed on the device. Pure: no Django, no NetBox.

A device fix is possible only if the field is a configuration attribute *and* a connection
module declares write support for that field on the device's platform. Every configured module
that declares the platform is considered, not only the one that ran the comparison.

For presence divergences (an object only on one side) the object's key field stands for the
object: creating or removing it on the device means writing that field.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from netbox_compare_core import FIELDS, FieldKind, PlatformCapabilities


@dataclass(frozen=True)
class DeviceFeasibility:
    possible: bool
    reason: str
    # Modules that declare the platform, and whether each can write the field there.
    modules: dict[str, bool] = field(default_factory=dict)

    @property
    def writers(self) -> list[str]:
        return [name for name, can in self.modules.items() if can]


def device_feasibility(
    field_path: str,
    platform: str | None,
    modules: Iterable[tuple[str, Mapping[str, PlatformCapabilities]]],
) -> DeviceFeasibility:
    """``modules``: ``(name, declared capabilities)`` for each configured connection module."""
    spec = FIELDS.get(field_path)
    if spec is None:
        return DeviceFeasibility(False, f"Unknown field {field_path!r}.")
    if spec.kind != FieldKind.CONFIG:
        return DeviceFeasibility(
            False,
            f"{spec.label} is a read-only fact: it can only be fixed in the documentation.",
        )
    if not platform:
        return DeviceFeasibility(False, "The device has no platform.")

    declared = {
        name: field_path in capabilities[platform].writable
        for name, capabilities in modules
        if platform in capabilities
    }
    if not declared:
        return DeviceFeasibility(False, f"No connection module declares platform {platform!r}.")
    writers = [name for name, can in declared.items() if can]
    if not writers:
        names = ", ".join(declared)
        return DeviceFeasibility(
            False,
            f"No connection module declares write support for {spec.label} on {platform!r} "
            f"(checked: {names}).",
            declared,
        )
    return DeviceFeasibility(
        True,
        f"Writable on {platform!r} by {', '.join(writers)}.",
        declared,
    )
