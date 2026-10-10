# D2HA Bridge 3.1.1

**Experimental test release. It may contain errors. Use at your own risk. Compatibility with every Dovit server/firmware version is unknown. Verify your own installation and keep a restorable Home Assistant backup.**

Connect a compatible TCP/XML endpoint to Home Assistant through MQTT. Install from `https://github.com/SPRuben/d2ha-bridge`, configure your own server and MQTT settings, and open the UI through HA Ingress. Supported architectures: amd64/aarch64. Port 8099 remains internal. The supplied device mapping is empty.

Existing installations must preserve their private options, mappings and HA/MQTT identities. Never run two bridges against the same home. Read [installation](DOCS.md) and [safe updates/data transfer](../docs/EXISTING_INSTALLATIONS.md).

**Known alarm limitation:** After a restart, some servers supply alarm state only after a later state update. HA/HomeKit can show the alarm as unavailable until fresh readings arrive. This candidate does not fix that behavior or automatically operate the alarm. [Details](../docs/ALARM_STARTUP.md).

Read [the changelog](CHANGELOG.md). Unchanged noncommercial use is free; software/documentation changes and commercial use need prior written permission under the [license](../LICENSE). D2HA Bridge is an independent, unofficial community project.
