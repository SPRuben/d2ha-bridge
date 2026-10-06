# Entwicklerhandbuch - Dovit Bridge

Dieses Projekt verwendet eigene Source-Available-Nutzungsbedingungen. Änderungen
am Programm, an Dokumenten oder Grafiken benötigen vorher die schriftliche
Erlaubnis des Rechteinhabers, auch für private Änderungen. Kommerzielle Nutzung
benötigt eine separate schriftliche Vereinbarung. Eigene Konfiguration und
Gerätezuordnungen sind erlaubt. Lizenz: https://github.com/SPRuben/dovit-bridge/blob/main/LICENSE

## Produktionsverhalten in 2.2 (eingeführt ab 2.0)

Legacy-MQTT-Rollladenbefehle nutzen `command_statetype` mit Rückfall auf den
Zustandskanal. Sitzungsschutz und Themen bleiben unverändert. Thermostatbefehle
halten nach Schritt- und Ein-Dezimalstellen-Rundung die konfigurierten Grenzen
ein; nicht sicher darstellbare Bereiche werden ohne Versand verweigert.

Nicht lesbare oder über 1 MiB große private Einrichtungsdateien verhindern die
Reparaturseite nicht mehr. Eine begrenzte Leseoperation unterscheidet fehlende
Dateien von Speicherfehlern. Ohne erhaltbares Original bleiben Revision und
Passwortstatus unbekannt, `writable=false`; kein Ersatz, keine Geräteverbindungen.
Kleine beschädigte Dateien behalten den bisherigen bestätigten Backup-/Reparaturweg.

Der MQTT-Dienstresolver verarbeitet abgeschlossene HTTP-Antworten ohne erneuten
Zugriff auf einen geschlossenen Socket. Unvollständige Content-Length-Antworten
werden auch bei gültigem JSON abgelehnt. Echte Loopback-HTTP- und TLS-Tests ergänzen
die bisherigen Stubs, ohne Supervisor, HA oder Dovit anzusprechen.

Das Produktionsimage verwendet weiterhin Python 3.11/Alpine und ausschließlich
`paho-mqtt==2.1.0` aus `requirements.txt`. `.dockerignore` erlaubt nur Laufzeitdateien,
Handbücher und Build-Eingaben; Caches, Tests, private Einstellungen und Backups
bleiben außerhalb des Build-Kontexts. `Dockerfile` ist die maßgebliche Basis,
`build.yaml` nur die erhaltene Kompatibilitätskonfiguration.

Öffentliche Installation und Grenzen: https://github.com/SPRuben/dovit-bridge/blob/main/dovit_bridge/DOCS.md
Laufzeit- und Paketverifikation getrennt betrachten; frühere Tests sind in
dovit_bridge/CHANGELOG.md zusammengefasst. Sie bestätigen keine reale Installation
des öffentlichen Repositorys auf einem neuen HA-System und keine HomeKit-Abnahme.
Öffentliche Metadaten/Defaults weichen vom früheren lokalen 2.2-Paket ab:
experimentell, amd64/aarch64, neutraler Dovit-Host 127.0.0.1 und leere MQTT-Zugangsdaten.
Keine aktive Hauszuordnung wird mitgeliefert.

## Einrichtung und MQTT-Dienst in 2.2

`setup_config.SetupConfig` bietet revisionsgebundene private Web-Einstellungen.
GET `/api/setup` liefert nur manuelle Felder, Passwort-vorhanden und Status;
POST verlangt den bestehenden Peer-/Sitzungstoken-Schutz, Bestätigung und Revision.
Eine pro Prozess geheime HMAC schützt Revisionskennungen vor Passwortverifikation.
Beschädigte Einstellungen benötigen zusätzliche Zustimmung; bytegenaues Backup,
0600-Dateirechte und atomarer Austausch gehen der nächsten Startanwendung voraus.
Keine Schaltbefehle, Credential-Hot-Swaps oder automatischen Neustarts.

