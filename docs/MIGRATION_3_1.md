# D2HA Bridge 3.1.0 — neue HA-App-Identität

3.1.0 führt `slug: d2ha_bridge` als separate App ein. Die bestehende Definition mit `slug: local_dovit_bridge` und Version 3.0.0 bleibt unverändert verfügbar. Der Python-Paketname, Dovit TCP/XML, Geräte-/HomeKit-Logik, MQTT-Topics, Discovery-Unique-IDs, Device-Identifier, Optionsschlüssel und Dateipfade bleiben erhalten. Ein Slugwechsel ist keine Aktualisierung der bisherigen App: Die neue App hat eine eigene private `/data`-Ablage.

Die Veröffentlichung und echte HA-/Ingress-/LAN-/Hardware-/HomeKit-Abnahme dieser Migration stehen noch aus. Eine alte Seitenleistenbeschriftung allein verlangt keinen Slugwechsel; dazu siehe [Phase 1](MIGRATION_D2HA.md).

## Voraussetzungen und Sicherung

1. Eine aktuelle vollständige HA-Sicherung einschließlich Core/Registry/HomeKit, alter App, ihrer privaten Daten, Share-Dateien und lokaler App-Quellen abschließen. Wiederherstellungsschlüssel privat aufbewahren. Ein laufender Backup-Job oder ein nicht entschlüsselbares Archiv reicht nicht für einen geprüften Import.
2. Alte vollständige App-ID, Installationsquelle, Version, Architektur, Optionen und bisherige Boot-/Watchdog-/Auto-Update-Einstellungen festhalten. Bisherige Entitäts-/Device-IDs und HomeKit-Zuordnung sichern. Version 3.1.0 unterstützt den Transfer vom geprüften 3.0.0-Stand; andere Quellversionen zuerst gesondert aktualisieren/prüfen.
3. Bestehenden Repository-Eintrag in HA beibehalten, auch wenn dort noch die alte GitHub-URL steht. Lokale Installation zunächst lokal lassen. Ein Wechsel von lokal zu GitHub würde noch einmal eine andere private App-Identität erzeugen.
4. Tatsächliche `devices_file`-/`cover_position_file`-Pfade prüfen, einschließlich privater Einrichtung, Einrichtungssicherungen, Gerätedatei-Sicherungen, Mapping-Drafts und beobachteter Kandidaten. Unterstützte Transferpfade liegen unter `/data` oder `/share`; andere Pfade vor der Migration gesondert klären. Unbekannte private Dateien nicht stillschweigend verwerfen.
5. `<Mapping-Stem>.pending.json` und noch nicht aktivierte Web-Einrichtung bewusst klären. Der Helfer wendet keine pending-Änderung an und verweigert einen Transfer mit ausstehendem Mapping. Niemals eine vorhandene Hauszuordnung durch den leeren öffentlichen Seed ersetzen.

Samba auf `/addons` und `/share` allein liefert nicht die private `/data`-Ablage. Sie muss aus einer freigegebenen, entschlüsselten Sicherung oder über bereits autorisierten Zugriff auf den HA-Host gewonnen werden. Die Bridge erhält dafür keine zusätzlichen Supervisor-/Docker-/Admin-Berechtigungen. Einen alten App-Backupnamen umzubenennen ist keine Migration auf einen neuen Slug.

## Privater Offline-Helfer

Der Helfer befindet sich ausschließlich in der neuen App: `python -m dovit_bridge.migration`. Er ruft keine HA-, MQTT- oder Dovit-Schnittstelle auf und führt weder Installation noch Start/Stop aus. `inspect` prüft nur; `stage` schreibt ausschließlich einen **neuen** privaten Übergabeordner. Es gibt keine automatische Live-Übernahme in `/data`, kein Share-Überschreiben und keine automatische Deinstallation.

