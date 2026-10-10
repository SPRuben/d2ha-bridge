# Benutzerhandbuch - D2HA Bridge

**Experimentelle Testversion 3.1.1: Fehler sind möglich; Nutzung auf eigene Gefahr. Kompatibilität mit jeder Dovit-Serverversion ist unbekannt. Nach einem Neustart kann der Alarm mangels frischer Serverwerte in HA/HomeKit nicht verfügbar bleiben. Diese Einschränkung ist noch nicht behoben.**

Unveränderte nichtkommerzielle Nutzung ist kostenlos. Änderungen am Programm
oder seinen Dokumenten sowie kommerzielle Nutzung brauchen vorher schriftliche
Erlaubnis; kommerzielle Bedingungen werden separat vereinbart. Eigene Einstellungen
und Gerätezuordnungen sind erlaubt und bleiben deine Daten.
Lizenz: https://github.com/SPRuben/d2ha-bridge/blob/main/LICENSE

D2HA Bridge is an independent, unofficial community project.

## Einstieg: Geräte, Einrichtung und Diagnose

Die drei Hauptbereiche haben unterschiedliche Aufgaben:

- **Geräte:** empfangene Zustände lesen, Signale beobachten und zuordnen sowie vorhandene Geräte bearbeiten.
- **Einrichtung:** Dovit- und MQTT-Einstellungen in vier Schritten vorbereiten und für den nächsten manuellen Neustart speichern.
- **Diagnose:** die laufende Verbindung prüfen und unter **Erweitert · JSON-Zuordnungen** die aktive Gerätedatei bearbeiten.

Fehlt die Gerätedatei oder ist sie ungültig, erscheint stattdessen der getrennte
Wiederherstellungs-Assistent. Nach einem Datenverlust zuerst die eigene Sicherung
wiederherstellen; „Neue Installation vorbereiten“ ist nur für eine tatsächlich
neue Anlage gedacht. Nach der Wiederherstellung selbst neu starten.

„Weiter“ prüft Eingaben nur lokal. Speichern startet weder Verbindungstests noch
die Bridge neu und sendet keine Gerätebefehle. Eine gespeicherte Einstellung
oder eine MQTT-Verbindung bestätigt keine Übernahme der Geräte in HA/HomeKit.
Der Einrichtungsassistent aktiviert keine Tests und ändert keine Alarmcodes.

## Orientierung und erster Schritt

Eine gültige, leere Gerätedatei ist keine beschädigte Einrichtung. Sind noch
keine Hausgeräte zugeordnet, bietet **Geräte** einen Einstieg zur **Einrichtung**
und zur Schritt-für-Schritt-Anleitung. Eine Systemuhr allein ist noch kein
zugeordnetes Hausgerät. Fehlen nur wegen eines Such- oder Kategorienfilters
Treffer, den Filter prüfen statt eine neue Anlage anzulegen.

Geräteübersicht: mit dem Filter Lichter die Namen und Beispielzustände der Lichtgeräte vergleichen.

Unter **Diagnose → Einrichtung und Verbindungen** stehen Dovit, die aktuelle
MQTT-Verbindung, vorhandene Zuordnungen und die aktivierte HA-Veröffentlichung
getrennt. Diese Übersicht liest den laufenden Zustand; sie prüft nicht deine
ungespeicherten oder vorgemerkten Eingaben und verändert keine Optionen.
Simulierte, fehlende oder alte Statuswerte sind kein erfolgreicher
Verbindungsnachweis. HA und Apple Home immer getrennt kontrollieren.

Diagnose: Verbindungen, Zuordnungen und Veröffentlichung getrennt lesen, bevor du ein Verbindungsproblem eingrenzt.

Unter **Geräte → Nicht zugeordnete Signale** öffnet **Gerät zuordnen** direkt
den Zuordnungsdialog. Bekannte Geräte behalten das Zahnrad **Gerät verwalten**.
Technische Textänderungen liegen nicht in einem zweiten Gerätebereich, sondern
unter **Diagnose → Erweitert · JSON-Zuordnungen**. Mit **Zurück zu den Geräten**
kehrst du von dort zur Geräteansicht zurück; ein ungespeicherter JSON-Textentwurf
bleibt beim Ansichtswechsel erhalten.

## Schritt für Schritt: von der Installation zum bearbeiteten Gerät

Diese Schritte gelten für den aktuellen Laufzeitstand. Eine ältere Installation kann
andere Funktionen oder Beschriftungen haben. Beispieladressen und Zugangsdaten
sind Platzhalter. Vor Updates die tatsächlichen eigenen Daten und Optionen sichern.

### 1. Voraussetzungen prüfen

Die Verbindung läuft so: Dovit TCP/XML > D2HA Bridge > MQTT-Broker >
Home Assistant MQTT-Integration > optional HomeKit Bridge.

- Eine funktionierende Dovit-Anlage mit erreichbarem TCP/XML-Zugang; beispielsweise Port 6060; den tatsächlichen Port deiner Anlage prüfen. Nicht jeder Dovit-Zugang ist damit nachgewiesen kompatibel.
- Home Assistant mit Apps-Unterstützung, beispielsweise Home Assistant OS, und Administratorzugang. HA Container bietet diese App-Installation nicht.
- Ein laufender MQTT-Broker, beispielsweise die Mosquitto-App, und gültige MQTT-Zugangsdaten. Der Einrichtungsassistent installiert keinen Broker.
- Die MQTT-Integration in HA muss mit demselben Broker verbunden sein und MQTT Discovery verwenden.
- Die Bridge muss Dovit und den Broker im lokalen Netz erreichen können. Stabile IP-Adressen sind hilfreich.
- Eine eigene Gerätedatei mit geprüften IDs und Signalarten oder ein ausdrücklich neuer, leerer Start.
- Für Apple Home zusätzlich die HA-Integration HomeKit Bridge; sie ist für die D2HA Bridge selbst nicht nötig.

Die **Geräte-ID** bezeichnet die Dovit-ID, die **Signalart (Statetype)** den
technischen Typ des gemeldeten Werts. Beide bilden zusammen einen Endpunkt.
Eine ID allein beschreibt noch nicht, ob es ein Licht, eine Temperatur oder
ein Alarmzustand ist. In JSON bleiben technische Schlüssel wie `statetype`
unverändert. Gerätedateien aus einem anderen Haus niemals einfach übernehmen.
Dovit-, MQTT- und Vorschauports nicht ins Internet freigeben.

### 2. App installieren und MQTT vorbereiten

1. Bei einer bestehenden Installation zuerst HA und die aktive Gerätedatei sichern. Die tatsächlichen Dateien vor einem Austausch sichern, nicht nur die lokale Entwicklungskopie.
2. Unter Einstellungen > Apps > App-Store > Menü > Repositories https://github.com/SPRuben/d2ha-bridge hinzufügen. Ältere HA-Versionen nennen Apps „Add-ons“.
3. Die Store-Liste aktualisieren, D2HA Bridge auswählen und installieren. Öffentliche Architekturen: amd64/aarch64. Eine bisherige lokale Bridge vorher stoppen; beide niemals parallel betreiben. Ihre privaten /data-Einstellungen werden nicht automatisch in die neue Repository-App übertragen.
4. MQTT-Broker starten und einen gültigen, für MQTT geeigneten Benutzer einrichten. Platzhalter wie `mqtt-user` sind keine zugesicherten Zugangsdaten.
5. Unter Einstellungen > Geräte & Dienste die MQTT-Integration einrichten oder ihre Verbindung prüfen. Broker und Integration sind zwei unterschiedliche Bausteine.

### 3. Basisoptionen vor dem Start festlegen