`mqtt_service.resolve_mqtt_config` fragt explizit den authentifizierten offiziellen
GET `/services/mqtt` ab (begrenzte Antwort, Timeout, keine Redirects/Fallbacks).
Servicegeheimnisse leben nur im Runtime-Config; `SetupConfig` erhält ausschließlich
die unaufgelöste Konfiguration. Dienste werden mit `services: mqtt:want` deklariert,
ohne zusätzliche breite Supervisor-/Core-API-Rechte. `MqttWrapper` prüft TLS mit
System-CAs und liefert sichere numerische Fehler und zeitgestempelte Zustände.
Manueller Default bleibt migrationssicher. `/data/dovit_setup.json` hat bei Start
Vorrang vor korrespondierenden App-Optionen. Laufzeittests sind kein Nachweis
echter Supervisor-, HA-, HomeKit- oder öffentlicher Repository-Abnahme.

## Wiederherstellung, Klassifizierung und Bereinigung in 2.2

Der Start verweigert fehlende/ungültige aktive Zuordnungen,
bevor Geräteverbindungen gestartet werden, und stellt stattdessen einen eingeschränkten
Wiederherstellungsassistenten bereit. `load_devices` behandelt fehlende Dateien
standardmäßig strikt; eine neue Installation erfordert eine explizite Initialisierung.
`recovery.py` bietet offline Prüfung/Wiederherstellung/Initialisierung mit Bestätigung
des Betreibers, dass der Betrieb gestoppt ist, SHA256-Prüfungen für Ziel und Quelle,
bytegenauer Erhaltung, Schutzprüfungen für Vormerkungen/Bereinigung und atomarer Installation.
Es stellt weder automatisch wieder her noch validiert es physische Dovit-Semantik.

`RecoveryManager` existiert nur im eingeschränkten Startmodus. Eigenständige
Wiederherstellungsassets verwenden relative Ingress-Pfade und die bestehenden
Peer-/Token-Beschränkungen für POST. Die Validierung ist rein lesend, berücksichtigt
nur die neueste Validierung und begrenzt die Eingabe auf 256 KiB. Hochgeladene Bytes,
eingefügter UTF-8-Text und undurchsichtige IDs serverseitiger Backups sind getrennte,
einander ausschließende Quellen. Die Anwendung erfordert übereinstimmende Revision
und Validierungsidentität, explizite Zustimmung sowie zusätzliche Zustimmung für
Alarme oder leere Zuordnungen. Das Original bleibt über die zugrunde liegende
Offline-Wiederherstellungsfunktion erhalten. Normale APIs sind im Wiederherstellungsmodus
gesperrt; Änderungen zur Wiederherstellung sind im Normalmodus nicht verfügbar.
Nach Erfolg bleibt der Prozess bis zu einem Neustart durch den Betreiber eingeschränkt.
Es werden weder Geräteverbindungen, Kandidatenschleife, Befehlssteuerung noch
automatische Wiederholungsversuche gestartet.

DeviceEditor und die unterstützten Schreibpfade von Speicherung/Wiederherstellung
teilen RLocks für aufgelöste Pfade; externe Prozesse werden nicht gesperrt.
Die endgültigen serialisierten vorgemerkten Zuordnungen werden vor der Vormerkung
und erneut vor der Anwendung validiert. Beschädigte Dateien für geschätzte Positionen
werden protokolliert/erhalten und können nicht durch routinemäßiges Speichern
einer Position überschrieben werden.

Snapshots ergänzen `classification` (observed/inferred/confirmed) und Herkunftsangaben.
`confirmed` bedeutet konfiguriert, nicht physische Identität oder Ausführungsbestätigung.
`inferred` entspricht der bestehenden TODO-Namenskonvention. Archivierte Beobachtungen
können keine Live-Herkunft belegen; Routen werden erneut mit der aktuellen Konfiguration
abgeglichen.

Bestehende Legacy-Discovery-Tombstones leeren jetzt kanonische Zustands-Topics
für Nicht-Alarme und Discovery-Konfigurationen; aktuelle Eigentümer sind ausgenommen.
Der reine Veröffentlichungsmodus verarbeitet sie nicht. Tombstones bleiben für
Wiederholungsversuche bei Wiederverbindung/erneuter Veröffentlichung erhalten.
Das Einreihen mit QoS1 ist kein PUBACK; weder breit angelegte Wildcard-Bereinigung
noch das Löschen von Befehls-Topics ist erlaubt. Alarme sind von Zustandsbereinigung ausgenommen; Veröffentlichung allein
löst keine solche Bereinigung aus.

