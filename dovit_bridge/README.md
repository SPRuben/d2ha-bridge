# D2HA Bridge

Experimental Home Assistant app for a compatible Dovit TCP/XML installation, connected to Home Assistant through MQTT. Includes German/French Ingress UI, mapping editor, diagnostics, and a restricted recovery assistant.

**License:** Unchanged noncommercial use is free. Changes to the software/documents and commercial use require prior written permission; commercial terms and compensation must be agreed separately. Your own configuration and device data are allowed and remain yours. See [LICENSE](../LICENSE) and [German explanation](../LICENCE_DE.md). This is source available under custom terms.

Install the repository `https://github.com/SPRuben/d2ha-bridge` through Home Assistant's app store on HA OS with Supervisor. Supported public architectures are `amd64` and `aarch64`.

Read [DOCS.md](DOCS.md) for first installation, MQTT publication, mapping, migration and optional HomeKit. Read [CHANGELOG.md](CHANGELOG.md) for the 3.0.0 rebrand/packaging and inherited runtime changes and the public package's verification limits.

3.0.0 is an experimental Phase 1 prerelease. HA uses prebuilt versioned GHCR images on both architectures. Ingress uses internal port 8099 with no host port or host networking. Phase 1 keeps `slug: local_dovit_bridge`. Existing users keep the same app/repository entry and private configuration; new users use the new repository URL. See [migration and rollback](../docs/MIGRATION_D2HA.md).

Each home needs its own Dovit endpoint and verified mapping. No active household mapping is distributed. The unconfigured Dovit host `127.0.0.1` and empty MQTT credentials must be replaced with your own settings. With a missing mapping file, first start opens restricted recovery; it does not connect to Dovit or MQTT.

D2HA Bridge is an independent, unofficial community project. It is not affiliated with, endorsed by, or sponsored by Dovit or RISCO Group. Dovit and related marks are the property of their respective owners.