Einstellungen > Apps > D2HA Bridge > Konfiguration öffnen. Hier bleiben
insbesondere `devices_file`, `enable_discovery`, reale Webtests, Rollladenmodus
und Alarmoptionen. Diese Optionen gehören nicht in die Geräte-JSON oder die
HA-`configuration.yaml`; der Web-Assistent ändert sie nicht.

Dovit, MQTT und `publish_discovery` kannst du danach unter **Einrichtung**
vorbereiten. Bereits gespeicherte Web-Einstellungen in `/data/dovit_setup.json`
haben nach Neustart Vorrang vor den entsprechenden App-Optionen. Ein anderer
Wert in der HA-App allein überschreibt sie daher nicht. Vorhandene Einstellungen
gezielt prüfen, nicht durch das folgende manuelle Beispiel ersetzen:

```yaml
dovit_host: "192.0.2.10"
dovit_port: 6060
mqtt_mode: "manual"
mqtt_host: "core-mosquitto"
mqtt_port: 1883
mqtt_user: "DEIN_MQTT_BENUTZER"
mqtt_pass: "DEIN_MQTT_PASSWORT"
mqtt_tls: false
mqtt_protocol: "3.1.1"
devices_file: "/share/dovit_devices.json"
enable_discovery: false
publish_discovery: true
web_light_control: false
web_device_control: false
cover_position_mode: "legacy"
alarm_code: ""
```

| Option | Was du eintragen beziehungsweise beachten musst |
| --- | --- |
| dovit_host / dovit_port | Adresse und TCP/XML-Port deiner Dovit-Anlage; die Beispiel-IP ist nicht automatisch deine. |
| mqtt_mode | `manual` für eigene Brokerangaben; `supervisor` ist der technische Wert für **Home-Assistant-MQTT-Dienst (automatisch)**. Keine ungefragte Umstellung einer Bestandsinstallation. |
| mqtt_host / mqtt_port / mqtt_user / mqtt_pass | Angaben für den manuellen Modus; MQTT-Zugangsdaten, nicht die Dovit-App-Anmeldung. |
| mqtt_tls / mqtt_protocol | Im manuellen Modus TLS und unterstütztes MQTT-Protokoll bewusst wählen; TLS prüft Zertifikat und Hostnamen. |
| devices_file | Pfad der aktiven, persistenten Gerätedatei; Standard `/share/dovit_devices.json`. |
| enable_discovery | Automatische Licht-/Rollladen-Kandidatensuche mit Veröffentlichung; bleibt im Web-Assistenten unverändert. Für einen kontrollierten neuen Einstieg ausgeschaltet lassen. |
| publish_discovery | Bereits zugeordnete, benannte Geräte an HA melden; auch im Web-Assistenten wählbar. `enable_discovery: true` veröffentlicht ebenfalls. |
| web_light_control / web_device_control | Optionale reale Tests in der Webseite; zunächst aus. Diese Schalter sperren nicht die normale MQTT-Steuerung aus HA/HomeKit. |
| cover_position_mode | `legacy` für Auf/Ab/Stopp. `timed` erst mit geprüfter, gerätespezifischer Kalibrierung; keine automatische Positionserkennung. |
| alarm_code | Nur bei eingerichteter Alarmfunktion nach deren Anleitung setzen; ist kein Dovit- oder MQTT-Passwort. |

Es gibt keine App-Optionen für Dovit-Benutzername oder Dovit-Passwort.
Wenn deine Anlage zusätzliche Authentifizierung verlangt, deren Unterstützung
zuerst klären; MQTT-Zugangsdaten lösen das nicht.

### 4. Gerätedatei bereitstellen oder wiederherstellen

Das öffentliche Paket liefert keine aktive Gerätedatei mit. Der Dovit-Standard
127.0.0.1 und die leeren MQTT-Zugangsdaten müssen vor normalem Betrieb eingerichtet
werden. 192.0.2.10 im Beispiel ist eine Dokumentationsadresse, kein echter Zugang.

1. Bei vorhandenen Zuordnungen die eigene geprüfte JSON-Datei am konfigurierten Pfad bereitstellen, beispielsweise im HA-share-Verzeichnis per Samba.
2. Nur bei einer wirklich neuen Anlage ohne frühere Zuordnungen im Wiederherstellungsassistenten „Neue Installation vorbereiten“ wählen. Das bereitet nur einen leeren Entwurf vor; prüfen, leere Zuordnung zusätzlich bestätigen und anschließend selbst neu starten. Alternativ kann die folgende leere Datei als bewusster Ausgangspunkt dienen. Sie repariert keine verlorenen Zuordnungen.
3. App-Optionen speichern und D2HA Bridge starten. Zunächst Logs lesen, nicht sofort Geräte steuern.

```json
{
  "lights": {},
  "shutters": {},
  "thermostats": {},
  "motions": {},
  "contacts": {},
  "alarms": {}
}
```

Fehlt die Datei oder ist sie ungültig, startet nur der getrennte
Wiederherstellungs-Assistent: Datei hochladen, Text einfügen oder eine Sicherung
auswählen, prüfen, Geräteübersicht lesen und ausdrücklich bestätigen.
Alarmzuordnungen und eine leere Quelle verlangen zusätzliche Zustimmung.
Der Assistent baut keine Dovit-/MQTT-Verbindung auf und steuert keine Geräte.
Offene Vormerkungen können die Wiederherstellung blockieren. Danach selbst
neu starten. Im normalen Betrieb ist dies kein JSON-Importknopf.

Wiederherstellung: die passende eigene Quelle auswählen und prüfen; die Übernahme folgt erst nach der Geräteübersicht und deiner Bestätigung.

### 5. Webseite öffnen und in vier Schritten einrichten

1. In der App unter Informationen „In der Seitenleiste anzeigen“ aktivieren; anschließend im HA-Menü D2HA Bridge öffnen. Alternativ „Weboberfläche öffnen“ verwenden.
2. Deutsch oder Français wählen. Unter **Handbücher** findest du diese Anleitung auch ohne Internet.
3. **Einrichtung** öffnen. Der Assistent lädt die gespeicherten Einstellungen in einen lokalen Entwurf. Die Rückmeldung **Aktuelle Verbindung · nur lesen** beschreibt weiterhin die laufende Bridge, nicht diesen Entwurf.

| Schritt | Was du tust |
| --- | --- |
| **1 · Dovit** | Host/IP und TCP-Port deiner Anlage prüfen. **Weiter** prüft Pflichtfelder lokal, ohne einen Verbindungstest. |
| **2 · MQTT** | **Home-Assistant-MQTT-Dienst (automatisch)** nur wählen, wenn HA diesen Dienst bereitstellt. Für einen externen Broker oder ohne diesen Dienst **Manuell** wählen und eigene Zugangsdaten eintragen. |
| **3 · Zuordnungen** | Mit **Zu den Geräten** vorhandene Zuordnungen prüfen oder ergänzen. Danach wieder **Einrichtung** öffnen; der lokale Einstellungsentwurf bleibt beim Ansichtswechsel erhalten. Geräteänderungen haben ihren eigenen Prüf-/Vormerkablauf. |
| **4 · Veröffentlichung** | Deine Auswahl `publish_discovery`, die hier unveränderte Option `enable_discovery` und das geplante Ergebnis getrennt lesen. Zusammenfassung prüfen, ausdrücklich bestätigen und **Für nächsten Neustart speichern** wählen. |

Schritt 1 · Dovit: Adresse und Port in den lokalen Einstellungsentwurf eintragen.

Schritt 2 · MQTT: den passenden Verbindungsmodus wählen; eigene Brokerangaben gehören in den manuellen Modus.

