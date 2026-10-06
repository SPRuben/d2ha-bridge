# Changelog

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
