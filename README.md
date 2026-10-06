![D2HA Bridge](docs/assets/branding/readme-logo.png)

# D2HA Bridge for Home Assistant

D2HA Bridge is an independent Home Assistant bridge for compatible Dovit home-automation installations. It translates the Dovit TCP/XML protocol to MQTT and Home Assistant MQTT Discovery. It includes device mapping, diagnostics, a German/French Ingress interface and restricted recovery. Apple Home can use the resulting HA entities through Home Assistant's optional HomeKit Bridge integration.

D2HA Bridge is an independent, unofficial community project. It is not affiliated with, endorsed by, or sponsored by Dovit or RISCO Group. Dovit and related marks are the property of their respective owners.

**3.0.0 is a Phase 1 rebrand release candidate**, marked experimental. Protocol, commands, topics, IDs and mapping formats remain compatible with 2.2. Real HA/Supervisor/Ingress, Dovit hardware and HomeKit acceptance are still pending. This checkout prepares the release; it has not published 3.0.0 or its images. Maintainers must complete [release preparation](docs/RELEASING.md) before making it available in the store.

**License:** Free noncommercial use of the unchanged software is allowed. Program/documentation changes and commercial use require prior written permission; commercial permission requires a separate agreement on use and compensation. Your own configuration and device mappings are allowed and remain yours. Read the [license](LICENSE) and [German explanation](LICENCE_DE.md). This is source available under custom terms, not an open source license; no automatic fee is set.

GitHub platform rights under its own [terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#d-user-generated-content), including public viewing/forking and uncompensated GitHub/affiliate AI-training rights, are unaffected by this project's license.

## Existing users: update the same app

Keep your existing repository entry, app options, mapping and entity IDs. If you added `https://github.com/SPRuben/dovit-bridge`, **keep that URL in HA** after the GitHub rename; do not remove/re-add the repository under the new URL. HA derives repository identity from the configured URL. The app slug remains `local_dovit_bridge`. The old GitHub URL redirects after a normal rename.

An already installed local app should stay local for this update; switching it to a repository installation is a separate data migration. Do not reinstall, initialize an empty mapping, reset MQTT discovery or re-pair HomeKit for a name change. Read [Phase 1 update and rollback](docs/MIGRATION_D2HA.md) before updating.

## New installation in Home Assistant

Requires Home Assistant OS with Supervisor/app store, administrator access, `amd64` or `aarch64`, your compatible Dovit TCP/XML endpoint, and an MQTT broker connected to HA's MQTT integration. HA Container does not provide this installation route.

[Installation guide for Home Assistant](dovit_bridge/DOCS.md)

1. Open **Settings → Apps → App store → ⋮ → Repositories**. Older HA versions call apps “add-ons”.
2. Add `https://github.com/SPRuben/d2ha-bridge` and refresh the store.
3. Select **D2HA Bridge** and install the available released version. Once 3.0.0 is published, HA downloads `ghcr.io/spruben/d2ha-bridge:3.0.0` for your architecture; it does not build a local fallback if this image is unavailable.
4. Configure your own Dovit host/port and MQTT connection. `127.0.0.1` is an unconfigured Dovit default and refers to the container itself; MQTT credentials are empty.
5. Start and open the web interface through HA Ingress. A missing mapping starts restricted recovery without Dovit/MQTT connections. Only for a genuinely new installation choose **Neue Installation vorbereiten**, validate the empty mapping and explicitly consent. Existing users restore their own mapping instead. Restart manually.
6. Map your own devices, review changes and restart when requested. Keep `enable_discovery: false` for a controlled setup; enable publication of known devices with `publish_discovery: true` after checking your mapping. MQTT connection alone does not create entities.

Port 8099 stays internal to Ingress, with no host networking or host port mapping. Dovit and MQTT use outbound connections to your configured endpoints.

The supplied `dovit_devices.json` contains only empty categories. No credentials, private options, backups or household device list are distributed. Never publish your active `/share` mapping or `/data` setup.

## Schnellstart auf Deutsch

**Bestehende Installation:** HA-Backup und eigene Dateien sichern, bisherigen Repository-Eintrag und App-Slug behalten und dieselbe App aktualisieren. Eine lokale Installation bleibt zunächst lokal. Kein erneutes Hinzufügen unter der neuen URL, keine leere Neuinstallation und kein Zurücksetzen der Entitäten/HomeKit-Verknüpfungen. Details: [Migration](docs/MIGRATION_D2HA.md).

**Neue Installation:** Unter **Einstellungen → Apps → App-Store → ⋮ → Repositories** `https://github.com/SPRuben/d2ha-bridge` hinzufügen und **D2HA Bridge** installieren, sobald die Version veröffentlicht ist. Eigene Dovit-Adresse/MQTT-Verbindung eintragen. Ohne Gerätedatei erscheint Recovery: Nur bei einer tatsächlich neuen Anlage **Neue Installation vorbereiten** wählen, prüfen und bestätigen; sonst eigene Sicherung wiederherstellen. Danach neu starten, eigene Geräte zuordnen und bekannte Geräte per MQTT veröffentlichen.

## Documentation

- [Installation and configuration / Installation und Einrichtung](dovit_bridge/DOCS.md)
- [Phase 1 migration and preserved identities](docs/MIGRATION_D2HA.md)
- [German user manual](docs/USER_DE.md)
- [French user manual](docs/USER_FR.md)
- [Developer manual](docs/DEVELOPER.md)
- [Release preparation and GHCR availability](docs/RELEASING.md)
- [App, GitHub and dashboard artwork](docs/BRANDING.md)
- [Changelog and verification limits](dovit_bridge/CHANGELOG.md)

Tutorial screenshots are historical 2.0 captures with simulated data and the former branding. They illustrate retained workflows, not the current appearance or a live installation.

## Support

Describe your app version, HA installation type, architecture and relevant errors. Remove passwords, alarm codes, private addresses, raw device telegrams and household-specific mappings before posting logs or files.