Schritt 4 · Veröffentlichung: Auswahl und Zusammenfassung prüfen, bevor du die Einstellungen für den nächsten Neustart speicherst.

Im automatischen MQTT-Modus liest die Bridge Dienstverbindung und Zugangsdaten
über den Home Assistant Supervisor erst beim nächsten Start. Servicepasswörter
werden nie im Formular angezeigt. Bei Dienstfehlern gibt es keinen automatischen
Rückfall auf manuelle Zugangsdaten. Nach geänderten Servicezugangsdaten selbst
neu starten. Im manuellen Modus behält ein leeres neues Passwortfeld das bereits
gespeicherte Passwort.

Die Veröffentlichung ist vorgesehen, wenn `publish_discovery` **oder**
`enable_discovery` aktiv ist. Die automatische Suche bleibt im Assistenten
unverändert; eine abgewählte Veröffentlichung ist daher nicht immer „alles aus“.
Eine unbekannte Einstellung ist keine bestätigte Deaktivierung. Keine dieser
Angaben bestätigt eine erfolgreiche Übernahme durch Home Assistant.

Speichern betrifft gemeinsam die Assistenten-Einstellungen, nicht automatisch
einen Geräteentwurf. Nach der Speicherung die Bridge bewusst manuell neu
starten. Erst danach unter **Diagnose** Dovit, MQTT und Veröffentlichung prüfen
und die erwarteten Geräte in HA kontrollieren. Ein grüner Dovit-Status beweist
keine MQTT-Verbindung; ein MQTT-Status beweist keine korrekten HA/HomeKit-Geräte.
Empfangszeitpunkte mitlesen: gespeicherte alte Werte sind keine neue Messung.

**Einstellungen neu lesen** verwirft einen lokalen Entwurf nach Rückfrage.
Bei unklarer Speicherantwort zuerst neu lesen, nicht blind erneut speichern.
Beschädigte Web-Einstellungen verlangen eine zusätzliche
Wiederherstellungsbestätigung; die Originaldatei wird zuvor gesichert.
Diese privaten Sicherungen können Zugangsdaten enthalten und dürfen nicht
öffentlich geteilt werden.

Ist die Einrichtungsdatei nicht lesbar oder größer als 1 MiB, bleibt beim Start
die Einrichtungsseite erreichbar. Sie zeigt ausdrücklich nur Basiseinstellungen;
gespeicherte Zugangsdaten sind unbekannt und Speichern bleibt gesperrt.
Die Originaldatei erhalten, Zugriffsrechte oder Dateigröße außerhalb der Oberfläche
klären und eine passende private Sicherung verwenden. Danach selbst neu starten.
Bis dahin startet die Bridge keine Dovit- oder MQTT-Verbindung.

Die Seite ist für Administratoren vorgesehen. Die lokale Vorschau ist eine
Simulation und kein Nachweis einer Hausverbindung; Speichern betrifft dort
nur isolierte Testdateien. Keine Alarmanlage nur für die Einrichtung auslösen.

### 6. Ein nicht zugeordnetes Signal einem Gerät zuordnen

Beispiel: Ein Licht im Büro soll als „Büro Licht“ zugeordnet werden.

1. Unter **Geräte → Beobachtung und Diagnose** „Beobachtung starten“ wählen. Das filtert den laufenden Empfang ab jetzt; es startet keinen Wireshark-Mitschnitt.
2. Nur dieses Licht vor Ort am bekannten Schalter ein- und ausschalten. Andere gleichzeitig aktive Signale beachten.
3. Unter **Geräte → Nicht zugeordnete Signale** ID, **Signalart (Statetype)**, Rohwerte und Empfangszeiten vergleichen. Wiederholungen helfen, beweisen aber allein noch keine Zuordnung.
4. Am passenden Signal direkt **Gerät zuordnen** wählen. Bei einem automatisch abgeleiteten TODO-Gerät dagegen das Zahnrad **Gerät verwalten**, dann **Bearbeiten** öffnen; auch solche Zuordnungen müssen geprüft werden.
5. Kategorie Licht und einen verständlichen Namen wählen. ID und Signalart anhand der Beobachtung prüfen, nicht raten.
6. Änderung prüfen, Vorschau lesen und bestätigen. Anschließend für den nächsten Start vormerken.
7. Die D2HA Bridge bewusst neu starten. Vor Übernahme wird die bisherige Gerätedatei gesichert und erneut geprüft.
8. Seite neu laden: Das Licht muss unter den bekannten Geräten erscheinen. Mit publish_discovery ein zusätzlich in HA unter MQTT kontrollieren.

Zuordnung prüfen: die betroffenen Geräte, Kategorien und Namen in der lesbaren Übersicht kontrollieren, bevor du der Übernahme zustimmst.

Eine Vormerkung ist noch nicht die aktive Konfiguration. Es ist jeweils eine
Änderung vorgemerkt; grafischer und JSON-Editor teilen sie. Vor der nächsten
Änderung erst übernehmen und kontrollieren oder den Entwurf verwerfen.
Verwerfen verändert die aktive Konfiguration nicht.

Bei Thermostaten Solltemperatur, Isttemperatur und Heizmodus separat identifizieren.
Unterstützt werden nur Heizen/Aus; ein Temperaturwechsel aktiviert nicht automatisch
Heizen. Bei Rollläden Status- und Befehls-Statetype prüfen.
Bewegungs- und Kontaktmelder nur anhand bestätigter Signale zuordnen.
Die Alarmrollen Bewegungsmelder und Kontakte sind je einmal verfügbar; vergebene
Rollen bleiben deaktiviert sichtbar. Alarm-Endpunkte niemals aus fremden Beispielen
übernehmen, bestehende Alarmzuordnungen bleiben geschützt.

### 7. Vorhandene Geräte bearbeiten oder entfernen

1. Unter **Geräte → Bekannte Geräte** das Gerät suchen und über das Zahnrad **Gerät verwalten** öffnen.
2. Bearbeiten wählen und beispielsweise „Büro Licht“ in „Büro Deckenlicht“ umbenennen. Für eine reine Umbenennung ID und Kategorie unverändert lassen.
3. Änderung prüfen, bestätigen und für den nächsten Start vormerken.
4. Bridge neu starten, Webseite neu laden und Namen sowie Status in HA kontrollieren.

Eine reine Namensänderung erhält die Bridge-Identität; HA/HomeKit können eigene
Namensüberschreibungen behalten. Räume werden nicht automatisch mit umbenannt.
Ein ID- oder Kategorienwechsel ist dagegen ein Identitätswechsel und benötigt
zusätzliche Bestätigung; Automationen und HomeKit-Zuordnungen können betroffen sein.

„Zuordnung entfernen“ löscht nur den Bridge-Eintrag, nicht das Dovit-Gerät.
Warnung lesen, ausdrücklich bestätigen und den Neustartablauf beachten.
Alte HA-Entitäten können bei deaktivierter automatischer Discovery bestehen bleiben:
publish_discovery allein bereinigt sie nicht. Nicht unüberlegt enable_discovery
einschalten, denn dies aktiviert zugleich die Kandidatensuche und Veröffentlichung.

### 8. Optional testen und JSON verstehen

Reale Webtests erst vor Ort aktivieren: web_light_control für Licht,
web_device_control für Rollläden/Thermostate. Optionen speichern und Bridge
neu starten. „Gerät verwalten“ bietet dann die zulässigen Tests mit Bestätigung.
Fahrweg freihalten; vor Richtungswechsel stoppen. Tests werden nicht automatisch
rückgängig gemacht. „Übertragen“ ist nicht „physisch ausgeführt“; Rückmeldung
separat prüfen und bei Zeitüberschreitung nicht blind wiederholen. Alarmtests
werden in dieser Geräteverwaltung nicht angeboten.

