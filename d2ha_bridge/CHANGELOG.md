# Changelog

## 3.1.0 — Phase 2 HA app identity migration

- Add the separate HA app slug `d2ha_bridge` with manual boot by default. Retain the complete legacy 3.0.0 app definition and versioned image as a rollback route; never run both bridges together.
- Add an offline private snapshot export/inspection/staging helper. Preserve original options and private setup for rollback; validate hashes, custom paths, pending edits and effective setup precedence, and disable publication/control flags in the target copy initially.
- Reject incomplete/redacted exports, malformed configuration, unexpected app identities, existing staging destinations and unsafe/oversized archives. Never transfer Supervisor/Ingress runtime credentials or overwrite shared mappings automatically.
- Preserve Python package, Dovit TCP/XML, all MQTT unique/device/entity IDs/topics, option keys, storage paths, mapping fields, device types, Web UI functions and HomeKit logic. Only the displayed runtime/UI version changes to 3.1.0.
- Check both app definitions and frozen legacy files in CI; build the new app for amd64/aarch64 and prepare versioned GHCR images and release notes. The public seed remains empty and new private transfer artifacts are ignored.
- Document complete HA backup, stopped-data transfer, single-bridge cutover, re-enabling discovery and rollback without reinstalling HomeKit or deleting the old app.

This is an experimental migration candidate. Offline checks use synthetic data; actual HA/Supervisor/Ingress/LAN/hardware, entity/automation and HomeKit migration acceptance remains pending. No release notes claim a live migration or physical test. Public publication requires verified versioned images first.

## 3.0.0 — D2HA Bridge Phase 1 rebrand

- Rename the public product to **D2HA Bridge**; apply supplied app, GitHub, dashboard and web artwork and the independent/unofficial project disclaimer.
- Rename the existing GitHub repository to `SPRuben/d2ha-bridge`, update links and use versioned public GHCR images for amd64/aarch64. Preserve repository identity and history; do not delete/recreate it.
- Keep `slug: local_dovit_bridge`, package/folder names, all MQTT unique IDs/device identifiers/topics, option keys, persistent paths and mapping formats. Existing HA users retain their repository entry and installation source; changing the configured URL can create a separate app identity.
- Update only MQTT discovery device display name and manufacturer attribution. Entity names from mappings and discovery identities/behavior remain unchanged. Dovit TCP/XML, device/control logic, supported types, UI functions and HomeKit logic remain unchanged.
- Carry forward internal-network Ingress on port 8099 without host ports, dynamically resolved Supervisor TCP-peer authentication, current app labels/share mount, and removal of unnecessary `build.yaml`.
- Pin Python 3.11.17 / Alpine 3.23 by multi-architecture digest; retain Paho 2.1.0. Add Python/Node, syntax/config/privacy, MQTT/TLS and amd64/aarch64 build/startup CI. Publish images only after an explicit version-tag push or publish-enabled dispatch.
- Keep the public device seed empty, strengthen privacy exclusions, and document safe updates, rollback, optional dashboard branding and release steps. The earlier unpublished 2.2.1 slug-change proposal is superseded; Phase 2 is not implemented.

3.0.0 is released as an experimental prerelease. The maintainer reports the existing local 3.0 installation is running. Independent HA update-in-place/new-installation, Supervisor/Ingress, Dovit LAN/hardware, entity duplication/automations and HomeKit acceptance remains pending. ARM local checks use CPU emulation. Historical tutorial screenshots show simulated 2.0 workflows with the former branding.

## 2.2 — public experimental package

The public package is based on the 2.2 runtime and adds repository installation metadata and public documentation. It offers `amd64` and `aarch64`; older `armv7` build verification is historical. Public defaults use an unconfigured Dovit host (`127.0.0.1`) and empty MQTT credentials, and the package contains no active household mapping. These packaging and default changes differ from the previously tested local 2.2 release.

Runtime features inherited from 2.2:

- New switch discovery uses `default_entity_id: switch.dovit_switch_<ID>` on first registration. Unique IDs and MQTT topics remain unchanged. Home Assistant preserves entity IDs already stored in its registry.
- Configurable binary switches with MQTT command/state handling, strict state validation, session handling, mapping editor and recovery support.
- German/French device, setup and diagnostic views, reviewed mapping changes and integrated manuals.
- Private Dovit/MQTT setup overrides, optional Supervisor MQTT service resolution, TLS certificate validation and connection diagnostics.
- Restricted startup recovery for missing or invalid mappings; validated restore/empty initialization requires explicit consent and a manual restart.
- Availability and same-session state handling, retained-command rejection, optional confirmed web control, and scoped non-alarm discovery/state cleanup.

The prepared public package was checked on 2026-10-06: 360 Python tests passed
on Windows and 360 in the isolated amd64 Alpine image; twelve Node suites and
nine JavaScript syntax checks passed. Both public architecture images built;
all 64 production inputs and the exact 60 image files passed SHA256/length
inventory verification, imports and pip checks. All six restricted startup
cases passed with networking disabled and fresh temporary data: missing mapping,
missing Supervisor token, and invalid setup storage on each architecture.
aarch64 runtime checks used CPU emulation. All 65 historical 2.2 inputs remained
unchanged. The test suite uses synthetic mappings; the published seed is empty.

Live installation of the public repository on a new Home Assistant, real Supervisor/Ingress integration, compatibility with another Dovit installation, new-switch registration and physical command/HomeKit acceptance remain unverified. Do not infer physical compatibility from unit tests or tutorial screenshots.
