"""Resolve a NetBox device into connection credentials via the credentials modules."""

from __future__ import annotations

import logging

from netbox_compare.modules import get_credentials_providers
from netbox_compare_core import Credentials, CredentialsError, DeviceIdentity

logger = logging.getLogger(__name__)


def device_identity(device) -> DeviceIdentity:
    primary_ip = device.primary_ip
    return DeviceIdentity(
        name=device.name or "",
        host=str(primary_ip.address.ip) if primary_ip else None,
        platform=device.platform.slug if device.platform else None,
    )


def resolve_credentials(device) -> Credentials | None:
    identity = device_identity(device)
    if not identity.name or not identity.host:
        return None
    for name, provider in get_credentials_providers():
        try:
            credentials = provider.resolve(identity)
        except CredentialsError as exc:
            logger.warning("Credentials module %r failed for %s: %s", name, identity.name, exc)
            continue
        if credentials is not None:
            return credentials
    return None