## Version 1.17

Historischer Ursprung dieser Funktionen: App-Name und panel_title sind Dovit Bridge;
slug bleibt local_dovit_bridge. Ingress und der ausschließlich Administratoren
vorbehaltene Zugriff bleiben erhalten. Die Sichtbarkeit in der Seitenleiste ist
eine Supervisor-Benutzereinstellung, kein config.yaml-Schalter: In HA
„In der Seitenleiste anzeigen“ (Show in sidebar) aktivieren. Es wird keine neue
Supervisor-API-Berechtigung angefordert.

Der neue JSON-Tab liest die konfigurierte Gerätedatei über /api/devices.
replace_json-Operationen verwenden die Revisionsprüfungen von DeviceEditor,
die einzige Vormerkungsdatei, erneute Validierung beim Start, verifizierte Backups
und atomare Ersetzung. json_editor.py validiert geänderte Zuordnungen mit der
bestehenden Endpunktvalidierung. Unveränderte Legacy-Zuordnungen bleiben erhalten.
Alarm-/interne/Sonderfelder bleiben geschützt; Löschungen erzeugen
Discovery-Tombstones und unterdrückte Endpunkte. Änderungen an Rollladen-Endpunkten
deaktivieren den zeitgesteuerten Modus; die Zusammenfassung weist explizit darauf hin.

Text ist auf 256 KiB begrenzt; die beiden HTTP-Routen zur Gerätevalidierung und
zum Speichern erlauben eine Anfragehülle von 2 MiB für JSON mit Escape-Sequenzen.
Andere POST-Routen behalten ihre Grenze von 8 KiB. Ingress-Peer-/Session-Prüfungen
bleiben erforderlich. Clients geben keinen Pfad an. Doppelte JSON-Schlüssel und
nicht endliche Zahlen werden serverseitig abgewiesen. Die UI erhält ungespeicherte
Entwürfe beim Tabwechsel und verwirft veraltete Validierungen. Die Live-Anzeige
spiegelt Dovit-Konnektivität und HTTP-Polling wider, nicht den MQTT-Zustand.

Offizielle Konfigurationsreferenz:
https://developers.home-assistant.io/docs/apps/configuration/

## Bestätigte Steuerung und Partitionsrollen

`device_control.py` behandelt nur zugeordnete Rollläden und Thermostate nach
expliziter Aktivierung der neuen Einstellung `web_device_control`.
Der POST-Endpunkt verwendet dieselben Schutzmaßnahmen für Ingress-Peer/Token,
Bestätigung und Anfragegröße. Befehle verwenden stabile UUIDs, ein begrenztes
Befehlsregister, eine Warteschlangenfrist von zwei Sekunden und erneute Prüfungen
von Writer/Zuordnung; keine Wiederholungsversuche. Der Statusabgleich verwendet
den konfigurierten Zustandsendpunkt und den erwarteten numerischen Wert,
bei Rollläden nicht den Befehlsendpunkt. STOP umgeht Belegt-Prüfungen und verwirft
eingereihte Fahrten desselben Rollladens. Tests über den vollständigen Fahrweg
löschen zeitgesteuerte Zielstopps; Tests in Gegenrichtung erfordern zuerst STOP,
wenn eine Bewegung verfolgt wird. Die MQTT-Befehlshandler für Lichter, Rollläden
und Thermostate bleiben unverändert.

`alarm_partitions.py` ermittelt eindeutige `motion`-/`contact`-Rollen aus
`partition_role`, mit Legacy-Fallback für IDs 87/88. Der Editor akzeptiert neue
`alarm_motion`-/`alarm_contact`-Zuordnungen, speichert sie in `alarms`,
weist doppelte Rollen, IDs und Endpunkte ab und wendet sie über den bestehenden
Revisions-, Bestätigungs- und Backup-Ablauf an. Bestehende Alarme können weder
bearbeitet noch gelöscht werden. Der kombinierte Alarm-MQTT-Handler und die
Zustandsaggregation verwenden diese ermittelten IDs. Scharfschalten erfordert
beide Rollen. Alarmbefehle werden nicht über die Web-Test-API bereitgestellt.

## Inventaränderungen in 1.16

