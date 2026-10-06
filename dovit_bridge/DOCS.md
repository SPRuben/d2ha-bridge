# Installation und Einrichtung / Installation and configuration

Die öffentliche Dovit Bridge ist eine experimentelle Home-Assistant-App auf Basis des 2.2-Laufzeitcodes. Sie verbindet einen kompatiblen Dovit-TCP/XML-Zugang mit MQTT. Die Verbindungskette lautet:

**Dovit TCP/XML → Dovit Bridge → MQTT-Broker → HA-MQTT-Integration → optional HomeKit Bridge**

Eine Installation dieses öffentlichen Repositorys auf einem neuen HA-System und die Kompatibilität mit anderen Dovit-Anlagen sind noch nicht live bestätigt. Die [Versionshinweise](CHANGELOG.md) unterscheiden die früheren Laufzeittests von diesem öffentlichen Paket.

**Nutzungsbedingungen:** Unveränderte nichtkommerzielle Nutzung ist kostenlos. Änderungen am Programm oder den Dokumenten und kommerzielle Nutzung benötigen vorher die schriftliche Erlaubnis des Rechteinhabers; erlaubte kommerzielle Nutzung und Vergütung werden separat vereinbart. Eigene Einstellungen und Gerätezuordnungen sind erlaubt und bleiben deine Daten. Die [LICENSE](../LICENSE) ist maßgeblich; eine [deutsche Erläuterung](../LICENCE_DE.md) ist enthalten. Es handelt sich um Source Available mit eigenen Bedingungen, nicht um eine freie Open-Source-Lizenz.

## Deutsch: Voraussetzungen

- Home Assistant OS mit Supervisor, App-Store und Administratorzugang. HA Container unterstützt diesen Installationsweg nicht.
- Architektur `amd64` oder `aarch64`. `armv7` gehört zu älteren Entwicklungsbuilds und wird hier nicht angeboten.
- Erreichbarer Dovit-TCP/XML-Zugang. Port `6060` ist ein Beispiel aus der bisherigen Implementierung; Adresse, Port und Protokoll deiner Anlage prüfen. Es gibt keine Dovit-Benutzername-/Passwortoptionen für zusätzliche Authentifizierung.
- Laufender MQTT-Broker und eine HA-MQTT-Integration, die denselben Broker verwendet. Die Bridge installiert weder den Broker noch die HA-Integration.
- Eigene, geprüfte Zuordnungen oder eine tatsächlich neue Anlage ohne alte Zuordnungen. Niemals die IDs eines anderen Hauses übernehmen.

## Deutsch: App aus dem Repository installieren

1. Bei bestehender Bridge zuerst den Abschnitt **Migration** unten lesen und eigene Daten sichern.
2. In HA **Einstellungen → Apps → App-Store → ⋮ → Repositories** öffnen. Ältere HA-Versionen verwenden die Bezeichnung „Add-ons“.
3. `https://github.com/SPRuben/dovit-bridge` hinzufügen, die Store-Liste aktualisieren, **Dovit Bridge** auswählen und installieren. Das Installationsimage wird aus den Quellen gebaut; keine Dateien per Samba nach `/addons` kopieren.
4. Vor dem Start unter **Konfiguration** die eigene Dovit-Adresse und MQTT-Verbindung eintragen. `127.0.0.1` ist nur der neutrale, nicht eingerichtete Standard. MQTT-Benutzer/Passwort sind leer und müssen bei einem Broker mit Anmeldung ausgefüllt werden.
5. App starten und **Weboberfläche öffnen** wählen. Ingress ist der vorgesehene Zugang; keinen direkten Webport ins Internet freigeben.

## Deutsch: Erster Start ohne Gerätedatei

Das Paket liefert keine aktive Gerätedatei mit. Standardpfad ist `/share/dovit_devices.json`. Fehlt sie oder ist sie ungültig, läuft zunächst ausschließlich der getrennte Wiederherstellungsassistent. Dieser Modus verbindet sich nicht mit Dovit oder MQTT und sendet keine Gerätebefehle.

