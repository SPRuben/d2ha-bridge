![D2HA Bridge](docs/assets/branding/readme-logo.png)

# D2HA Bridge 3.1

D2HA Bridge connects a compatible home-automation TCP/XML server to MQTT and Home Assistant. It provides device mapping, German/French configuration and diagnostics, and a web interface through Home Assistant Ingress. Apple Home can use the resulting entities through Home Assistant's optional HomeKit Bridge integration.

**Experimental test release. It may contain errors. Use at your own risk. Compatibility with every Dovit server/firmware version is unknown. Verify your own installation and keep a restorable Home Assistant backup.**

**Experimentelle Testversion:** Fehler sind möglich. Die Nutzung erfolgt auf eigene Gefahr. Wir wissen nicht, ob die Bridge mit jeder Dovit-Serverversion funktioniert. Sichere Home Assistant und deine privaten Einstellungen vor der Installation oder einem Update.

## Install in Home Assistant

Requires Home Assistant OS with Supervisor and administrator access, `amd64` or `aarch64`, a compatible TCP/XML endpoint and an MQTT broker connected to HA's MQTT integration.

1. Open **Settings → Apps → App store → ⋮ → Repositories**.
2. Add `https://github.com/SPRuben/d2ha-bridge` and refresh the store.
3. Install **D2HA Bridge**. The versioned public GHCR image supplies your architecture; no local build is required once the release images are published.
4. Enter your own server address/port and MQTT settings. `127.0.0.1` is an unconfigured server default; MQTT credentials are empty.
5. Start manually and choose **Open Web UI**. If the mapping is missing or invalid, restricted recovery starts without server/MQTT connections. Initialize an empty mapping only for a genuinely new installation; otherwise restore your own mapping.
6. Identify and map your own devices, review changes and restart when requested. Keep automatic discovery off initially. Publish checked known mappings with `publish_discovery: true` and verify the resulting entities in HA before using them in automations or HomeKit.

[Installation and configuration](d2ha_bridge/DOCS.md) · [German manual](docs/USER_DE.md) · [French manual](docs/USER_FR.md)

## Existing installations

Keep your HA repository entry, installation source, MQTT/HA identities and private data. Do not reinstall or re-pair HomeKit to change the displayed product name. Changing the HA app identity creates separate private storage: read [existing installations and safe transfer](docs/EXISTING_INSTALLATIONS.md) before replacing an app. Never run two bridges against the same home or copy an empty seed over an existing mapping.

The distributed `dovit_devices.json` contains only empty categories. No household mapping, credentials, private options or backups are supplied. Technical configuration keys, file paths and MQTT identifiers stay compatible with existing installations.

## Alarm state after restart

With mapped alarm partitions, the bridge requests current states after every new TCP connection using the read-only startup synchronization used by the official app. Both configured partition readings were verified on the affected installation without operating the alarm. Availability still requires fresh server readings; stored values are never substituted as current. Compatibility with other server versions is unknown. See [alarm diagnostics](docs/ALARM_STARTUP.md).

## Network and support

Port 8099 is internal to HA Ingress, with no host networking or published host port. Server and MQTT connections use your configured endpoints.

Report the app/server versions, HA installation type, architecture and relevant errors in [GitHub Issues](https://github.com/SPRuben/d2ha-bridge/issues). Remove passwords, alarm codes, private addresses and household data before posting logs or files. Tests on one installation do not establish compatibility with other servers or firmware.

## License

Unchanged noncommercial use is free under the [custom license](LICENSE). Software/documentation changes and commercial use require prior written permission; commercial terms and compensation must be agreed separately. Your configuration and device mappings remain yours. See [the German explanation](LICENCE_DE.md). D2HA Bridge is an independent, unofficial community project.

[Current changelog](d2ha_bridge/CHANGELOG.md) · [Artwork](docs/BRANDING.md) · [Release checks](docs/RELEASING.md)