`Monitor.configure(..., include_system=True)` ergänzt den rein lesbaren Endpunkt
39/111 im Live-Inventar und in der Vorschau. Temporäre Editorinventare lassen ihn
aus, damit das Entfernen einer Zuordnung diesen Systemendpunkt nicht versehentlich
als nicht zugeordnet erfassen kann. Bestehende explizite Zuordnungen haben Vorrang.
Die Entwurfsvalidierung reserviert 39/111, auch für Rollladen-Befehlsendpunkte.
Es wird weder eine MQTT-Entität noch ein Befehlspfad hinzugefügt.

Die UI gruppiert gefilterte Karten in fester Kategorienreihenfolge.
Die Uhrzeitformatierung akzeptiert nur gültige Werte im Format Stunde;Minute;
Rohwerte bleiben im Ereignisverlauf erhalten. Automatisierte Tests verwenden
synthetische Daten, niemals reale Dovit- oder HA-Befehle.


Aktueller Laufzeitstand: 2.2. Historische Versionsüberschriften kennzeichnen
die Einführung einzelner Funktionen und keine heutige Deployment-Aussage.

## Geräteeditor 1.15

Bekannte Geräte und unbekannte ID/Statetype-Paare werden getrennt gerendert.
`GET /api/devices` liefert editierbare Maps, SHA256-Revision und Pending-Status.
`POST /api/devices/validate|save|cancel` benötigt den bestehenden Session-Token
und den Ingress-Peer. `devices.js` arbeitet nur mit relativen URLs.

Eine Änderung wird neben devices_file als `<stem>.pending.json` vorgemerkt.
Pro Bridge ist genau eine Vormerkung erlaubt. Bestätigungen sind serverseitig
erforderlich. Bei Identitätswechsel ist eine zweite Bestätigung nötig.
Alarme sind nicht editierbar. Die alten Draft-API-Routen bleiben kompatibel.

Das Verwaltungsfenster bündelt Test, Bearbeitung und Entfernen hinter einem
SVG-Schraubendreher mit zugänglicher Beschriftung. Löschen verwendet dieselben
validate/save-Routen mit operation=delete, source, revision und beiden
Bestätigungen. Es entfernt ausschließlich erlaubte bestehende Zuordnungen.
_unassigned_endpoints verhindert automatische Wiederanlage nach einer Löschung,
ohne manuelle Neuzuordnung zu sperren. Es werden keine Dovit-Löschbefehle gesendet.

`DeviceEditor.apply_pending()` läuft vor Erstellung von DovitBridge, MQTT
und TCP. Es validiert erneut gegen den Datei-Hash, sichert die Originalbytes
nach `dovit_device_backups/`, prüft sie und ersetzt die aktive Datei atomar.
Bei Konflikt bleibt das Original erhalten und die Vormerkung zur Prüfung liegen.
Es gibt keinen Hot-Reload und keine Schaltbefehle. Externe gleichzeitige
Schreibzugriffe beim Startup sind nicht unterstützt; ein OS-weites Dateilock
und vollständige Stromausfallsicherheit werden nicht garantiert.

Unbekannte Zusatzfelder bleiben bei gleicher Kategorie erhalten. Ein geänderter
Rollladen-Endpunkt setzt position_mode=legacy, um falsche Kalibrierung zu vermeiden.
Status- und Befehl-Statetype sind separat editierbar.
Bei neuer ID/Kategorie speichert `_removed_discovery` die alte Identität als
Tombstone. Discovery entfernt sie mit retained-Leerpayload (QoS1) bei jedem
Republish/Reconnect, außer die Identität wird wieder verwendet. Bei deaktivierter
Discovery findet keine HA-Aktualisierung statt. Namen behalten ihre Unique-ID.
Automatische Kandidatenerkennung darf bekannte Endpunkte nicht neu klassifizieren.

## Architektur

```text
Dovit TCP/XML -> DovitBridge -> MQTT -> HA MQTT Discovery -> HomeKit Bridge
                      |
                      +-> Monitor -> HTTP Snapshot -> Browser (Polling)
                            |
                            +-> CandidateStore (separate JSON-Datei)
Browser -> Entwurf prüfen/speichern -> separate unveränderliche JSON-Datei
```