Unter **Diagnose → Erweitert · JSON-Zuordnungen** zeigt **Erweitert · JSON**
dieselbe aktive Gerätedatei wie die grafische Ansicht, nicht eine Beispieldatei.
Für Anfänger zuerst einen Namen unter **Geräte** grafisch ändern und nach dessen
Übernahme die passende Stelle im JSON ansehen. Für direkte Textänderungen:

1. Den aktiven Text bearbeiten und **Änderung prüfen** wählen. Syntax, doppelte Schlüssel, Werte und Endpunktkonflikte werden geprüft.
2. Die lesbare Änderungsliste und bei Bedarf **Technische Änderungsdetails** kontrollieren. Erst nach Prüfung bestätigen; Entfernen oder Wechsel einer Identität verlangt zusätzliche Zustimmung.
3. **Für nächsten Start vormerken** wählen, selbst neu starten und das Ergebnis unter **Geräte** und in HA kontrollieren.

JSON-Prüfung: die betroffenen Geräte und Änderungen in der lesbaren Liste kontrollieren; danach bestätigen und vormerken.

**Zurück zu den Geräten** verlässt den JSON-Bereich, ohne den lokalen Textentwurf
zu verwerfen. Die Rückkehr erfolgt über **Diagnose → Erweitert · JSON-Zuordnungen**.
Neuladen mit ungespeichertem Text verlangt eine Rückfrage. Nach jeder Textänderung
erneut prüfen. **Werkzeuge** enthält Laden und Formatieren; auch danach erneut
prüfen. Keine IDs aus dem Tutorial kopieren und keine Spezial-/Alarmfelder durch
vereinfachte Beispiele ersetzen. Der Wiederherstellungs-Upload ist kein
Importknopf im normalen JSON-Editor. Grafischer und JSON-Editor teilen dieselbe
Geräte-Vormerkung; die Assistenten-Einstellungen bleiben davon getrennt.

### 9. HA, HomeKit und Sicherungen abschließen

1. In HA die MQTT-Entitäten prüfen und passende Bereiche zuweisen. Kategorie, Name und tatsächlicher Status müssen stimmen.
2. Erst danach die gewünschten Entitäten gezielt in die HomeKit Bridge aufnehmen. Eine HA-Bereichszuordnung ist keine Zusicherung derselben Raumzuordnung in Apple Home.
3. In Apple Home Namen, Räume und Status kontrollieren. Bestehende HomeKit-Konfiguration nicht durch ein Tutorial-Beispiel ersetzen.
4. HA-Backup erstellen und prüfen, ob die aktive Datei sowie der Ordner dovit_device_backups tatsächlich enthalten sind. Die Geräte-JSON zusätzlich separat exportieren beziehungsweise kopieren.
5. Nach größeren Änderungen zusätzlich cover_position_file sichern, falls zeitbasierte Rollläden verwendet werden; geschätzte Positionen sind keine gemessenen Werte.

Offizielle HomeKit-Anleitung: https://www.home-assistant.io/integrations/homekit/
Die Bridge gibt keine automatische Zusage, dass jede HA-Sicherung die Gerätedatei
enthält. Wiederherstellung vor einem Notfall anhand einer sicheren Kopie prüfen.

### 10. Wenn etwas nicht funktioniert

| Beobachtung | Zuerst prüfen |
| --- | --- |
| Nur Wiederherstellungsseite | devices_file, Dateiformat und eigene Sicherung prüfen; keine verlorene Einrichtung durch eine leere Datei ersetzen. |
| Dovit nicht verbunden | Host, Port, Netz und Logs; keine Dovit-Anmeldedaten in MQTT-Felder schreiben. |
| Webseite live, aber keine HA-Geräte | MQTT-Broker, MQTT-Integration, Discovery-Optionen, aktive benannte Zuordnungen. |
| Änderung noch nicht sichtbar | Nur vorgemerkt? Bridge neu gestartet? Logs auf Konflikte prüfen und Webseite neu laden. |
| Gerätetest fehlt | Passende Web-Steueroption und Neustart; unbekannte/geschützte Geräte sind nicht frei steuerbar. |
| Befehl übertragen, keine Wirkung | Status und Dovit-Endpunkt prüfen; nicht automatisch wiederholen oder IDs erraten. |
| Gelöschtes Gerät noch in HA | Bestehende Discovery-/Zustandsdaten und getrennte Bereinigung beachten; Schalter allein löschen keine Entitäten. |

Für Hilfe Version, betroffene ID/Statetype und einen kurzen Log-Ausschnitt mit
Zeitstempel angeben. Passwörter, Alarmcode und private Hausdaten vorher entfernen.

## Zuordnungsstatus und Wiederherstellung

- **Beobachtet:** Ein Signal wurde empfangen; sein Gerätetyp ist noch unbekannt.
- **Abgeleitet:** Eine `TODO_`-Zuordnung stammt aus der bisherigen Erkennung und
  muss geprüft werden. Die automatische Erkennung wurde nicht neu erfunden.
- **Zugeordnet:** Ein Eintrag steht in der Gerätedatei. Das bestätigt weder die
  physische Identität noch die Ausführung eines Befehls.
- **Simulation:** Testantworten beschreiben nur simulierte Ergebnisse, keine
  reale Bewegung oder Schaltung. Gesendet und passender Status bleiben getrennt.

Eine fehlende oder ungültige Gerätedatei wird nicht mehr beim Lesen automatisch
leer angelegt. Statt des normalen Betriebs startet ein eingeschränkter
Wiederherstellungs-Assistent ohne Dovit/MQTT-Verbindung oder Gerätesteuerung.
Dort kannst du eine JSON-Datei hochladen, JSON-Text einfügen oder eine der
angezeigten Sicherungen auswählen. Erst prüfen: Die Seite zeigt Geräteanzahlen
und bis zu 200 Namen. Nach deiner Bestätigung wird wiederhergestellt;
Alarmzuordnungen und leere Dateien verlangen eine zusätzliche Bestätigung.
Die Bridge startet danach nicht automatisch in den normalen Betrieb. Du musst
sie selbst neu starten, wenn du bereit bist. Alternativ bleibt das Offline-Werkzeug
`python -m dovit_bridge.recovery` verfügbar. Beschädigte Originale
werden vor dem Austausch separat gesichert. Offene Entwürfe und Backups mit
ausstehenden Löschaktionen blockieren die Wiederherstellung. Nie einfach die
neueste Sicherung übernehmen, besonders bei Alarm-Zuordnungen.

Upload: `.json`, gültiges UTF-8, maximal 256 KiB. Hochgeladene Dateien werden
bytegenau geprüft und übernommen; Bearbeiten des angezeigten Textes erzeugt
stattdessen eine neue Textquelle. Eingefügter Text wird als UTF-8 gespeichert.
Der Assistent ist nur im eingeschränkten Modus verfügbar, nicht als Import im
laufenden normalen Betrieb. Bei unklarer Speicherantwort nicht erneut anwenden;
erst den Status prüfen lassen. Kein automatischer Neustart oder Schaltbefehl.

Beim Löschen oder Wechsel einer Zuordnung kann die bestehende automatische
Discovery zusätzlich die alten, eindeutig zugehörigen MQTT-Zustände löschen.
Aktuell wiederverwendete Zuordnungen bleiben erhalten. Es werden keine
Steuerbefehle, Alarmzustände oder fremden Topics gelöscht. Bei
`publish_discovery` ohne `enable_discovery` findet diese Bereinigung nicht statt.
Bei ausgeschalteter Discovery können alte HA-Entitäten/Zustände deshalb bleiben.
Der Löschauftrag bleibt für Wiederholungen erhalten; erfolgreich eingereiht ist
noch keine bestätigte Broker-Verarbeitung.