1. Nur für eine wirklich neue Anlage **Neue Installation vorbereiten** wählen. Die Aktion bereitet eine leere Zuordnung zur Prüfung vor; sie startet keine automatische Suche und stellt keine verlorenen Geräte wieder her.
2. Bei vorhandenen Zuordnungen stattdessen die eigene geprüfte Datei hochladen, ihren JSON-Text einfügen oder eine angebotene eigene Sicherung auswählen.
3. **Prüfen** wählen und die Zusammenfassung mit Gerätenamen/Kategorien lesen. Erst nach dieser Validierung ausdrücklich bestätigen. Eine leere Quelle und Alarmzuordnungen verlangen zusätzliche Zustimmung.
4. Nach erfolgreicher Übernahme die App selbst über HA neu starten. Der Assistent bleibt bis dahin eingeschränkt; es gibt keinen automatischen Neustart.

Eine offene Vormerkung oder ein unlesbares Original kann den sicheren Austausch blockieren. Nicht durch Löschen vorhandener Daten umgehen. Bei Datenverlust zuerst die eigene Sicherung wiederherstellen. Details stehen im [deutschen Benutzerhandbuch](../docs/USER_DE.md).

## Deutsch: Dovit und MQTT einrichten

Die normale Weboberfläche bietet **Geräte**, **Einrichtung** und **Diagnose**. Unter **Einrichtung** Dovit, MQTT, Zuordnungen und Veröffentlichung prüfen. „Weiter“ prüft Eingaben lokal. Speichern gilt nach dem nächsten manuellen Neustart und führt weder Verbindungstests noch Gerätebefehle aus.

Für MQTT gibt es zwei Modi:

| Modus | Verwendung |
| --- | --- |
| `manual` | Eigene Brokeradresse, Port, Benutzer/Passwort, TLS und MQTT-Protokoll. `core-mosquitto` ist die HA-interne Adresse einer installierten Mosquitto-App, keine öffentliche Brokeradresse. |
| `supervisor` | **Home-Assistant-MQTT-Dienst (automatisch)**: Der Supervisor liefert die Verbindung des bereitgestellten MQTT-Dienstes. Es muss tatsächlich ein solcher Dienst vorhanden sein; ohne ihn den manuellen Modus verwenden. |

Beispiel für einen lokalen manuellen Broker, **vor Verwendung alle Platzhalter ersetzen**. `192.0.2.10` und `192.0.2.20` sind Dokumentationsadressen und keine erreichbaren Geräte:

```yaml
dovit_host: "192.0.2.10"
dovit_port: 6060
mqtt_mode: manual
mqtt_host: "192.0.2.20"
mqtt_port: 1883
mqtt_user: "DEIN_MQTT_BENUTZER"
mqtt_pass: "DEIN_MQTT_PASSWORT"
mqtt_tls: false
mqtt_protocol: "3.1.1"
devices_file: "/share/dovit_devices.json"
enable_discovery: false
publish_discovery: false
web_light_control: false
web_device_control: false
cover_position_mode: legacy
alarm_code: ""
```