Die Lichtsteuerung nutzt denselben send_light-/XML-Pfad wie MQTT. Neu ist
`POST /api/lights/command`, nur nach explizitem Opt-in `web_light_control: true`
und mit Ingress-Peer-Prüfung, Session-Token, confirm=true und UUID request_id.
Vorschau nutzt ausschließlich Simulation. Unbekannte IDs und Nicht-Lichter sind
gesperrt. Bis zu 1000 Request-IDs pro Prozess werden zur Deduplizierung behalten;
danach verweigert die Steuerung neue Requests. Es gibt keine persistente Queue.
Die asynchrone Übergabe hat zwei Sekunden Gültigkeit und ist an den aktuellen
TCP-Writer gebunden. Status beobachtet passende Werte bis zu zwölf Sekunden,
ohne kausale Ausführungsbestätigung zu behaupten. Ein offener Befehl sperrt weitere
Webbefehle kurzzeitig. MQTT bleibt unabhängig. Nur die letzten 30 Webbefehle sind
im Snapshot sichtbar. Noch keine allgemeine Befehlschronik in der Ereignisliste.
Der Webserver besitzt keine Route für aktive Zuordnungen, Neustarts oder Discovery.
Keine zusätzlichen Frontend-Abhängigkeiten oder CDN-Anfragen.

| Modul | Verantwortung |
| --- | --- |
| `main.py` | Logging, Konfiguration, Instanzen, Hintergrundaufgaben, Dovit-Reconnect |
| `bridge.py` | MQTT-Befehle, XML-Dispatch, Zustände, Discovery, bestehende Gerätemodelle |
| `dovit_tcp.py` | asyncio-TCP, NUL-Keepalive, Transportfehler, Empfangsstatistik |
| `mqtt_client.py` | Paho Callback API v2, Publish/Subscribe-/Callback-Fehler |
| `storage.py` | Geräte- und Positionsdateien; bestehende Schreibpfade |
| `web_monitor.py` | In-Memory-Beobachtungen, Endpunktindex, HTTP-API, IP-Prüfung |
| `candidate_store.py` | Kandidatenarchiv laden/prüfen/atomar ersetzen |
| `mapping_drafts.py` | Neue Zuordnungen validieren und separat speichern |
| `logging_setup.py` | UTC, Level, Modul, einzeilige Ausgabe, Secret-Maskierung |
| `web/i18n.js` | DE/FR-Katalog, dynamische Muster, Sprachauswahl |
| `web/app.js` | Polling, Filter, Beobachtungssitzung, Entwurfsdialog |

## Threads und Lebenszyklus

Dovit-Empfang läuft auf dem asyncio-Loop, MQTT-Callbacks auf dem Paho-Netzwerkthread.
Der HTTP-Server verwendet `ThreadingHTTPServer`. Ein `RLock` schützt die
Beobachtungssammlungen; das Schreiben des Kandidatenarchivs erfolgt per
`asyncio.to_thread`, nach Erstellung eines Snapshots unter dem Lock.

Die Bridge erfasst valide `hidv-state`-Werte vor dem normalen Zustandsdispatch.
Der Parserhelper existiert weiterhin, der Hauptpfad parst XML aber inline.
Das Protokoll wird nicht durch vermutete Gerätetypen erweitert.

Discovery-/Statusaufgaben werden vor MQTT-Abschluss abgebrochen und abgewartet.
Der gesamte Prozess garantiert weiterhin keinen vollständigen Abschluss-Flush
aller Hintergrundaufgaben/Daemon-Threads bei SIGTERM. Der Webserver
hat keinen separaten Prozess und kein Request-Rate-Limit. HA-Ingress, Containerbau
und Langzeitlast sind vor einem Release gesondert zu prüfen.

## API

Ingress erwartet den tatsächlichen TCP-Peer `172.30.32.2`. Andere Quellen werden
abgewiesen; `X-Forwarded-For` wird nicht zur Authentifizierung verwendet.
Lokal erlaubt ausschließlich der Preview-Aufruf explizit `127.0.0.1`.