Beschädigte Rollladen-Positionsdateien bleiben erhalten; neue Schätzwerte dürfen
sie nicht überschreiben. Bei aktivierter Zeitsteuerung kann dies den Start
blockieren und muss ausdrücklich behoben werden. Prozentwerte bleiben Schätzungen.
Diese Änderungen sind lokal getestet; HA/HomeKit und die sichtbare Oberfläche
prüfen wir gemeinsam später.

## Zweck und Entwicklungsstand

Die Bridge verbindet Dovit über TCP/XML mit MQTT. Home Assistant erstellt daraus
Entitäten und reicht ausgewählte Geräte über seine HomeKit Bridge an Apple Home weiter.
Die neue Oberfläche hilft, Geräte und unbekannte Signale zu beobachten und Zuordnungen
vorzubereiten. Standardmäßig steuert sie keine Geräte. Optional können bereits
zugeordnete Lichter nach ausdrücklicher Bestätigung ein-/ausgeschaltet werden.

### Optionale Lichtsteuerung

In der Vorschau sind Ein/Aus rein simuliert. Im echten Betrieb muss die Option
`web_light_control` bewusst aktiviert werden (Standard: aus). Eine Bestätigung
zeigt Geräte-ID, Statetype und Wert. Keine Steuerung von unbekannten Signalen,
Entwürfen, Rollläden oder Alarmen. Status unterscheidet angefordert, übertragen,
passende Rückmeldung, Fehler und Zeitüberschreitung nach etwa 12 Sekunden.
Eine passende Rückmeldung beweist nicht, dass gerade dieser Befehl die Ursache war.
Ohne Rückmeldung prüfen statt blind erneut senden. Keine automatische Wiederholung
und keine Übertragung nach Wiederverbindung. Echte Tests nur vor Ort und mit Freigabe.

Diese Anleitung beschreibt den aktuellen Laufzeitstand. Vor Updates eigene Daten sichern;
die tatsächlich installierte Version in HA prüfen. Die historischen Abschnitte
bewahren frühere Versionshinweise und ersetzen nicht den aktuellen Einrichtungsablauf.

## Öffnen und Sprache

Der vorgesehene Zugang in HA ist die Dovit-App und „Weboberfläche öffnen“
(Ingress) oder der aktivierte Menüeintrag. Die öffentliche Repository-Installation
und ihre Live-Abnahme auf einem neuen HA-System bleiben unbestätigt.
Die lokale Vorschau unter `http://127.0.0.1:8097/` läuft nur, solange der
Vorschauprozess gestartet ist. Ihre Daten sind simuliert, Dovit ist nicht verbunden,
und Geräteänderungen werden nur in temporären Testdateien vorgemerkt.

Oben wählst du **Deutsch** oder **Français**. Die Wahl wird im jeweiligen Browser
gespeichert, sofern dessen Datenschutz-Einstellungen das erlauben. Beim ersten
Besuch wird Französisch bei französischer Browsersprache gewählt, sonst Deutsch.
Ein Wechsel verändert keine Geräte, Formulareingaben, Rohwerte oder MQTT-Themen.
Gerätenamen werden nicht automatisch übersetzt. Zeiten nutzen die Browser-Zeitzone.

## Handbücher in der Oberfläche

Über **Handbücher** im Kopfbereich öffnest du diese Anleitung direkt in der Seite.
Die Auswahl enthält Deutsch, Französisch und das Entwicklerhandbuch auf Deutsch.
Ein Inhaltsverzeichnis führt zu den Abschnitten. Mit „Schließen“ oder Escape
kehrst du zur unveränderten vorherigen Ansicht zurück. Die Texte sind in der Bridge
enthalten: Internet ist nicht nötig, die laufende Bridge muss jedoch erreichbar sein.
Die Hilfe öffnet zunächst das Benutzerhandbuch der aktuell gewählten Sprache.

## Geräte und Ereignisse

Suche nach Name oder ID und filtere nach Kategorie. Eine Gerätekarte zeigt empfangene
Werte, Geräte-ID, Statetype, Zeit und Meldungsanzahl. ID und Statetype bilden gemeinsam
einen Datenpunkt. Ein Thermostat hat normalerweise mehrere davon.

- **Erstmeldung:** erster Empfang in diesem Bridge-Lauf, kein bewiesener Wechsel.
- **Änderung:** Wert unterscheidet sich von der zuvor empfangenen Meldung.
- **Wiederholt:** gleicher Wert; standardmäßig aus der Ereignisliste ausgeblendet.
- **Archiviert:** früher unbekanntes Signal, seit diesem Start noch nicht empfangen.

Karten werden bei Änderungen kurz hervorgehoben. Numerisch gleichwertige Werte wie
`1` und `1.0` zählen als Wiederholung. Rohwerte werden bewusst nicht pauschal als
„offen“ oder „geschlossen“ interpretiert. Der tatsächliche Ursprung (Schalter,
Dovit-App oder Automation) lässt sich aus einem Status allein nicht sicher erkennen.

„Oberfläche erreichbar“ bedeutet nicht automatisch „Dovit verbunden“. Bei einem
Abrufausfall bleiben letzte Werte sichtbar und können veraltet sein.

## Ein Gerät identifizieren

1. Unter **Geräte → Beobachtung und Diagnose** „Beobachtung starten“ drücken. Die Anzeige filtert auf Meldungen ab jetzt.
2. Einen gefahrlos bedienbaren Schalter gezielt betätigen. Bei Rollläden den Fahrweg freihalten.
3. Neue Signale, ID, Statetype und Werte vergleichen. Bei Bedarf wiederholen.
4. Andere gleichzeitig aktive Geräte berücksichtigen; es gibt keine automatische Ursachenzuordnung.
5. „Beobachtung beenden“ zeigt wieder den verfügbaren Verlauf, nicht nur diese Sitzung.

Dieser Modus löscht nichts und startet keine Netzwerkmitschnitte. Er filtert den
bereits laufenden Empfang der Bridge. Nach einem Bridge-Neustart beginnt eine neue
Sitzung. In der statischen Testvorschau kommen keine weiteren Signale hinzu.
Alarmanlage oder Rauchmelder nicht allein zu Identifikationszwecken auslösen.

## Geräte trennen und bearbeiten

Unter **Geräte** zeigt **Bekannte Geräte** konfigurierte Geräte;
**Nicht zugeordnete Signale** zeigt noch nicht zugeordnete ID/Signalart-Paare.
Der technische Begriff für Signalart ist **Statetype**. Ein physisches Gerät
kann mehrere Endpunkte haben. Suche, Kategorie und Beobachtungsfilter wirken
auf beide Bereiche. Konfigurierte TODO-Geräte bleiben bei den bekannten Geräten;
„Abgeleitet“ ist noch kein Nachweis ihrer physischen Identität.

Bekannte Karten haben das Zahnrad **Gerät verwalten**; im Verwaltungsfenster
**Bearbeiten** wählen. Nicht zugeordnete Signale haben direkt **Gerät zuordnen**.
Vorbelegte technische Werte immer prüfen, fehlende Werte nicht erraten.
Licht-Testbuttons Ein/Aus liegen im Verwaltungsfenster und benötigen eine
gesonderte Bestätigung, bevor ein Befehl gesendet wird.
Rollläden und Thermostate haben separate optionale Tests über
`web_device_control`; Alarme bleiben geschützt.

