# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Implemented:
- Credentials module (Vaultwarden) and the connection module (NAPALM, tested against a Huawei VRP switch).
- Canonical model, connection contract and the diff, following the comparison semantics below.
- Manual comparison of one device: the device page button queues a background job, and the report (documented vs. observed value per divergence, plus not-comparable fields) is stored in NetBox. It is shown at `/plugins/compare/comparisons/<id>/`, in a "Comparisons" device tab, and through a read-only REST API.
- Comparison policies: stored in NetBox (`ComparisonPolicy`: per canonical field, whether it is compared and its severity, set separately; at most one default), editable in the UI and REST API. Each comparison links its policy and keeps a snapshot of its fields (`policy_fields`). The device button runs the default policy or one picked from its dropdown.
- Resolution: on the report the administrator picks, per divergence, documentation / device / no fix. Apply writes documentation fixes to NetBox (`documentation_fix.py`); for device fixes it only reports whether a connection module declares write support (`device_fix.py`). Outcomes are in the comparison's "Resolution" tab.

Not implemented yet: device writes (no write method in the connection contract), scheduled jobs, notification modules, open commands, the modules page, the MCP adapter.

Statements marked **(spec)** come from the project's design text (section 5, "Definições do projeto", in Portuguese) and are requirements.

## Repo layout and commands

uv workspace monorepo; each package is separately installable (hatchling, `src/` layout):

- `packages/core` → `netbox_compare_core`: canonical model and module contracts. No Django/NetBox dependency.
- `packages/credentials-vaultwarden` → `netbox_compare_vaultwarden`: credentials module. Matches the Login item named after the device; the host is the device's primary IP. Decrypted secrets stay in process memory only.
- `packages/connection-napalm` → `netbox_compare_napalm`: connection module. Maps NetBox platform slugs to NAPALM drivers; `fixups.py` corrects per-driver output (e.g. huawei_vrp administrative state).
- `packages/plugin` → `netbox_compare`: the NetBox plugin. **Not** a workspace member, because it needs NetBox and is only installed into NetBox's venv.

Commands:
- `uv sync`: dev env for core + modules
- `uv run pytest`: unit tests, including the plugin's Django-free modules (`diff.py`; `packages/plugin/tests/conftest.py` stubs NetBox)
- `set -a; . ./.env; set +a; uv run pytest -m live`: tests against the local Vaultwarden
- `uv run ruff check . && uv run ruff format --check .`
- `sudo scripts/install-netbox-dev.sh`: editable-install all packages into `/opt/netbox/venv`, run the plugin's migrations, and rewrite `PLUGINS_CONFIG` from `contrib/netbox_configuration_snippet.py`. Secrets come from the git-ignored `.env` (see `.env.example`).
- Local dev environment (outside the repo): NetBox 4.5 at `/opt/netbox` on :8000 (runserver + rqworker, run by the user; restart both after changing entry points or job code), Vaultwarden at `https://localhost:8443` (CA: `~/caddy-root.crt`). Commands that need `sudo` must be run by the user.

Plugin config (`PLUGINS_CONFIG["netbox_compare"]`):
- `credentials`, `connections`: ordered lists of `{"module": <entry point name>, "config": {...}}`. The first credentials module that resolves the device wins; a device uses the first connection module that declares its platform slug.
- `os_version_custom_field`: Device custom field holding the OS version (NetBox has no native field).

## What the project is

netbox-compare detects **configuration drift**. It compares the *documented* state of network devices in NetBox with the *observed* state read live from the devices. It produces a divergence report and lets an administrator decide how to resolve each divergence. The default modules target the needs of PoP-RS (Huawei VRP routers, Vaultwarden, Zabbix).

## Architecture (spec)

The **application module** is a NetBox plugin and sits at the center. It owns the models, views, scheduled jobs and all comparison logic. It uses NetBox's ORM directly; it does not use NetBox's REST API to read NetBox. Three kinds of **pluggable modules** are installed as separate Python packages. Each one handles exactly one external boundary:

| Module type  | Boundary                  | Default implementation |
|--------------|---------------------------|------------------------|
| Connection   | Network devices           | NAPALM (read and open-command exec only, no writes) |
| Credentials  | Where access secrets live | Vaultwarden |
| Notification | Channels the team watches | Zabbix (events) |

Comparison flow for one device:
1. The plugin reads the device from NetBox and converts it to the **canonical model**.
2. It picks the connection module by the device's NetBox **platform** (e.g. `VRP` → module that declares VRP).
3. It asks a credentials module to resolve the device into exactly **(host, username, password)**.
4. The connection module opens the session, runs commands, and returns the requested fields already in canonical form.
5. The plugin diffs the two canonical representations and persists a **divergence report** in NetBox.
6. If the run was a scheduled job, the report also goes to the configured notification modules.