| Route | Zweck |
| --- | --- |
| `GET /api/snapshot` | Session, Sequenz, Dovit-Verbindung, Geräte, Zustände, Ereignisse, Speicherstatus, Draft-Token |
| `GET /`, `/index.html` | HTML |
| `GET /app.js`, `/i18n.js`, `/style.css`, `/mapping.css` | explizit freigegebene Assets |
| `POST /api/drafts/validate` | validierte Vorschau, keine Dateiänderung |
| `POST /api/drafts/save` | neue separate Entwurfsdatei, `active: false` |

POST benötigt `Content-Type: application/json`, 1 bis 8192 Bytes und den
Header `X-Dovit-Token` mit dem Token der aktuellen Prozesssession. Ingress
authentifiziert den Benutzer; das Token ist kein unabhängiges Benutzerkonto.
Es gibt noch keine zusätzliche Benutzer-/Administratorrollenprüfung im Editor.
Token nicht protokollieren. HTTP-Access-Logging ist deshalb deaktiviert.
Die API setzt kein CORS-Allow-Origin. Frontend nutzt relative URLs für Ingress.
Responses dürfen nicht gecacht werden; Assets/Snapshot nutzen eine lokale CSP.

Ein Snapshot enthält private Hausdaten. Niemals den Ingress-Port im Router freigeben.
`host_network: true` bleibt aus dem bisherigen Add-on erhalten: vor Deployment
Portkonflikte auf 8099 und die tatsächliche Ingress-Quelladresse kontrollieren.
HA-Referenz: https://developers.home-assistant.io/docs/apps/presentation/#ingress

## Beobachtungsmodell

Endpunktschlüssel: `device_id:statetype`; Geräte-UID: `category:id`.
Thermostate gruppieren target/current/mode. Alarmgeräte gruppieren state/text/trigger.
Ein Endpunkt kann bestehende Mehrfachzuordnungen haben; neue Entwürfe blockieren
jedoch belegte Endpunkte. Identitätswechsel im neuen Editor erfordern Bestätigung.

`seq` steigt nur für neue eingehende Meldungen innerhalb einer Session.
`first`, `change`, `repeat` unterscheiden Empfang von Änderung. Numerisch gleiche
Strings gelten als gleich. `historical` hat `seq=0` und erscheint nicht in Live-Events.
Frontend-Beobachtung setzt eine lokale Sequenzgrenze, ohne Serverdaten zu löschen.
Status allein verrät nicht den Auslöser. Ein gesendeter MQTT-Befehl ist keine
physische Bestätigung. Command-intent-Events sind im Monitor noch nicht implementiert.

Limits: 500 Live-Ereignisse, 2000 aktuelle Paare, 2000 archivierte Kandidaten,
20 unterschiedliche Werte pro Kandidat, 160 Zeichen pro maskiertem Wert.
Aktuelle und archivierte Zustände können zusammen mehr als 2000 Listeneinträge haben.
Kandidaten werden nur aktualisiert, solange der Endpunkt unbekannt ist.

## Persistenz

Aktive Zuordnungen: konfigurierter `devices_file`, normalerweise
`/share/dovit_devices.json`. Dazu benachbart:

- `dovit_observed_candidates.json`: Schema `{version: 1, candidates: [...]}`.
- `dovit_mapping_drafts/`: pro Speichern neue UUID-/UTC-basierte Datei.
- Rollladenpositionen bleiben über `cover_position_file` separat konfiguriert.

CandidateStore schreibt nur bei Änderung, alle fünf Sekunden. Ablauf: JSON-Snapshot,
temporäre Datei im selben Verzeichnis, Flush/fsync, `os.replace`. Die vorherige
Datei bleibt bei fehlgeschlagenem Replace erhalten. Kein Directory-fsync oder
vollständiges Crash-/Stromausfallversprechen; kein garantierter Shutdown-Flush.
Ein Writer pro Archiv ist vorausgesetzt. Beschädigte/zu große/unlesbare Archive
blockieren weitere Schreibvorgänge und bleiben unangetastet.

Entwürfe sind exklusive neue Dateien (`open('x')`), keine atomare Aktivierung.
Ein Prozessabbruch kann eine unvollständige Entwurfsdatei hinterlassen. Das aktive
Mapping bleibt trotzdem unverändert. Es gibt noch keinen Draft-Reader, keine
Bereinigung und keine Prüfung auf Konflikte mit anderen Entwürfen.
Die bisherigen `storage.py`-Schreibpfade sind nicht generell atomar; diese
Eigenschaft darf nicht vom Kandidatenarchiv auf alle Dateien übertragen werden.

