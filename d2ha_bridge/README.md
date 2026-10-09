# D2HA Bridge 3.1.0

Experimental Home Assistant app with the new `d2ha_bridge` HA identity. MQTT/HA entity identities, topics, options, mapping, private paths, Web UI and HomeKit behavior remain compatible. The separate legacy 3.0.0 app stays available for rollback.

**Existing installation:** This is a private data migration, not an update of the same app. Create a current full HA backup, keep your repository/local source, transfer actual options and private `/data`, preserve shared mappings and start only one bridge. Read [migration and rollback](../docs/MIGRATION_3_1.md) before installing/starting.

**New installation:** Add `https://github.com/SPRuben/d2ha-bridge` through the HA OS app store, choose the 3.1.0 entry after its versioned public GHCR images are available, configure your own Dovit/MQTT settings and start manually. Supported architectures: amd64/aarch64. Port 8099 stays internal to Ingress; no host networking or host ports. The distributed device seed is empty; it must never overwrite an existing home.

Read [DOCS.md](DOCS.md), [CHANGELOG.md](CHANGELOG.md) and [release preparation](../docs/RELEASING.md). Actual HA/Supervisor/Ingress/LAN/hardware, automation and HomeKit migration acceptance remains pending. The offline migration CLI validates/stages private snapshots; it does not control HA or perform live transfer.

**License:** Unchanged noncommercial use is free. Changes to software/documents and commercial use require prior written permission; commercial terms and compensation must be agreed separately. Your own configuration/device data remain yours. See [LICENSE](../LICENSE) and [German explanation](../LICENCE_DE.md). This is source available under custom terms.

D2HA Bridge is an independent, unofficial community project. It is not affiliated with, endorsed by, or sponsored by Dovit or RISCO Group. Dovit and related marks are the property of their respective owners.