Eingaben sind ein vollständiger gestoppter Snapshot der alten privaten Daten und der tatsächlich verwendeten Share-Dateien, außerdem authentifiziertes Supervisor-App-Info-JSON von `/addons/<alte-ID>/info`. Der Helfer verlangt Version 3.0.0, `state: stopped`, `boot: manual`, `watchdog: false`, `auto_update: false` und vollständige, übereinstimmende Optionen. Redigierte `options: {}` sind kein Export. Vor der echten Umschaltung müssen diese Zustände erneut am HA-Host bestätigt werden; ein Offline-JSON belegt keinen aktuellen Laufzustand.

Die folgenden Befehle verwenden ausschließlich **private Offline-Snapshots**. Aus dem App-Ordner ausführen; für eine Linux-Containerprüfung `--network none` verwenden. Pfade vor Ausführung passend setzen. Keine Zugangsdaten in die Befehlszeile schreiben.

```sh
python -m dovit_bridge.migration export \
  --data-dir /private/source-data \
  --share-dir /private/source-share \
  --source-info /private/source-info.json \
  --output /private/migration.bundle

python -m dovit_bridge.migration inspect /private/migration.bundle

python -m dovit_bridge.migration stage /private/migration.bundle \
  --destination /private/new-staging \
  --target-info /private/target-info.json
```

`target-info.json` muss die regulär installierte, gestoppte 3.1.0-App mit gleichem Repository-/lokalem Präfix, manuellem Boot, deaktiviertem Watchdog und Auto-Update beschreiben. Für eine lokale Quelle `local_local_dovit_bridge` erwartet der Helfer `local_d2ha_bridge`; tatsächliche IDs immer aus Supervisor prüfen. Unbekannte private Dateien erfordern eine ausdrückliche Prüfung und gegebenenfalls `--reviewed-data relative/datei.json`. Laufzeit-Tokens, Ingress-/Auth-/Sessiondateien bleiben ausgeschlossen.

Das Bundle und der Übergabeordner enthalten echte Passwörter und private Geräte-/Einrichtungssicherungen. Sie sind **nicht verschlüsselt**. Ausschließlich in einem privaten, angemessen geschützten Speicher aufbewahren; niemals in Git/GHCR/Actions-Artefakte hochladen. Neue Dateien erhalten unter POSIX private Rechte; auf Windows müssen die tatsächlichen NTFS-Zugriffsrechte geprüft werden. Der öffentliche Seed bleibt leer.

Der Helfer begrenzt Datei-/Archivgrößen und Dateianzahl, prüft SHA256/Längen, lehnt absolute Pfade, Traversal, Links, doppelte/abweichende Archiveinträge und vorhandene Zielordner ab. Teilfehler lassen Quelle und vorhandene Backups unverändert. Die Zusammenfassung enthält keine Passwörter, Geräteinhalte oder privaten Dateipfadwerte.

## Kontrollierte Umschaltung