## Entwurfsschema und Validierung

Beispiel POST-Body (keine Dovit-Aktion):

```json
{"category":"contacts","name":"Testfenster","id":999,"statetype":0,"device_class":"window"}
```

Serverergebnis:

```json
{"draft":{"category":"contacts","device_id":"999","configuration":{"name":"Testfenster","statetype":0,"device_class":"window"}},"active":false}
```

Die separate Legacy-Entwurfs-API erlaubt lights, switches, motions, contacts,
shutters, thermostats. Alarmzuordnungen verwenden den geschützten Geräteeditor.
IDs/Statetypes: Integer ohne Boolean, 0 bis 2147483647. Name: 1-80 Zeichen,
keine Steuerzeichen. Kontakte: door/window/garage_door. Thermostate benötigen
getrennte current/mode-Endpunkte; Target-ID entspricht dem Schlüssel.
Grenzen: -50 <= min_temp < max_temp <= 100, Schritt > 0 und <= Spanne;
NaN/Infinity werden verworfen. Keine Feldänderung kann eine frühere erfolgreiche
Frontend-Validierung weiterverwenden. Bei save wird serverseitig erneut validiert.

Die separate Entwurfs-API aktiviert ihre Vorschläge nicht selbst. Der aktuelle
Geräteeditor prüft Änderungen, merkt sie mit Bestätigung vor und übernimmt sie
nach erneuter Validierung beim nächsten manuellen Start mit geprüftem Backup
und atomarem Austausch. Eine gespeicherte Legacy-Entwurfsdatei ersetzt diesen
Prüf-/Vormerkungsablauf nicht.

## Internationalisierung

`i18n.js` wird vor `app.js` geladen. Schlüssel sind stabile ursprüngliche UI-Texte,
Werte Paare `[Deutsch, Französisch]`. Dynamische Texte verwenden begrenzte Muster.
`setText` speichert den Originaltext in `data-i18n`; `translateStatic` aktualisiert
nur den Textknoten, nicht enthaltene Formularfelder. Attribute verwenden
`data-i18n-placeholder` und `data-i18n-label`. Gerätenamen, JSON, IDs und Rohwerte
explizit als nicht übersetzbar behandeln (`node(..., undefined, true)`).

Sprache in `localStorage['dovit.language']`, Fallback Browsersprache fr, sonst de.
Storage-Fehler dürfen die Oberfläche nicht blockieren. `html.lang`, Titel und
Datumsformat folgen der Auswahl; Zeitzone bleibt die des Browsers. Eine Auswahl
im offenen Dialog darf weder Eingaben löschen noch als Feldänderung gelten.
Backend-Validierungsnachrichten werden an der UI-Grenze übersetzt. Neue Meldungen
müssen im Katalog/Muster ergänzt und mit Tests abgedeckt werden. Technische Logs
bleiben sprachunabhängig und nutzen UTC.

## Lokal entwickeln und testen

### Integrierte Handbücher

`docs/` im Repository ist die redaktionelle Quelle. Die drei Handbücher werden
bytegleich nach `dovit_bridge/dovit_bridge/manuals/` kopiert und durch Docker-COPY
ausgeliefert. Nach Änderungen beide Kopien synchronisieren. `test_manuals.py`
prüft Byte-Gleichheit gegen die Quellen, damit ausgelieferte Texte nicht veralten.
Die 16 festen lokalen JPEG-Abbildungen unter `docs/images/` werden nach
`dovit_bridge/dovit_bridge/manuals/images/` kopiert; Quellen und ausgelieferte
Bilddateien müssen ebenfalls bytegleich sein.

