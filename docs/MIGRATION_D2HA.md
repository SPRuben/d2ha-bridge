# D2HA Bridge 3.0.0 — Phase 1 migration

This release changes the public product name and artwork. It deliberately keeps the existing HA/MQTT/storage identities. Phase 2 is not included.

## Update an existing installation

1. Create a full HA backup before updating. Save the actual app options, private `/data/dovit_setup.json` and its backups, your active `/share/dovit_devices.json`, `/share/dovit_cover_positions.json`, pending editor changes and relevant adjacent backups. Keep credentials/household data private. Record current entity IDs and HomeKit associations.
2. Keep the same app and installation source. Existing repository users keep `https://github.com/SPRuben/dovit-bridge` in HA after GitHub renames it. GitHub redirects the old URL; changing HA's configured URL can change the repository prefix and create another app. New users use `https://github.com/SPRuben/d2ha-bridge`.
3. Existing local installations remain local. The current app directory/package stays `dovit_bridge/` and `slug: local_dovit_bridge` stays unchanged. Installing from GitHub instead is a separate migration of app-specific `/data`, even with the same slug. This rebrand does not transfer local data into a different installation source.
4. When the update is available, stop the existing app, update that same app and start it manually. Keep its existing options and private files. Never start two bridges against the same Dovit/MQTT installation.
5. Check stored options/overrides, logs, Dovit and MQTT connections, Ingress title, original entity/device IDs and absence of duplicates. Confirm existing dashboards/automations and HomeKit accessories still refer to the same HA entities. Perform physical controls only deliberately, on site and with permission. No re-pairing, discovery reset or registry rename is required by this branding change.

Shared mappings must not be replaced by the empty public seed. A new recovery page in an existing home is a reason to verify/restore the actual configured path, not initialize an empty home. Web overrides still take precedence over corresponding app options.

The maintainer reports the existing local 3.0 installation is running. Independent update-in-place, new-installation, HA entity/automation, Supervisor/Ingress, LAN/hardware and HomeKit acceptance remains pending. A retained slug alone is not proof of live migration success.

## Sidebar still shows the former name

The app configuration sets both `name` and `panel_title` to **D2HA Bridge**. The sidebar title does not require a new slug. Reload the app store metadata, turn **Show in sidebar** off and on for the same installed app, then reload the browser. This re-registers the existing Ingress panel without reinstalling the app or changing MQTT identities. If the former title remains, inspect the installed app metadata and HA/Supervisor logs before considering further action. Do not change the slug or edit HA registry/private storage to fix a display label.

## Preserved compatibility surfaces

| Surface | Kept values / reason |
| --- | --- |
| HA app | `local_dovit_bridge`; existing repository/local prefix must also remain stable |
| MQTT node/device | `dovit_bridge` discovery node and existing `device.identifiers` |
| MQTT entity IDs | `dovit_light_*`, `dovit_switch_*`, `dovit_cover_*`, `dovit_motion_*`, `dovit_contact_*`, `dovit_alarm_*`, `dovit_climate_*`; existing HA registry/HomeKit references |
| First switch suggestion | `switch.dovit_switch_<ID>`; existing HA entity IDs remain untouched |
| MQTT transport | All `dovit/...` state, command, position and availability topics, discovery topics and command formats |
| Options | `dovit_host`, `dovit_port` and all other schema keys/defaults |
| Files | `/share/dovit_devices.json`, `/share/dovit_cover_positions.json`, `/data/options.json`, `/data/dovit_setup.json`, existing pending/draft/backup names and JSON keys |
| Code/package | `dovit_bridge`, `DovitBridge`, `X-Dovit-Token`, Dovit client/protocol names; stable imports/API and no cosmetic refactor |
| External system | Dovit hardware, TCP/XML, host/port, signal types, default device names; compatibility terminology |

Discovery device display name becomes **D2HA Bridge** and manufacturer becomes **Independent community project**. Identifiers, entity names from your mapping, topics and discovery behavior are unchanged. HA may retain a user-customized device display name. No MQTT publication is performed by local migration/testing.

Historical tutorial images retain the former Dovit Bridge branding because they are actual 2.0 captures with simulated data. Captions identify this history; no image is represented as a tested 3.0.0 live installation.

## Rollback

Stop the new version first. Restore the same app's previous source/image plus the actual backed-up options/private data if needed. Preserve the original mapping and registry. Never run two copies together or delete retained discovery/state topics with a broad wildcard. Do not delete/recreate the old GitHub repository name: that would break GitHub redirects.

## Not included

No `d2ha_bridge` app slug, persistent-file migration, topic/unique-ID migration, HA registry edit or HomeKit reset. No change to Dovit TCP/XML, device assignments, supported device types or command/state logic.

Sources: [GitHub repository rename](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository), [Supervisor repository identity implementation](https://github.com/home-assistant/supervisor/blob/main/supervisor/store/repository.py), [HA app configuration](https://developers.home-assistant.io/docs/apps/configuration/).