„Zuordnung entfernen“ entfernt nur den Bridge-Eintrag, nicht das physische
Dovit-Gerät. Warnung lesen, Checkbox bestätigen und das Entfernen für den
nächsten Start vormerken. Vor dem Neustart kann die Vormerkung verworfen werden.
Übernahme, Sicherung und Discovery-Bereinigung erfolgen wie bei anderen Änderungen.
Automationen und HomeKit-Zuordnungen können betroffen sein.
Nach neuen Meldungen erscheint der Endpunkt wieder als unbekannt. Er wird nicht
automatisch neu zugeordnet; manuelles Zuordnen bleibt möglich.

| Kategorie | Felder und bestehende Semantik |
| --- | --- |
| Licht / Bewegung | Name, ID, Statetype; Werte ab 0,5 sind aktiv |
| Kontakt | Zusätzlich Tür, Fenster oder Garagentor; keine freie Invertierung |
| Rollladen | 1=Auf, 2=Ab, 0=Stopp; Status- und Befehl-Statetype separat prüfen |
| Thermostat | Sollwert-ID/Statetype, Istwert-ID/Statetype, Heizmodus-ID/Statetype, Temperaturgrenzen und Schrittweite |

Thermostate unterstützen nur Heizen/Aus, kein Kühlen oder Auto. Der geöffnete
Thermostatentwurf verwendet die gewählte ID zunächst als Sollwert-ID; bei einem
Istwertsensor muss diese daher korrigiert werden. Die Rollladenform ist keine
Prozentkalibrierung. Alarmzuordnungen bleiben schreibgeschützt.

„Änderung prüfen“ kontrolliert Pflichtfelder, Wertebereiche und Konflikte mit
bestehenden Endpunkten. Die resultierende Konfiguration erscheint zur Kontrolle.
Eine Feldänderung macht die Prüfung ungültig. Erst nach erneuter Prüfung kann
gespeichert werden. Ein Entwurf beweist nicht, dass die Dovit-Semantik richtig ist.

Nach Bestätigung „Für nächsten Start vormerken“ wählen. Es ist jeweils eine
Änderung vorgemerkt; sie kann vor dem Neustart verworfen werden. Die Bridge
startet nicht automatisch neu und sendet dabei keine Schaltbefehle.

Beim nächsten Bridge-Start wird erneut geprüft, die bisherige JSON-Datei im
Ordner `dovit_device_backups` neben der Geräte-Datei gesichert und überprüft.
Erst danach wird die aktive Datei atomar ersetzt. Bei zwischenzeitlichen
Dateiänderungen bleibt die Vormerkung gesperrt: Log prüfen, verwerfen und neu
erstellen. Nach dem Neustart die Seite neu laden und die Zuordnung kontrollieren.

Reine Namensänderungen erhalten Kategorie, ID und HA-Identität. ID- oder
Kategorienwechsel benötigen eine zusätzliche Bestätigung. Bei aktivierter
Veröffentlichung kann HA eine neue Entität anlegen; Räume, HomeKit-Zuordnungen
und Automationen können neu zugeordnet werden müssen. Die Bereinigung alter
Discovery-Einträge erfolgt nur mit der bestehenden automatischen Discovery,
nicht durch `publish_discovery` allein. Bei deaktivierter Discovery aktualisiert
sich nur die Bridge-Konfiguration; die Übernahme in HA getrennt kontrollieren.
Benutzerdefinierte Namen in HA/HomeKit können Vorrang vor dem Namen aus der Bridge haben.
Wird der Endpunkt eines Rollladens geändert, wird Prozentsteuerung vorsorglich
für diesen Eintrag deaktiviert. Kalibrierwerte bleiben als Referenz erhalten.

## Speicherung und Grenzen

| Daten | Aufbewahrung |
| --- | --- |
| Live-Ereignisse | letzte 500 Meldungen im RAM; Neustart löscht den Verlauf |
| Aktuelle Signale | maximal 2000 ID/Statetype-Paare im RAM |
| Unbekannte Kandidaten | maximal 2000 Paare, jeweils bis zu 20 zuletzt neu beobachtete unterschiedliche Werte |
| Entwürfe | separate Dateien; bisher keine automatische Bereinigung |

Das Kandidatenarchiv speichert alle fünf Sekunden bei Änderungen: erste/letzte
Beobachtung, Meldungsanzahl und Werte. Bei einem abrupten Ausfall können die
jüngsten Daten fehlen; bei Speicherproblemen auch mehr als fünf Sekunden.
Bei Erreichen des Limits werden die ältesten Kandidaten verdrängt.

Üblicher Speicherort ist `/share/dovit_observed_candidates.json`; Entwürfe liegen
unter `/share/dovit_mapping_drafts/`. Beide liegen neben der konfigurierten
`dovit_devices.json`. Die Vorschau verwendet keine permanente Speicherung.

## Fehler und Datenschutz

### Verfügbarkeit in Home Assistant

Nach einer MQTT-Wiederverbindung veröffentlicht die Bridge zuletzt empfangene
Zustände derselben Dovit-Verbindung erneut. Das ist keine neue Messung und kein
erneuter Steuerbefehl. Der Cache liegt nur im Arbeitsspeicher und wird bei einem
Dovit-Verbindungswechsel oder Bridge-Neustart verworfen. Geschätzte
Rollladenpositionen werden dabei nicht automatisch wiederveröffentlicht.

Steuerbefehle bleiben an die beim Empfang vorhandene Dovit-Verbindung gebunden.
Bei einem Verbindungswechsel werden wartende alte Befehle verworfen, auch
zeitgesteuerte Rollladen-Stopps. Bereits gesendete Befehle lassen sich nicht
zurücknehmen. Falls nötig, nach Wiederverbindung einen neuen STOP auslösen;
die Bridge behauptet nicht, dass ein Rollladen bei einem Ausfall angehalten hat.

Nach Installation dieser Version werden Geräte bei unterbrochener
MQTT- oder Dovit-Verbindung als **nicht verfügbar** angezeigt. Das bedeutet nicht
Licht aus, Kontakt geschlossen oder Alarm ausgeschaltet. Der letzte Zustand
kann weiterhin als historische Information vorhanden sein.

Die Hausalarmanlage wartet nach einer neuen Dovit-Verbindung auf aktuelle Daten
beider Partitionen oder ein neu empfangenes Auslöseereignis. Die einzelnen
Alarmzustände und Meldungstexte werden unabhängig freigegeben: Ein neuer Zustand
macht einen alten Meldungstext nicht aktuell. Verfügbarkeit bestätigt weder eine
erfolgreiche Alarm-Code-Prüfung noch die Ausführung eines Steuerbefehls.

Bei normalen Geräten bestätigt Verfügbarkeit die Verbindung zur Bridge/Dovit,
nicht eine neue Messung jedes einzelnen Geräts. HomeKit zeigt den von HA
weitergereichten Status; die konkrete Anzeige muss nach Veröffentlichung geprüft
werden. Die Verfügbarkeit hängt von der tatsächlich installierten Version ab.

- **Archiv beschädigt/gesperrt:** Originaldatei bleibt erhalten. Nicht löschen;
  zuerst sichern und technisch prüfen lassen. Die Bridge kann weiter beobachten.
- **Speicherfehler:** aktuelle Beobachtungen eventuell nur im RAM. Schreibrechte
  und freien Speicher prüfen lassen; spätere Schreibversuche erfolgen automatisch.
- **Verlaufslücke:** der begrenzte Ereignispuffer enthält nicht mehr alle Meldungen.
- **Endpunkt bereits zugeordnet:** ID und Statetype überprüfen; vorhandene Zuordnung nicht blind überschreiben.
- **Anfrage fehlgeschlagen:** Verbindung prüfen und Entwurf erneut validieren.
  Nach unklarer Speicherantwort kann bereits eine Entwurfsdatei existieren.

