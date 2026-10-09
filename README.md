![D2HA Bridge](docs/assets/branding/readme-logo.png)

# D2HA Bridge for Home Assistant

D2HA Bridge is an independent Home Assistant bridge for compatible Dovit home-automation installations. It translates the Dovit TCP/XML protocol to MQTT and Home Assistant MQTT Discovery. It includes device mapping, diagnostics, a German/French Ingress interface and restricted recovery. Apple Home can use the resulting HA entities through Home Assistant's optional HomeKit Bridge integration.

D2HA Bridge is an independent, unofficial community project. It is not affiliated with, endorsed by, or sponsored by Dovit or RISCO Group. Dovit and related marks are the property of their respective owners.

**3.1.0 is the Phase 2 migration candidate**, marked experimental. It adds the separate `d2ha_bridge` HA app identity; the unchanged legacy 3.0.0 app remains available for rollback. MQTT IDs/topics, Dovit protocol and commands, mappings, file paths, Web UI and HomeKit behavior stay compatible. Actual HA migration acceptance and public 3.1 image publication are pending. See [migration](docs/MIGRATION_3_1.md) and [release checks](docs/RELEASING.md).

**License:** Free noncommercial use of the unchanged software is allowed. Program/documentation changes and commercial use require prior written permission; commercial permission requires a separate agreement on use and compensation. Your own configuration and device mappings are allowed and remain yours. Read the [license](LICENSE) and [German explanation](LICENCE_DE.md). This is source available under custom terms, not an open source license; no automatic fee is set.

GitHub platform rights under its own [terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#d-user-generated-content), including public viewing/forking and uncompensated GitHub/affiliate AI-training rights, are unaffected by this project's license.

## Existing users: migrate safely or keep 3.0

The repository contains both identities: legacy **3.0.0** (`local_dovit_bridge`) and new **3.1.0** (`d2ha_bridge`). Version 3.1 is a separate app with separate private data. Create a current full HA backup and follow [the controlled migration and rollback procedure](docs/MIGRATION_3_1.md) before installing/starting it. Keep the old app stopped for rollback; never run both bridges against the same home.

Keep your existing repository entry, private options, mapping and entity IDs. If you added `https://github.com/SPRuben/dovit-bridge`, **keep that URL in HA**; do not remove/re-add it under the new URL. Existing local installations remain local for this migration. Do not initialize an empty existing home, reset MQTT discovery, rename HA registry entities or re-pair HomeKit. Users staying on the unchanged 3.0 app can use [the Phase 1 instructions](docs/MIGRATION_D2HA.md).

## New installation in Home Assistant

Requires Home Assistant OS with Supervisor/app store, administrator access, `amd64` or `aarch64`, your compatible Dovit TCP/XML endpoint, and an MQTT broker connected to HA's MQTT integration. HA Container does not provide this installation route.

[Installation guide for Home Assistant](d2ha_bridge/DOCS.md)

1. Open **Settings → Apps → App store → ⋮ → Repositories**. Older HA versions call apps “add-ons”.
2. Add `https://github.com/SPRuben/d2ha-bridge` and refresh the store.
3. After image publication, select the **D2HA Bridge 3.1.0** entry and install it. Version 3.1.0 downloads `ghcr.io/spruben/d2ha-bridge:3.1.0` for your architecture; it does not build a local fallback if this image is unavailable.
4. Configure your own Dovit host/port and MQTT connection. `127.0.0.1` is an unconfigured Dovit default and refers to the container itself; MQTT credentials are empty.
5. Start manually (boot is manual by default) and open the web interface through HA Ingress. A missing mapping starts restricted recovery without Dovit/MQTT connections. Only for a genuinely new installation choose **Neue Installation vorbereiten**, validate the empty mapping and explicitly consent. Existing users restore their own mapping instead. Restart manually.
6. Map your own devices, review changes and restart when requested. Keep `enable_discovery: false` for a controlled setup; enable publication of known devices with `publish_discovery: true` after checking your mapping. MQTT connection alone does not create entities.

Port 8099 stays internal to Ingress, with no host networking or host port mapping. Dovit and MQTT use outbound connections to your configured endpoints.

The supplied `dovit_devices.json` contains only empty categories. No credentials, private options, backups or household device list are distributed. Never publish your active `/share` mapping or `/data` setup.

## Schnellstart auf Deutsch

**Bestehende Installation:** 3.0 bleibt unverändert verfügbar. Für 3.1 ist eine kontrollierte Migration auf eine neue App erforderlich: vollständige aktuelle HA-Sicherung, private Optionen und Daten übernehmen, gemeinsame Mapping-Dateien erhalten und nur eine Bridge starten. Bisherigen Repository-Eintrag und lokale/GitHub-Installationsquelle behalten. Kein Zurücksetzen von Entities/HomeKit. Details: [Migration 3.1 und Rückweg](docs/MIGRATION_3_1.md).

**Neue Installation:** Nach Veröffentlichung der Images unter **Einstellungen → Apps → App-Store → ⋮ → Repositories** `https://github.com/SPRuben/d2ha-bridge` hinzufügen und den **3.1.0**-Eintrag auswählen. Eigene Dovit-Adresse/MQTT-Verbindung eintragen und manuell starten. Nur bei einer tatsächlich neuen Anlage Recovery mit leerem Mapping vorbereiten; bestehende Zuordnungen erhalten/wiederherstellen.

## Documentation

- [Installation and configuration / Installation und Einrichtung](d2ha_bridge/DOCS.md)
- [Phase 2 migration and rollback](docs/MIGRATION_3_1.md)
- [Legacy Phase 1 migration and preserved identities](docs/MIGRATION_D2HA.md)
- [German user manual](docs/USER_DE.md)
- [French user manual](docs/USER_FR.md)
- [Developer manual](docs/DEVELOPER.md)
- [Release preparation and GHCR availability](docs/RELEASING.md)
- [App, GitHub and dashboard artwork](docs/BRANDING.md)
- [Changelog and verification limits](d2ha_bridge/CHANGELOG.md)

Tutorial screenshots are historical 2.0 captures with simulated data and the former branding. They illustrate retained workflows, not the current appearance or a live installation.

## Support

Describe your app version, HA installation type, architecture and relevant errors. Remove passwords, alarm codes, private addresses, raw device telegrams and household-specific mappings before posting logs or files.
