# Alarm state after a restart

The TCP connection and the availability of a current alarm state are separate facts. The bridge requires fresh numeric readings for both configured alarm partitions, or a current trigger event, before it announces the combined alarm as available. MQTT reconnection alone does not discard current TCP-session readings; a new TCP session does.

On the affected installation, a read-only connection received ordinary telemetry but no alarm partition values during a 20-second observation with no outgoing data. A separate 30-second connection using the existing six NUL heartbeats also received ordinary telemetry and no alarm values. Neither observation restarted the running bridge or sent alarm commands. The owner reports that merely opening the official app does not resolve the symptom, whereas a later alarm state change does. This supports a missing initial-state explanation; it does not establish a documented status-query command or prove all server versions behave alike.

The bridge deliberately does not substitute a retained/stored alarm state as a current reading and does not automatically arm or disarm an alarm to initialize it. Until fresh evidence arrives, Home Assistant and its HomeKit Bridge may show the alarm as unavailable. This limitation remains unresolved in this candidate.

For diagnosis, check the server and MQTT connections and whether the log contains fresh numeric readings for **both** configured alarm partitions after the connection starts. Do not post alarm codes, raw authentication frames or household mappings. A TCP/MQTT connection alone does not prove an alarm state or a physical command succeeded.

A reliable correction requires a verified read-only initial-state source or a documented read-only server query. No guessed XML command has been sent to the installation, and no alarm operation has been performed by the agent.

See [MQTT alarm availability](https://www.home-assistant.io/integrations/alarm_control_panel.mqtt/) and [HA HomeKit Bridge](https://www.home-assistant.io/integrations/homekit/).