Im manuellen TLS-Modus müssen Brokerzertifikat und Hostname zur gewählten Adresse passen. MQTT-Zugangsdaten sind unabhängig von einer Dovit-App-Anmeldung. Unter **Einstellungen → Geräte & Dienste** die [MQTT-Integration](https://www.home-assistant.io/integrations/mqtt/) mit demselben Broker einrichten und Discovery prüfen.

Im Web gespeicherte Dovit-/MQTT-/Veröffentlichungseinstellungen liegen privat unter `/data/dovit_setup.json`. Sie haben beim Start Vorrang vor den entsprechenden App-Optionen. Wenn Änderungen in HA scheinbar wirkungslos bleiben, die gespeicherten Web-Einstellungen prüfen. Alarmcode, `devices_file`, automatische Suche, Websteuerungsoptionen und Rollladenmodus bleiben App-Optionen.

## Deutsch: Eigene Geräte zuordnen und an HA melden

**Geräte** zeigt empfangene Zustände und nicht zugeordnete Signale. Dovit-ID und Signalart (`statetype`) gemeinsam anhand deiner eigenen Anlage verifizieren, Kategorie und Name wählen, **Änderung prüfen**, ausdrücklich bestätigen und für den nächsten Start vormerken. Danach selbst neu starten. Eine formal gültige JSON-Datei beweist keine physische Identität.

Unterstützte Zuordnungskategorien sind Lichter, Schalter, Rollläden, Thermostate, Bewegung, Kontakte und Alarme. Binäre Schalter müssen anhand des tatsächlichen Endpunkts und seiner Rückmeldungen geprüft werden. Es wird kein hausbezogener Tatto-/Schalter-Endpunkt mitgeliefert. Rollläden bleiben standardmäßig im `legacy`-Modus Auf/Ab/Stopp; zeitbasierte Positionen benötigen eigene geprüfte Kalibrierung.

| `enable_discovery` | `publish_discovery` | Verhalten |
| --- | --- | --- |
| `false` | `false` | Keine automatische Kandidatensuche und keine Veröffentlichung von Discovery-Konfigurationen. |
| `false` | `true` | Bekannte, benannte Geräte an HA veröffentlichen; keine automatische Kandidatensuche. Empfohlener kontrollierter Einstieg nach eigener Zuordnung. |
| `true` | beliebig | Automatische Licht-/Rollladen-Kandidatensuche und Veröffentlichung, einschließlich des bestehenden Suchverhaltens. Nur bewusst aktivieren. |

Zum kontrollierten Einstieg `enable_discovery: false` beibehalten und nach Prüfung eigener Zuordnungen **bekannte Geräte veröffentlichen** (`publish_discovery: true`) aktivieren, speichern und selbst neu starten. HA sollte danach die MQTT-Entitäten anlegen. MQTT-Verbindung und Veröffentlichung allein beweisen weder vollständige Übernahme noch funktionierende physische Steuerung.

Namen und Bereiche anschließend in HA passend zuweisen. Neue Schalter schlagen bei erster Registrierung `switch.dovit_switch_<ID>` vor; bereits registrierte Entitäten behalten die HA-Registry-ID. Die tatsächliche Entität in HA prüfen, keine vorhandene Registry zur Anpassung an ein Beispiel umbenennen.

`web_light_control` und `web_device_control` sind standardmäßig aus. Sie betreffen optionale bestätigte Tests in der Webseite und sperren nicht die normale MQTT-Steuerung aus HA. Reale Tests erst mit geprüfter Zuordnung, vor Ort und mit Wissen über die Wirkung ausführen; Alarme nicht zum Installationsnachweis betätigen.

## Deutsch: Optional HomeKit

Zuerst die betreffenden Entitäten in HA prüfen. Danach die [HomeKit-Bridge-Integration](https://www.home-assistant.io/integrations/homekit/) einrichten und die tatsächlich vorhandenen gewünschten HA-Entitäten über deren Filter aufnehmen. Die Dovit Bridge erstellt keine separate direkte Apple-Home-Verbindung. Änderungen an HA-Namen/Bereichen oder ein erfolgreicher MQTT-Connect bestätigen keine HomeKit-Übernahme.

## Deutsch: Migration von einer lokalen Bridge

Eine Repository-App erhält ein anderes HA-App-Präfix als eine bisherige lokale App. Sie ist eine separate Installation; ein Update über den Store überträgt nicht automatisch die privaten Daten der alten App.

1. HA-Backup erstellen und die tatsächlichen eigenen Dateien sichern: aktive `/share/dovit_devices.json`, Positionsdaten und benachbarte Zuordnungs-/Sicherungsdateien, HA-App-Optionen sowie private Einrichtung unter `/data/dovit_setup.json` und gegebenenfalls deren Sicherungen. Diese Dateien können Zugangsdaten oder Hausdaten enthalten und gehören nicht auf GitHub.
2. Die alte Bridge stoppen und ihren automatischen Start deaktivieren, bevor die neue Bridge erstmals normal läuft. **Beide Bridges niemals parallel betreiben**: Sie verwenden dieselben Dovit-Endpunkte und MQTT-Topics.
3. Den vorhandenen eigenen `/share`-Pfad bewusst weiterverwenden. Keine leere Neuinstallation über eine bestehende Zuordnung anwenden. Die neue App enthält keine Ersatzzuordnung.
4. Die App-Optionen der neuen Installation gezielt übernehmen. `/data` ist app-spezifisch; Web-Overrides aus der alten App gehen nicht automatisch mit. Eigene Einstellungen vorzugsweise über den neuen Einrichtungsassistenten erneut speichern; eine manuelle Übertragung privater Daten nur nach geprüfter Sicherung und Kenntnis der HA-Datenpfade durchführen.
5. Discovery-Optionen und MQTT-Zugang prüfen, selbst starten und Logs/Diagnose lesen. Erst danach HA-Entitäten prüfen. Das App-Präfix ändert nicht die im Laufzeitcode verwendeten MQTT-Topics/Unique-IDs; eine bestimmte Registry-/HomeKit-Migration ist dennoch nicht live zugesichert.

Bei einem Rollback zuerst die neue Bridge stoppen. Die alte Installation mit ihren tatsächlich gesicherten Daten und Optionen wiederherstellen; niemals beide starten. Entfernte Discovery-Entitäten nicht über eine breite MQTT-Wildcard löschen.

## English: Installation

Unchanged noncommercial use is free under the [custom license](../LICENSE). Software/documentation changes and commercial use need prior written permission; commercial use and compensation require a separate agreement. Your configuration and device data are allowed and remain yours. No automatic fee is set.

1. Use Home Assistant OS with Supervisor on `amd64` or `aarch64`. Home Assistant Container does not offer this app-store installation route. Have your own compatible Dovit TCP/XML endpoint and a working MQTT broker ready.
2. Open **Settings → Apps → App store → ⋮ → Repositories**, add `https://github.com/SPRuben/dovit-bridge`, refresh the store, and install **Dovit Bridge**. Older HA versions call apps “add-ons”.
3. Before starting, set your real Dovit host/port and MQTT connection. `127.0.0.1` is an unconfigured Dovit default; MQTT credentials are empty. Manual MQTT mode uses your broker details; optional `supervisor` mode obtains the available HA MQTT service. Configure HA's MQTT integration to use the same broker.
4. Start and open the Ingress web interface. The package includes no active device map. A missing/invalid `/share/dovit_devices.json` starts restricted recovery with no Dovit/MQTT connections.
5. For a genuinely new installation, choose **Neue Installation vorbereiten** (or **Préparer une nouvelle installation** in French), validate the prepared empty mapping, review the summary and explicitly consent. For an existing home, upload/paste/select your own backup instead. Empty mappings and alarms require additional consent. Restart manually after applying; the recovery process remains restricted until then.
6. In the normal UI, configure your own Dovit and MQTT settings, identify your own device IDs plus signal types, review mapping changes and restart manually when required. Saved web settings in `/data/dovit_setup.json` override their corresponding app options on the next start.
7. Keep `enable_discovery: false` for a controlled setup. Once your known mappings are checked, set `publish_discovery: true`, save and restart to publish them through MQTT discovery. Confirm the resulting entities in HA. An MQTT connection is not evidence that entities were imported or commands work.
8. Optionally select those verified HA entities in Home Assistant's HomeKit Bridge integration. Web control defaults are off; HA/MQTT control is separate and may operate real devices.

When migrating a local app, back up the real `/share` maps, private `/data` setup and app options. The repository app has a different HA app identity and its private data is separate. Stop the old app and disable its automatic start before starting the public app; never run both together. Preserve your existing map rather than initializing it empty. Re-enter or carefully transfer your own private setup, accounting for its precedence over app options. The public repository installation, physical compatibility and HomeKit acceptance still require live verification on your system.

## Troubleshooting / Fehlerdiagnose

| Symptom | Check / Prüfen |
| --- | --- |
| Recovery assistant after start | Own mapping missing/invalid; validate and restore it, or explicitly initialize only a new installation. Restart manually afterwards. |
| Dovit disconnected | Real Dovit host, TCP/XML port and network reachability; neutral/example hosts are not your device. |
| MQTT disconnected | Correct mode, broker service/host, port, credentials, TLS certificate and protocol. |
| Connected, but no HA entities | Same broker in HA MQTT integration, checked named mapping and discovery publication enabled; restart after saved configuration changes. |
| Changed app option has no effect | Corresponding saved web override in `/data/dovit_setup.json` may take precedence. |
| HA entity unavailable | Dovit/MQTT transport and fresh state; a historical received value does not prove a current connection. |

Use the integrated **Handbücher / Manuels** and **Diagnose / Diagnostic** views. When reporting a problem, share only redacted logs and configuration excerpts. Never publish MQTT passwords, alarm codes, private setup files or household mappings.
