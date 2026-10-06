# Dovit Bridge for Home Assistant

Dovit Bridge connects a compatible Dovit TCP/XML installation to Home Assistant through MQTT. It provides device mapping, MQTT discovery, connection diagnostics, a German/French web interface, and a restricted recovery assistant. Apple Home can use the resulting Home Assistant entities through the optional HomeKit Bridge integration.

This is a community project. It is not an official Dovit or Home Assistant product. The public app is marked **experimental**: its runtime is based on version 2.2, but installation of this public repository on a new user's Home Assistant and compatibility with other Dovit installations have not yet been verified.

**License:** Free noncommercial use of the unchanged software is allowed. Program/documentation changes and commercial use require prior written permission; commercial permission requires a separate agreement on use and compensation. Your own configuration and device mappings are allowed and remain yours. Read the [license](LICENSE) and [German explanation](LICENCE_DE.md). This is source available under custom terms, not an open source license; no automatic fee is set.

GitHub platform rights under its own [terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#d-user-generated-content), including public viewing/forking and uncompensated GitHub/affiliate AI-training rights, are unaffected by this project's license.

## Requirements

- Home Assistant OS with Supervisor and access to the app store. Home Assistant Container does not provide this app installation route.
- An `amd64` or `aarch64` system. Earlier development builds for `armv7` are historical and are not offered by this public package.
- A reachable Dovit TCP/XML endpoint, your own verified device IDs and signal types, and an MQTT broker connected to Home Assistant's MQTT integration.

## Install in Home Assistant

[Add repository to Home Assistant](https://my.home-assistant.io/redirect/supervisor_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FSPRuben%2Fdovit-bridge)

1. Open **Settings → Apps → App store → ⋮ → Repositories**. Older Home Assistant versions call apps “add-ons”.
2. Add this repository URL: `https://github.com/SPRuben/dovit-bridge`.
3. Refresh the store, select **Dovit Bridge**, and install it.
4. Set your own Dovit host/port and MQTT connection in the app configuration. The Dovit default `127.0.0.1` is unconfigured; MQTT credentials are empty. Do not reuse another household's mapping.
5. Start the app and open its web interface. With no mapping file, the restricted recovery assistant appears first. For a genuinely new installation, choose **Neue Installation vorbereiten**, review the empty mapping, validate it and explicitly consent. For an existing installation, restore your own mapping instead. Restart the app manually.
6. Map your own devices, restart when a saved change requests it, and enable publication of known devices (`publish_discovery: true`) to Home Assistant. MQTT connection alone does not create entities.

Read the [complete installation guide](dovit_bridge/DOCS.md) before enabling physical control or migrating an existing bridge.

## Schnellstart auf Deutsch

Unter **Einstellungen → Apps → App-Store → ⋮ → Repositories** die URL `https://github.com/SPRuben/dovit-bridge` hinzufügen und **Dovit Bridge** installieren. Eigene Dovit-Adresse und MQTT-Verbindung eintragen. Nach dem ersten Start erscheint ohne Gerätedatei der Wiederherstellungsassistent: Nur bei einer wirklich neuen Anlage **Neue Installation vorbereiten** wählen, prüfen und ausdrücklich bestätigen; vorhandene Zuordnungen aus der eigenen Sicherung wiederherstellen. Danach selbst neu starten, eigene Geräte zuordnen und bekannte Geräte per MQTT veröffentlichen.

Unveränderte nichtkommerzielle Nutzung ist kostenlos. Änderungen und kommerzielle Nutzung benötigen vorher die schriftliche Erlaubnis des Rechteinhabers; eine kommerzielle Vergütung wird separat vereinbart. Eigene Einstellungen und Gerätezuordnungen sind erlaubt. Siehe [Nutzungsbedingungen](LICENCE_DE.md).

Bei einer Migration zuerst die alte Bridge stoppen. Die neue Repository-App hat eine andere HA-App-Identität; `/share`-Zuordnungen und private `/data`-Einstellungen sorgfältig sichern und übertragen. Beide Bridges niemals parallel betreiben.

## Documentation

- [Installation and configuration / Installation und Einrichtung](dovit_bridge/DOCS.md)
- [German user manual](docs/USER_DE.md)
- [French user manual](docs/USER_FR.md)
- [Developer manual](docs/DEVELOPER.md)
- [Changelog and verification limits](dovit_bridge/CHANGELOG.md)

The tutorial screenshots use simulated data and were captured from the 2.0 interface. They illustrate workflows retained in 2.2; they are not screenshots of a live installation.

## Support

For an issue, describe your app version, Home Assistant installation type, architecture, and relevant error messages. Remove passwords, alarm codes, private addresses, raw device telegrams and household-specific mapping details before posting logs or files. Do not post your active `/share` mapping or `/data` settings publicly.
