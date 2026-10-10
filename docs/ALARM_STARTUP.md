# Alarm state after a restart

The TCP connection and a current alarm state are separate facts. The bridge requires fresh numeric readings for both configured alarm partitions, or a current trigger event, before it announces the combined alarm as available. MQTT reconnection alone does not discard current TCP-session readings; a new TCP session does.

With mapped alarms, each new TCP connection now sends `hisynch-ask`, the read-only initial synchronization used by the official DO.App. It uses the app's default client (`user`, empty PIN, client ID `-1`), requests current states and sends no device-state or alarm command. Existing device control and alarm-code handling remain unchanged. Installations without mapped alarms keep their existing heartbeat-only connection behavior.

The affected server supplied no partition readings in earlier heartbeat-only observations. With the verified synchronization, it supplied both configured partitions. Two further connections using the corrected bridge runtime and its existing parser/availability checks each obtained fresh readings and made the combined alarm available within one second. MQTT publication was isolated in these diagnostic probes and the running HA bridge was unchanged. No alarm operation or physical HomeKit test was performed.

The bridge never substitutes retained/stored alarm state as current and never automatically arms/disarms an alarm to initialize it. If a server requires different authorization, does not support this synchronization, or fails to return valid readings, HA/HomeKit may still show the alarm unavailable. Compatibility with all server/firmware versions is unknown. No retry of physical commands is introduced.

For diagnosis, check the server and MQTT connections and whether the log contains fresh numeric readings for **both** configured alarm partitions after connection. Do not post alarm codes, raw authentication frames or household mappings. A TCP/MQTT connection alone does not prove an alarm state or physical command succeeded.

See [MQTT alarm availability](https://www.home-assistant.io/integrations/alarm_control_panel.mqtt/) and [HA HomeKit Bridge](https://www.home-assistant.io/integrations/homekit/).
