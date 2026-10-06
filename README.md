![D2HA Bridge](docs/assets/branding/readme-logo.png)

# D2HA Bridge for Home Assistant

D2HA Bridge connects a compatible Dovit TCP/XML installation to Home Assistant through MQTT. It provides device mapping, MQTT discovery, connection diagnostics, a German/French web interface, and a restricted recovery assistant. Apple Home can use the resulting Home Assistant entities through the optional HomeKit Bridge integration.

D2HA Bridge is an independent, unofficial community project. It is not affiliated with, endorsed by, or sponsored by Dovit or RISCO Group. Dovit and related marks are the property of their respective owners. The public app is marked **experimental**: its runtime is based on version 2.2, but installation of this public repository on a new user's Home Assistant and compatibility with other Dovit installations have not yet been verified.

**Branding transition:** The public project is now **D2HA Bridge**. The installable app remains version **2.2** and is still displayed as **Dovit Bridge** in Home Assistant. The 3.0.0 runtime rebrand is being prepared and has not been released.

**Existing installations:** Keep your current repository entry and installed app. If you added `https://github.com/SPRuben/dovit-bridge`, keep that configured URL; GitHub redirects it to the renamed repository. Changing the stored repository URL can change the HA app identity. A project rename does not require reinstalling the app, replacing your mapping, resetting MQTT discovery or pairing HomeKit again.

**License:** Free noncommercial use of the unchanged software is allowed. Program/documentation changes and commercial use require prior written permission; commercial permission requires a separate agreement on use and compensation. Your own configuration and device mappings are allowed and remain yours. Read the [license](LICENSE) and [German explanation](LICENCE_DE.md). This is source available under custom terms, not an open source license; no automatic fee is set.

GitHub platform rights under its own [terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#d-user-generated-content), including public viewing/forking and uncompensated GitHub/affiliate AI-training rights, are unaffected by this project's license.

## Requirements

- Home Assistant OS with Supervisor and access to the app store. Home Assistant Container does not provide this app installation route.
- An `amd64` or `aarch64` system. Earlier development builds for `armv7` are historical and are not offered by this public package.
- A reachable Dovit TCP/XML endpoint, your own verified device IDs and signal types, and an MQTT broker connected to Home Assistant's MQTT integration.

## Install in Home Assistant

[Installation guide for Home Assistant](dovit_bridge/DOCS.md)

1. Open **Settings → Apps → App store → ⋮ → Repositories**. Older Home Assistant versions call apps “add-ons”.
2. Add this repository URL: `https://github.com/SPRuben/d2ha-bridge`.
3. Refresh the store, select the app currently listed as **Dovit Bridge** (D2HA Bridge version 2.2), and install it.
4. Set your own Dovit host/port and MQTT connection in the app configuration. The Dovit default `127.0.0.1` is unconfigured; MQTT credentials are empty. Do not reuse another household's mapping.
5. Start the app and open its web interface. With no mapping file, the restricted recovery assistant appears first. For a genuinely new installation, choose **Neue Installation vorbereiten**, review the empty mapping, validate it and explicitly consent. For an existing installation, restore your own mapping instead. Restart the app manually.
6. Map your own devices, restart when a saved change requests it, and enable publication of known devices (`publish_discovery: true`) to Home Assistant. MQTT connection alone does not create entities.

Read the [complete installation guide](dovit_bridge/DOCS.md) before enabling physical control or migrating an existing bridge.

## Schnellstart auf Deutsch

Unter **Einstellungen → Apps → App-Store → ⋮ → Repositories** die URL `https://github.com/SPRuben/d2ha-bridge` hinzufügen und die derzeit als **Dovit Bridge** gelistete App (D2HA Bridge Version 2.2) installieren. Eigene Dovit-Adresse und MQTT-Verbindung eintragen. Nach dem ersten Start erscheint ohne Gerätedatei der Wiederherstellungsassistent: Nur bei einer wirklich neuen Anlage **Neue Installation vorbereiten** wählen, prüfen und ausdrücklich bestätigen; vorhandene Zuordnungen aus der eigenen Sicherung wiederherstellen. Danach selbst neu starten, eigene Geräte zuordnen und bekannte Geräte per MQTT veröffentlichen.

Unveränderte nichtkommerzielle Nutzung ist kostenlos. Änderungen und kommerzielle Nutzung benötigen vorher die schriftliche Erlaubnis des Rechteinhabers; eine kommerzielle Vergütung wird separat vereinbart. Eigene Einstellungen und Gerätezuordnungen sind erlaubt. Siehe [Nutzungsbedingungen](LICENCE_DE.md).

Die reine GitHub-Umbenennung benötigt keine Neuinstallation: Den bestehenden Repository-Eintrag und die App behalten. Nur bei einem Wechsel von einer lokalen App zu einer Repository-Installation gilt: zuerst die alte Bridge stoppen. Die neue Repository-App hat eine andere HA-App-Identität; `/share`-Zuordnungen und private `/data`-Einstellungen sorgfältig sichern und übertragen. Beide Bridges niemals parallel betreiben.

## Documentation

- [Installation and configuration / Installation und Einrichtung](dovit_bridge/DOCS.md)
- [German user manual](docs/USER_DE.md)
- [French user manual](docs/USER_FR.md)
- [Developer manual](docs/DEVELOPER.md)
- [Changelog and verification limits](dovit_bridge/CHANGELOG.md)

The tutorial screenshots use simulated data and were captured from the 2.0 interface. They illustrate workflows retained in 2.2; they are not screenshots of a live installation.

## Support

For an issue, describe your app version, Home Assistant installation type, architecture, and relevant error messages. Remove passwords, alarm codes, private addresses, raw device telegrams and household-specific mapping details before posting logs or files. Do not post your active `/share` mapping or `/data` settings publicly.