Die neuen Logs enthalten UTC-Zeitstempel (`Z`), Log-Level und Modulnamen. Die
Weboberfläche verwendet dagegen lokale Browserzeiten. Konfigurierte Geheimnisse
werden maskiert; Status, Namen und Alarmtexte bleiben private Hausdaten.
Logs/Archive vor Weitergabe prüfen. Kurze numerische Alarmcodes können bei der
Maskierung auch gleichlautende Teile legitimer Zahlen oder Zeitstempel verdecken.
Keinen Vorschauport ins Internet freigeben.
## Discovery verstehen: Geräte suchen oder an HA melden?

Die zwei Schalter lösen unterschiedliche Aufgaben. `true` bedeutet **ein**,
`false` bedeutet **aus**. Beide stehen standardmäßig auf `false`.

**Automatisch suchen (`enable_discovery`):** Die Bridge beobachtet Dovit-Signale
und versucht, daraus Licht- und Rollladen-Kandidaten zu erkennen und in der
Geräte-Datei zu speichern. Sie veröffentlicht außerdem die Discovery-Konfiguration
für HA. Das ist eine heuristische Suche, keine sichere Erkennung aller Gerätetypen.
Thermostate und Alarmrollen werden dadurch nicht automatisch vollständig zugeordnet.

**An HA melden (`publish_discovery`):** Ohne automatische Suche veröffentlicht
die Bridge die Discovery-Konfiguration bereits zugeordneter, benannter Geräte.
Diese beschreibt für HA den Gerätetyp, MQTT-Themen und die Verfügbarkeit.
HA kann damit eine neue Entity anlegen oder eine vorhandene aktualisieren.
Gerätenamen, Räume und HomeKit-Zuordnungen werden dadurch nicht automatisch richtig gewählt.

Merksatz: **Suchen verändert mögliche Gerätezuordnungen. Melden beschreibt HA,
wie bereits eingerichtete Geräte eingebunden werden.**

### Welche Kombination brauche ich?

| enable_discovery | publish_discovery | Ergebnis |
| --- | --- | --- |
| false | false | Keine automatische Kandidatensuche und keine erneute Discovery-Veröffentlichung. |
| false | true | Nur bekannte, benannte Geräte an HA melden. Empfehlung nach der Einrichtung. |
| true | false | Automatische Kandidatensuche UND Discovery-Veröffentlichung nach bisherigem Verhalten. |
| true | true | Gleiches umfassendes Verhalten wie bei enable_discovery allein. Keine doppelte Veröffentlichung durch die beiden Schalter. |

Wichtig: `publish_discovery: false` schaltet die Veröffentlichung **nicht** aus,
wenn `enable_discovery: true` ist. Die automatische Suche beinhaltet bereits
die Veröffentlichung.

### Beispiel 1: Meine Geräte sind schon eingerichtet

Du hast zum Beispiel „Büro Licht“ und „Wohnzimmer Thermostat“ richtig zugeordnet.
Nach einem Bridge-Update soll HA ihre Konfiguration erneut erhalten, ohne neue
Kandidaten in die Geräte-Datei aufzunehmen:

```yaml
enable_discovery: false
publish_discovery: true
```

Die vorhandenen MQTT-Themen und eindeutigen IDs bleiben gleich; dadurch ist
die Veröffentlichung keine absichtliche Neuanlage mit neuer Identität.
Sie erfolgt bei MQTT-Verbindung beziehungsweise Wiederverbindung und regelmäßig
im konfigurierten Intervall, standardmäßig alle 300 Sekunden.
Eine neue Zuordnung wird erst berücksichtigt, wenn sie nach dem bestehenden
Speicher-/Neustartablauf in die laufende Gerätekonfiguration übernommen wurde.

### Beispiel 2: Ich suche ein noch nicht zugeordnetes Licht

Du betätigst einen Lichtschalter und möchtest die automatische Kandidatensuche nutzen:

```yaml
enable_discovery: true
publish_discovery: false
```

Wenn das Signal zu den Erkennungsregeln passt, kann ein Kandidat gespeichert
werden. Prüfe anschließend in der Oberfläche die Dovit-ID, den Statetype und
die Zuordnung; gib dem Gerät einen verständlichen Namen. Nicht jedes Signal
wird erkannt, und ein Kandidat ist noch keine bestätigte Zuordnung.
Namen wie `TODO_Light_123` werden standardmäßig nicht an HA veröffentlicht.
Danach für den normalen Betrieb wieder die Kombination aus Beispiel 1 verwenden.
Unbekannte Signale lassen sich auch ohne automatische Suche in der Oberfläche
beobachten und gezielt manuell zuordnen.

### Beispiel 3: Ich möchte keine HA-Konfiguration neu veröffentlichen

```yaml
enable_discovery: false
publish_discovery: false
```

Die bestehenden MQTT-Zustandsmeldungen und Schaltbefehle laufen weiter, sofern
die Verbindungen funktionieren. HA kann bereits gespeicherte Discovery-Daten
weiterverwenden. Die Schalter löschen keine vorhandenen HA-Entities und
halten die HomeKit Bridge nicht an.

### Wo ändere ich das, und was bleibt geschützt?

**`publish_discovery`** kannst du unter **Einrichtung → 4 · Veröffentlichung**
für den nächsten manuellen Neustart speichern. **`enable_discovery`** bleibt
dort unverändert und gehört in die **Konfiguration der D2HA-Bridge-App in HA**.
Die Optionen gehören weder in die Geräte-JSON noch in die HomeKit-Konfiguration.

Gespeicherte Web-Einstellungen haben für `publish_discovery` Vorrang vor dem
entsprechenden App-Wert; diese unter **Einrichtung** prüfen und bewusst ändern.
Nach Änderungen selbst die D2HA Bridge neu starten. Die Zusammenfassung nennt
deinen Veröffentlichungswunsch, die unveränderte automatische Suche und das
geplante Ergebnis getrennt. Sie bestätigt weder eine erfolgreiche Verbindung
noch eine Übernahme durch HA. Die Beispiele erklären Einstellungen, nicht
eine Aufforderung, Geräte oder die Alarmanlage zu Testzwecken zu schalten.

Bei **false / true** werden keine TODO-Geräte veröffentlicht, keine neuen
automatischen Kandidaten gespeichert und keine alten Discovery-Einträge gelöscht.
Entfernte Geräte können deshalb weiterhin in HA sichtbar sein; ihre Bereinigung
ist ein separater Schritt. Auch wird keine Geräte-Datei allein durch die
Veröffentlichung neu geschrieben.

## Geräteübersicht

Bekannte Geräte zeigen zuerst ihren zuletzt gemeldeten Zustand und, soweit
verfügbar, dessen Empfangszeitpunkt in deiner Browser-Zeitzone. Das ist keine
Bestätigung einer neuen Messung oder Befehlsausführung. Dovit-ID, Signalart
(Statetype), Rohwerte und weitere Empfangsdetails stehen unter **Signaldetails**.
**Nicht zugeordnete Signale** behalten ihre Rohwerte sichtbar zur Zuordnung.

1. Bei bekannten Geräten das Zahnrad **Gerät verwalten**, dann **Bearbeiten** öffnen; bei nicht zugeordneten Signalen direkt **Gerät zuordnen** wählen.
2. Name und Gerätetyp prüfen. **Technische Zuordnung** enthält IDs und **Signalart (Statetype)**.
   Bei nicht zugeordneten Signalen ist dieser Bereich bereits geöffnet.