Der Server erlaubt ausschließlich `/manuals/USER_DE.md`, `/manuals/USER_FR.md`
und `/manuals/DEVELOPER.md` sowie die 16 fest freigegebenen JPEG-Pfade unter
`/manuals/images/` hinter derselben Ingress-IP-Prüfung. Keine frei wählbaren Pfade.
`help.js` rendert einen bewusst begrenzten Markdown-Umfang:
Überschriften, Absätze, Listen, Tabellen, Fett-/Codeauszeichnung und Codeblöcke.
HTML wird ausschließlich als Text eingefügt. Ausschließlich die 16 festen lokalen
JPEGs aus der Bild-Freigabeliste werden als Abbildungen geladen; andere Bildpfade
und externe Inhalte bleiben Text. Normale URLs bleiben Text; kein allgemeiner
Markdown-Linkrenderer.
Der Hilfedialog verwendet ein eigenes Inhaltsverzeichnis, ohne den Ingress-Pfad
oder die Beobachtungssitzung zu verändern. Dokumentinhalt behält seine Sprache,
unabhängig von der Auswahl der UI-Sprache. Neue Rendererfunktionen gegen
HTML-Injection und die drei realen Texte testen (`node tests/test_help.cjs`).

### Befehle

Vom App-Verzeichnis `dovit_bridge` im Repository:

```powershell
python -m unittest discover -s tests -q
python -m compileall -q dovit_bridge tests
node --check dovit_bridge/web/app.js
node --check dovit_bridge/web/i18n.js
node tests/test_i18n.cjs
python preview_monitor.py
```

Tests verwenden temporäre Dateien, Mocks und Loopback-TCP, keine echten Geräte.
Dateitests können an Windows-Sandboxrechten scheitern; nicht durch Änderungen
am Produkt umgehen, sondern kontrolliert mit den erforderlichen Rechten testen.
Frontend hat keine Node-Laufzeitabhängigkeit im Container; Node dient hier Tests.
Vorschau lauscht nur auf 127.0.0.1:8097 und verwendet temporäre Editor-Testdateien.
`python -m dovit_bridge.main` dagegen kann reale Dovit-/MQTT-Verbindungen öffnen:
nicht als UI-Test starten.

Manuelle Abnahme auf dem eigenen System: beide Sprachen, Mobilansicht, offene
Formulare beim Sprachwechsel, Wiederverbindung, Archivhinweise, Validierungsfehler,
Ingress-Präfix und unautorisierte direkte Zugriffe. Test- oder Vorschauprüfungen
ersetzen keine Live-Abnahme der öffentlichen Repository-Installation.

## Release, Migration und Wiederherstellung

Öffentliche Versionsnummer in config.yaml und Release-Hinweise konsistent halten.
Vor Updates die tatsächlichen HA-Dateien, App-Optionen, private /data-Einrichtung
und aktiven /share-Geräte-/Positions-/Archivdateien sichern. Demo-Mappings niemals
über die produktiven Zuordnungen kopieren. Nur amd64/aarch64 werden öffentlich
angeboten; historische armv7-Tests erweitern diese Plattformangabe nicht.

Ein lokales App-Präfix unterscheidet sich von der Repository-App. /share ist
bewusst weiterzuverwenden; /data ist app-spezifisch und wird nicht automatisch
migriert. Gespeicherte Web-Overrides haben Vorrang vor den App-Optionen. Zuerst
die alte Bridge stoppen und deren Autostart deaktivieren; niemals beide betreiben.
Für einen Rollback zuerst die neue Bridge stoppen und dann tatsächlich gesicherte
Daten/Optionen der alten Installation wiederherstellen. Keine Geräte oder Alarme
lediglich zur Bestätigung eines Installationsschritts betätigen.

## Binary switches and entity IDs in 2.2

The optional switches map is read at startup without changing the existing
six-value reload_maps API. Discovery uses default_entity_id with the value
switch.dovit_switch_<id> on first registration; unique IDs and MQTT topics remain
stable, and HA retains existing registry identities. Commands and states use
dovit/switch/<id>/set and dovit/switch/<id>/state. Strict binary telemetry,
nonoptimistic state, transport availability, same-session replay,
retained-command rejection and scoped removal follow existing lifecycle rules.
Graphical/JSON editing and recovery support switches. No additional web switch
control buttons are added; command intent arrives through MQTT.

A fictional example endpoint is ID 1234 / ST 0 named “Example switch”. It is
not an actual household mapping and must not be copied into another installation
without verifying that installation's endpoint and command semantics. The public
package deliberately contains no active mapping or house-specific switch fragment.
Live new-entity registration, physical command and HomeKit acceptance remain open.
