"""Comparison of two canonical snapshots. Pure: no Django, no NetBox.

Object level (interfaces, IP addresses): an object only on the device is *undocumented*, an
object only in NetBox is *missing on device*; both are divergences. For objects on both sides
each considered field is a match, a divergence, or not comparable (one side unavailable).

Only fields named in the policy are considered; everything else is dropped.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from netbox_compare_core import FIELDS, NOT_IN_SCHEMA, ObjectType, Snapshot, Unavailable
from netbox_compare_core.canonical import FieldSpec, Record, fields_of, key_field
from netbox_compare_core.notification import SEVERITIES


class Kind(StrEnum):
    FIELD = "field"
    UNDOCUMENTED = "undocumented"
    MISSING_ON_DEVICE = "missing_on_device"


class Reason(StrEnum):
    NOT_READABLE = "not_readable"  # the module declared it cannot read the field here
    NOT_OBSERVED = "not_observed"  # readable, but not produced in this run
    NOT_IN_SCHEMA = "not_in_schema"  # NetBox has nowhere to document it


@dataclass(frozen=True)
class Divergence:
    object_type: ObjectType
    key: str  # object key ("" for the device itself)
    kind: Kind
    field: str  # canonical path; for presence divergences, the object's key field
    severity: str
    documented: Any = None  # JSON-serialisable
    observed: Any = None


@dataclass(frozen=True)
class NotComparable:
    field: str
    reason: Reason
    keys: tuple[str, ...] = ()  # affected objects; empty: the device, or the whole collection


@dataclass
class Result:
    divergences: list[Divergence] = field(default_factory=list)
    not_comparable: list[NotComparable] = field(default_factory=list)
    matches: int = 0


def validate_policy(policy: Mapping[str, str]) -> dict[str, str]:
    unknown = set(policy) - set(FIELDS)
    if unknown:
        raise ValueError(f"Comparison policy names unknown fields: {sorted(unknown)}")
    bad = {f: s for f, s in policy.items() if s not in SEVERITIES}
    if bad:
        raise ValueError(f"Comparison policy has invalid severities {bad}; use {SEVERITIES}")
    return dict(policy)


def natural_key(value: str) -> list[Any]:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", value)]


def same_value(a: Any, b: Any) -> bool:
    # bool is an int subclass: keep True distinct from 1.
    return a == b and isinstance(a, bool) == isinstance(b, bool)


def _summary(record: Record, specs: list[FieldSpec]) -> dict[str, Any]:
    out = {}
    for spec in specs:
        value = getattr(record, spec.name)
        if not isinstance(value, Unavailable):
            out[spec.name] = value
    return out


def compare(
    documented: Snapshot,
    observed: Snapshot,
    policy: Mapping[str, str],
    readable: Collection[str] | None = None,
) -> Result:
    """Compare ``documented`` (NetBox) with ``observed`` (device).

    ``policy`` maps the considered canonical fields to a severity. ``readable`` is the set of
    fields the connection module declared readable for the platform, used to tell "cannot be
    read here" apart from "was not produced in this run".
    """
    result = Result()
    pending: dict[tuple[str, Reason], list[str]] = defaultdict(list)

    def unavailable_reason(spec_paths: list[str], doc: Any) -> Reason:
        if doc is NOT_IN_SCHEMA:
            return Reason.NOT_IN_SCHEMA
        if readable is not None and not any(p in readable for p in spec_paths):
            return Reason.NOT_READABLE
        return Reason.NOT_OBSERVED

    def compare_field(spec: FieldSpec, object_type: ObjectType, key: str, doc: Any, obs: Any):
        if isinstance(doc, Unavailable) or isinstance(obs, Unavailable):
            reason = (
                Reason.NOT_IN_SCHEMA
                if isinstance(doc, Unavailable)
                else unavailable_reason([spec.path], doc)
            )
            pending[(spec.path, reason)].append(key)
        elif same_value(doc, obs):
            result.matches += 1
        else:
            result.divergences.append(
                Divergence(object_type, key, Kind.FIELD, spec.path, policy[spec.path], doc, obs)
            )

    for spec in fields_of(ObjectType.DEVICE, policy):
        compare_field(
            spec,
            ObjectType.DEVICE,
            "",
            getattr(documented.device, spec.name),
            getattr(observed.device, spec.name),
        )

    for object_type in (ObjectType.INTERFACE, ObjectType.IP_ADDRESS):
        specs = fields_of(object_type, policy)
        if not specs:
            continue
        key_spec = key_field(object_type)
        doc_records = documented.collection(object_type)
        obs_records = observed.collection(object_type)
        if doc_records is None or obs_records is None:
            reason = unavailable_reason(
                [s.path for s in specs], NOT_IN_SCHEMA if doc_records is None else None
            )
            for spec in specs:
                pending.setdefault((spec.path, reason), [])
            continue

        presence = key_spec is not None and key_spec.path in policy
        attributes = [s for s in specs if not s.key]
        for key in sorted(doc_records.keys() | obs_records.keys(), key=natural_key):
            doc, obs = doc_records.get(key), obs_records.get(key)
            if doc is not None and obs is not None:
                if presence:
                    result.matches += 1
                for spec in attributes:
                    compare_field(
                        spec, object_type, key, getattr(doc, spec.name), getattr(obs, spec.name)
                    )
            elif not presence:
                continue
            elif doc is None:
                result.divergences.append(
                    Divergence(
                        object_type,
                        key,
                        Kind.UNDOCUMENTED,
                        key_spec.path,
                        policy[key_spec.path],
                        None,
                        _summary(obs, specs),
                    )
                )
            else:
                result.divergences.append(
                    Divergence(
                        object_type,
                        key,
                        Kind.MISSING_ON_DEVICE,
                        key_spec.path,
                        policy[key_spec.path],
                        _summary(doc, specs),
                        None,
                    )
                )

    order = {path: i for i, path in enumerate(FIELDS)}
    result.not_comparable = [
        NotComparable(path, reason, tuple(k for k in keys if k))
        for (path, reason), keys in sorted(pending.items(), key=lambda kv: order[kv[0][0]])
    ]
    return result