3. **Änderung prüfen** wählen. Erst danach erscheinen Bestätigung und Vormerken.
   Nach jeder Eingabeänderung ist eine erneute Prüfung nötig.
4. Zum Testen **Gerät testen** aufklappen, die Aktion wählen und im folgenden
   Dialog ausdrücklich bestätigen. Das Öffnen eines Dialogs sendet nichts.
5. **Weitere Optionen** enthält das Entfernen der Zuordnung mit eigener Bestätigung.

Unter **Geräte → Beobachtung und Diagnose** stehen Beobachtung und Ereignisverlauf.
Die Beobachtung filtert Anzeigen; sie steuert keine Geräte. Ein aktiver Filter
bleibt auch bei geschlossenem Beobachtungsbereich sichtbar.
Alarme bleiben geschützt; es gibt keine Alarm-Teststeuerung.
Neue Zuordnungen werden weiterhin erst nach dem Bridge-Neustart übernommen.
Die tatsächliche installierte Version und die Übernahme in HA selbst prüfen.

### Neu

Die Verbindungsanzeige ist deutlich hervorgehoben: Grün bedeutet Dovit verbunden,
Orange bedeutet Oberfläche erreichbar, aber Dovit nicht verbunden; Rot bedeutet,
dass die Oberfläche keine aktuellen Daten von der Bridge bekommt.
Dies bestätigt keine MQTT-Verbindung und keine Ausführung eines Gerätebefehls.

### Geräteübersicht und JSON-Editor

Der JSON-Tab lädt die konfigurierte aktive Gerätedatei, nicht eine Beispielkopie.
Die Geräteübersicht zeigt weiter die laufende Konfiguration. Tabwechsel erhalten
deinen Textentwurf. Beim Neuladen mit ungespeichertem Text wird nachgefragt.

1. JSON-Tab öffnen, Namen, IDs oder Zuordnungen bearbeiten.
2. Änderung prüfen. Syntaxfehler zeigen Zeile und Spalte. Doppelte Schlüssel,
   ungültige Werte und Endpunktkonflikte werden abgewiesen.
3. Unter "Werkzeuge" bei Bedarf formatieren und danach erneut prüfen.
4. Änderungen prüfen und bestätigen, bei Löschungen zusätzlich den Identitätswechsel.
5. Für nächsten Start vormerken. Danach die Bridge selbst neu starten.

In dieser Version erscheint die Bestätigung erst nach erfolgreicher
Prüfung. Laden und Formatieren liegen im aufklappbaren Bereich "Werkzeuge";
die technischen Änderungsdetails sind ebenfalls aufklappbar. Nach einer
Textänderung wird die alte Bestätigung ausgeblendet und erneut geprüft.

Vor Übernahme wird die bisherige Datei gesichert. Externe Änderungen seit dem
Laden blockieren das Speichern bzw. die Übernahme. Grafischer und JSON-Editor
teilen dieselbe vorgemerkte Änderung. Diese kann verworfen werden.
Alarm-Zuordnungen, interne Verwaltungsfelder und zusätzliche Spezialfelder
(z. B. Kalibrierung) bleiben geschützt. Freie Alarm-Rollen grafisch zuordnen.
Geänderte Rollladen-Endpunkte werden vorsorglich auf Legacy zurückgesetzt;
die Prüfübersicht nennt sie unter covers_reset_to_legacy.
Maximale Dokumentgröße: 256 KiB. Es werden keine Gerätebefehle gesendet.

### Direktzugriff in Home Assistant

Nach dem Update: Einstellungen > Apps > D2HA Bridge > Informationen öffnen
und „In der Seitenleiste anzeigen“ einschalten. Danach erscheint D2HA Bridge
direkt im Hamburger-Menü. Falls nötig, HA-Seite neu laden.
Der Zugang bleibt Administratoren vorbehalten, da die Oberfläche Geräte steuern
und Konfiguration ändern kann. Keine Änderung der configuration.yaml nötig.

### Gerätetests und Alarm-Partitionen

Die neue App-Option `web_device_control: true` aktiviert Tests für konfigurierte
Rollläden und Thermostate nach einem Bridge-Neustart. Standard ist ausgeschaltet;
`web_light_control` bleibt separat für Lichter. Das Zahnrad öffnet die Tests.
Jeder Befehl benötigt eine Bestätigung. Thermostate erlauben Heizen, Aus und
Solltemperaturen innerhalb der konfigurierten Grenzen und Schrittweite.
Eine Temperaturänderung schaltet nicht automatisch auf Heizen.

Rollladentests senden Auf, Ab oder Stopp für eine vollständige Fahrt, nicht
Prozentpositionen. Vor einem Richtungswechsel stoppen und Rückmeldung abwarten.
Stopp ist auch während eines noch offenen Tests möglich. Die Änderung wird
nicht automatisch zurückgestellt. Übertragen ist keine Ausführungsbestätigung;
eine passende Dovit-Meldung wird gesondert angezeigt. Keine automatischen Wiederholungen.

Bei der Zuordnung gibt es zusätzlich „Alarm Bewegungsmelder“ und „Alarm Kontakte“.
Jede Partition darf nur einmal existieren. Vergebene Rollen bleiben sichtbar,
sind aber mit „bereits zugeordnet“ deaktiviert. Die bestehenden IDs 87 und 88
werden ohne Änderung der Gerätedatei erkannt. Freie Rollen verlangen ID sowie
Status-, Text-, Auslösungs- und Befehls-Statetype aus bestätigten Mitschnitten.
Die Zuordnung wird erst beim Neustart nach Sicherung übernommen.
Bestehende Alarm-Partitionen bleiben geschützt; es gibt keine Alarm-Teststeuerung.

### Neu

Bekannte Geräte sind nach Kategorien gruppiert. Das Zahnrad öffnet die
Geräteverwaltung; unbekannte Endpunkte bleiben separat. Suche, Kategorie und
Beobachtungsmodus filtern weiterhin beide Bereiche.

Unter Uhren erscheint Dovit (ID 39 / ST 111). Gültige Werte wie `15;44` werden als
`15:44` angezeigt. Dies ist die zuletzt empfangene Uhrzeit, keine weiterlaufende
Browser-Uhr. Der Empfangszeitpunkt zeigt, wie alt die Meldung ist. Im Verlauf
bleibt der Rohwert sichtbar. Datum und Zeitzone werden nicht abgeleitet.
Die Uhr ist schreibgeschützt und wird nicht als neue HA-Entität veröffentlicht.

## Binäre Schalter

Im Geräteeditor „Schalter“ auswählen, den eigenen Dovit-Endpunkt prüfen und für
den nächsten Bridge-Start vormerken. Rein fiktives Beispiel: ID 1234, Statetype 0,
Name „Beispielschalter“. Das Beispiel gehört zu keiner Anlage und darf nicht
ungeprüft übernommen werden. ID, Signalart und Bedeutung anhand deiner eigenen
Dovit-Rückmeldungen feststellen; eine Zuordnung aus einem anderen Haus ist ungeeignet.

Bekannte Geräte müssen über MQTT veröffentlicht werden. Neue Schalter schlagen
bei erster Registrierung switch.dovit_switch_<ID> vor; vorhandene Registry-Entitäten
behalten ihre HA-ID. Ein/Aus wird über MQTT angefordert, der Zustand folgt geprüften
binären Dovit-Rückmeldungen. Es gibt keine zusätzlichen Web-Schaltertestknöpfe.
Für HomeKit die tatsächlich angelegte HA-Entität im HomeKit-Bridge-Filter auswählen.
Physische Schaltung, neue HA-Registrierung und HomeKit-Übernahme müssen an der
eigenen Anlage geprüft werden; die öffentliche Installation ist noch nicht live bestätigt.