1. Ursprüngliche Betriebsflags sichern. Für beide Apps Start beim Boot auf manuell, Watchdog und Auto-Update aus. Die neue App hat bereits `boot: manual` als Default. Kein Hostneustart darf zwei Bridges starten.
2. Alte Bridge stoppen und gestoppten Zustand bestätigen. Erst danach finalen privaten Daten-/Options-/Share-Snapshot und Supervisor-Info aufnehmen und Hashes vergleichen. Es darf höchstens eine aktive Bridge geben.
3. Neue **3.1.0**-App regulär installieren und gestoppt lassen. Öffentliche Installation benötigt vorher anonym abrufbare GHCR-Images für beide Architekturen. Lokale Installation verwendet den separaten neuen Quellordner. Alte App und Quellen erhalten.
4. Bundle offline exportieren, prüfen und in einen neuen privaten Ordner stagen. Optionen aus `target/options.json` über HA-Konfiguration/unterstützte Supervisor-Optionsschnittstelle setzen. `options.json` nicht per Dateikopie in das Supervisor-Datenverzeichnis einbringen. Dateien aus `target/data/` bei gestoppter Ziel-App über den zuvor geprüften Zugriff in deren neue private Ablage übernehmen. Bei bereits befüllter Zielablage anhalten und klären.
5. `source/share/` ist eine exakte Referenz für Prüfung/Rückweg, kein automatischer Import. Bestehende gemeinsame Share-Dateien und ihre Pfade erhalten. Die neue App muss dieselben Mapping-Bytes, Zusatzfelder und Positionsdaten verwenden. Herkunft und aktueller Hash der echten Dateien prüfen.
6. Der Helfer setzt in der Zielkopie `enable_discovery`, `publish_discovery`, `web_light_control` und `web_device_control` auf false. Vorhandene private Einrichtung erhält zusätzlich `settings.publish_discovery: false`; ihre übrigen Werte bleiben erhalten. Web-Einrichtung überschreibt entsprechende HA-Optionen. Originalbytes/-flags bleiben für den Rückweg im Bundle erhalten.
7. Effektive Konfiguration nach beiden Ladephasen prüfen. Eine erste synthetische technische Prüfung erfolgt isoliert ohne externes Netz. **Discovery aus ist kein Testmodus ohne Steuerbefehle:** Bestehende MQTT-Entities können Befehle senden, Verfügbarkeit kann Automationen auslösen; Web-Flags sperren MQTT nicht. Der echte Start ist ein bewusster Betriebswechsel.
8. Alte App weiterhin gestoppt bestätigen, ausschließlich neue App starten. Version, Mapping, Dovit/MQTT-Verbindung und Ingress prüfen. Kein automatischer Alarm-/Gerätebefehl. Bei Recovery oder abweichenden IDs anhalten, nicht leer initialisieren.
9. Erst nach erfolgreichem Konfigurations-/Identitätsvergleich gewünschte ursprüngliche Discovery-/Steuerflags bewusst freigeben. Originale HA-Entity-/Device-IDs, vollständige Discovery-Payloads und Topics müssen erhalten bleiben. Keine pauschale MQTT-Bereinigung, Registry-Umbenennung oder HomeKit-Neukopplung.
10. Automationen, Dashboards, HomeKit-Zuordnung und fehlende Duplikate prüfen; physische Funktionstests nur bewusst mit Erlaubnis. Nur die neue App darf anschließend automatisch starten. Alte App gestoppt und ohne Watchdog/Autostart für Rollback behalten. Deinstallation erfolgt erst nach gesonderter Entscheidung.

## Rückweg auf 3.0.0

Neue App zuerst stoppen und ihren Boot-/Watchdogschutz beibehalten. Fehlerstand privat sichern. Alte App mit ihren unveränderten eigenen Optionen und `/data` wieder verwenden. Falls diese beschädigt sind, die ursprünglichen privaten Daten/Optionen bzw. das originale HA-Backup auf **die alte Identität** zurückspielen.

Beide Apps verwenden dieselben Share-Pfade. Vor einem Rückweg prüfen, ob die neue App seit dem finalen Snapshot Positionen/Mapping/Kandidaten verändert hat. Neuere gültige kompatible Daten nicht blind durch ältere Snapshots überschreiben. Ein alter Positionswert ist keine aktuelle Messung. Erst nach Prüfung alte App allein starten, Identitäten und HomeKit-Bezüge vergleichen und dann ihre ursprünglichen Betriebsflags wiederherstellen. Die neue App bleibt gestoppt.

## English summary

3.1.0 adds the separate `d2ha_bridge` HA identity and an offline private transfer helper. The complete legacy 3.0 app remains unchanged for rollback. Existing MQTT unique/device/entity IDs, topics, options, private paths, mappings and HomeKit links stay compatible. Keep the same HA repository entry/installation source; never run both bridges against the same home. Create and verify a current complete HA backup, stop/protect the old app, export actual options/private data, validate/stage offline, install the new app stopped, transfer through authorized interfaces and then start only the new app. Disabled discovery does not prevent MQTT commands. Keep the old app stopped for rollback; do not reset discovery, initialize an empty existing home, uninstall automatically or re-pair HomeKit. Live migration acceptance is still pending.

Sources: [HA app configuration](https://developers.home-assistant.io/docs/apps/configuration/), [Supervisor app/options/backup endpoints](https://developers.home-assistant.io/docs/api/supervisor/endpoints/).