A separate **MCP adapter** process acts as an MCP server. It translates calls into the plugin's REST API and never touches the database or devices directly.

### Module discovery (spec)

Modules are found through Python **entry points**, one group per module type. The plugin lists the entry points at startup but only *imports* a module when it is actually used. Installing a package must be enough for its module to appear. The plugin must never import a concrete module by name.

Entry point groups (constants in `netbox_compare_core.entrypoints`): `netbox_compare.connections`, `netbox_compare.credentials`, `netbox_compare.notifications`. Discovery lives in `netbox_compare/modules.py`.

The canonical model and the module contracts (ABCs) live in `netbox_compare_core`, which has no Django or NetBox dependency. Modules then depend only on that package and can be developed and tested without a NetBox install. The plugin depends on it as well.

## Canonical model (spec)

There are three object types. This vocabulary is shared by the plugin and the connection modules, and the diff runs only on it:

- **Device**: name, manufacturer, model, serial number, OS version
- **Interface**, keyed by name: enabled, description, MTU, speed, MAC address
- **IP address**: interface, address, prefix length

Each field is in one of two categories:
- **Read-only facts** (identity and hardware: manufacturer, serial, …) can only be read.
- **Configuration attributes** (description, MTU, enabled, …) can also be changed on the device, if a connection module supports it.

The model must have a way to say "not observed" that is different from an empty value (see field-level rules below). Do not use `""`/`None` for both meanings.

NetBox mapping notes: some canonical fields have no stable home in the NetBox schema. OS version has no native Device field, and the interface MAC address moved to a separate MAC address model in NetBox 4.2. The NetBox→canonical translation must handle each schema version explicitly. If a field does not exist in the installed version, it is reported as *not comparable*, not as blank.

## Connection module contract (spec)

- The module declares, **per platform**, which canonical fields it can **read**, which configuration attributes it can **write**, and whether it supports **open command execution**.
- The plugin reads these declarations *before* making a request, so it knows in advance what each device can be checked for.
- The plugin asks for fields **by name**. The module decides which commands to run and returns **exactly** the requested fields, already in canonical form.
- Open command execution sends an arbitrary command string (e.g. `display cpu-usage`) and returns the raw output without parsing it. Modules only implement the transport. The commands themselves are defined in the plugin.
- The module gets credentials for each session and must not know where they came from.

The NAPALM module gets its fields from NAPALM getters and declares no write capability. As a result, divergences on its devices can only be fixed in the documentation.

## Comparison semantics (spec — the core logic, get this right)

**Object level** (interfaces, IP addresses). Each object falls into one of four classes:
- only on the device (undocumented) → divergence
- in both, with differing fields → divergence
- in both, identical → not a divergence
- only documented, not found on the device → divergence

**Field level** (only for objects present in both sources). Each field gets one of three results:
- **match**
- **divergence**
- **not comparable**, which is neither a match nor a divergence. It happens when:
  - the value was not observed: the module declared it cannot read the field on this platform, or it did not produce the value in this run; or
  - the field does not exist in the installed NetBox version's schema.

A field that exists but that the operator left **blank** is a valid value and is compared normally.

**Comparison policy**: the policy selects which canonical fields are considered. Divergences on other fields are dropped and never appear in the report. Each considered field has a **severity**, which is passed to the notification modules.

**Resolution rules**:
- A fix in the **documentation** is always offered.
- A fix on the **device** is offered only if the field is a configuration attribute *and* the device's connection module declares write support for that field on that platform.
- The administrator always chooses. The plugin **never pre-selects** a direction.
- **Scheduled jobs never apply fixes.** They only detect, report and notify.

## Plugin features (spec)

- Start a comparison manually from the UI, or schedule periodic jobs over a set of devices. Each job can be linked to notification modules.
- Store reports in NetBox, showing the documented and observed value for each divergence, with resolve actions.
- **Open commands**: text templates with parameterized parts, filled in at run time and executed through the connection module's open-exec method. **Every run is audit-logged** with the command sent, output, target device, user and timestamp. The plugin cannot guarantee a command is non-destructive. The audit log is the safeguard, so it must never be optional or skippable.
- A page listing the installed modules, with access to each module's settings.
- A REST API exposing the plugin's operations. The MCP adapter uses it.

## MCP exposure boundary (spec)

- **Exposed to agents**: query comparisons and divergences, request new comparisons, run open commands that are **already declared**.
- **Never exposed**: creating or editing open commands, applying fixes (documentation or device). These stay with the administrator in the plugin UI.

Enforce this boundary in the adapter *and* through the permissions of the API token the adapter uses. Do not rely on the adapter alone.
