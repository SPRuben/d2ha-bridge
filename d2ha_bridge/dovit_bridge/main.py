# -*- coding: utf-8 -*-
import logging
LOGGER = logging.getLogger(__name__)

import asyncio
import time
import os

from .logging_setup import setup_logging

from .config import load_config
from .storage import load_devices, ensure_cover_positions_file
from .recovery import validate_recovery_document
from .bridge import DovitBridge
from .web_monitor import Monitor, start_monitor
from .recovery_service import RecoveryManager
from .candidate_store import CandidateStore
from .light_control import LightControl
from .device_control import DeviceControl
from .device_editor import DeviceEditor
from .setup_config import SetupConfig, apply_setup_overrides
from .mqtt_service import resolve_mqtt_config, MqttServiceError

async def main():
    setup_logging()
    cfg = load_config()
    setup_logging((cfg.mqtt_user, cfg.mqtt_pass, cfg.alarm_code, os.environ.get('SUPERVISOR_TOKEN', '')))
    try:
        cfg = apply_setup_overrides(cfg)
    except ValueError as error:
        LOGGER.error('Setup overrides invalid; original preserved; no transports started')
        await run_setup_only(cfg, 'setup_storage_error' if str(error) == 'setup_storage_error' else 'invalid_configuration')
        return
    setup_logging((cfg.mqtt_user, cfg.mqtt_pass, cfg.alarm_code, os.environ.get('SUPERVISOR_TOKEN', '')))
    LOGGER.info("D2HA Bridge starting version=3.1.0 timestamps=UTC")
    LOGGER.info('%s', f"Config: enable_discovery={cfg.enable_discovery}")
    LOGGER.info('%s', f"DEBUG: DEVICES_FILE={cfg.devices_file}")
    LOGGER.info('%s', f"DEBUG: COVER_POSITION_MODE={cfg.cover_position_mode}")
    LOGGER.info('%s', f"DEBUG: COVER_POSITION_FILE={cfg.cover_position_file}")

    setup = SetupConfig(cfg)
    if setup.snapshot().get('writable') is False:
        LOGGER.error('Setup storage unavailable; original preserved; no transports started')
        await run_setup_only(cfg, 'setup_storage_error')
        return

    # Missing after restore is not evidence of a first installation.
    try:
        load_devices(cfg.devices_file, create_if_missing=False)
        validate_recovery_document(cfg.devices_file.read_bytes())
    except (ValueError, OSError, TypeError, RecursionError):
        LOGGER.critical('Device configuration missing/invalid; restricted web recovery only. Dovit/MQTT disabled; original preserved.')
        await run_recovery(cfg)
        return
    ensure_cover_positions_file(cfg.cover_position_file)
    editor = DeviceEditor(cfg.devices_file)
    try:
        if editor.apply_pending():
            LOGGER.info('Device edit applied; previous configuration backed up')
    except (ValueError, OSError, TypeError, KeyError):
        LOGGER.exception('Device edit startup processing failed; inspect active configuration and pending change')

    try:
        resolved = await asyncio.to_thread(resolve_mqtt_config, cfg)
    except MqttServiceError as error:
        LOGGER.error('MQTT configuration unavailable key=%s; setup only, no transports', error.key)
        await run_setup_only(cfg, error.key)
        return
    setup_logging((resolved.mqtt_user, resolved.mqtt_pass, resolved.alarm_code,
                   os.environ.get('SUPERVISOR_TOKEN', '')))
    b = DovitBridge(resolved)
    b.monitor.setup_config = setup
    b.monitor.device_editor = editor
    b.monitor.draft_directory = cfg.devices_file.parent / 'dovit_mapping_drafts'
    candidates = CandidateStore(b.monitor, cfg.devices_file.with_name('dovit_observed_candidates.json'))
    candidates.load()
    asyncio.create_task(candidates.run())
    b.loop = asyncio.get_running_loop()
    if cfg.web_light_control:
        b.monitor.light_control = LightControl(b.monitor, b.loop, b)
    if cfg.web_device_control:
        b.monitor.device_control = DeviceControl(b.monitor, b.loop, b)
    start_monitor(b.monitor)
    await run_bridge(b, cfg)


async def run_setup_only(cfg, error):
    """Configuration failures are repairable in UI, never silent broker fallback."""
    monitor = Monitor((cfg.mqtt_user, cfg.mqtt_pass, cfg.alarm_code, os.environ.get('SUPERVISOR_TOKEN', '')))
    monitor.setup_config = SetupConfig(cfg)
    monitor.runtime_status = lambda: dict(mqtt_connected=False, mqtt_state='unavailable',
        mqtt_mode=cfg.mqtt_mode, mqtt_changed_at=None, configuration_error=error,
        dovit_state='not_started', discovery_publishing=cfg.enable_discovery or cfg.publish_discovery,
        automatic_discovery=cfg.enable_discovery)
    try:
        maps = validate_recovery_document(cfg.devices_file.read_bytes())
        monitor.configure({key: maps.get(key, {}) for key in
            ('lights', 'switches', 'shutters', 'thermostats', 'motions', 'contacts', 'alarms')}, include_system=True)
    except (ValueError, OSError, TypeError, RecursionError):
        pass
    server = start_monitor(monitor)
    try:
        await asyncio.Event().wait()
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()


async def run_recovery(cfg):
    """Recovery never falls through to runtime, even after a successful restore."""
    monitor = Monitor((cfg.mqtt_pass, cfg.alarm_code))
    monitor.recovery = RecoveryManager(cfg.devices_file)
    server = start_monitor(monitor)
    try:
        await asyncio.Event().wait()
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()


async def run_bridge(b, cfg):
    discovery_task = None
    status_task = None
    try:
        b.dovit.on_connection_lost = lambda: b.set_dovit_connected(False)
        b.set_dovit_connected(False)
        b.start_mqtt()
        discovery_task = asyncio.create_task(b.discovery_republish_loop())
        status_task = asyncio.create_task(b.session_status_retry_loop())
        attempts = 0
        while True:
            attempts += 1
            connected_at = None
            try:
                LOGGER.info("Dovit connection attempt=%s host=%s port=%s", attempts, cfg.dovit_host, cfg.dovit_port)
                await b.connect_dovit()
                b.set_dovit_connected(True)
                connected_at = time.monotonic()
                await b.dovit_read_loop()
            except Exception as e:
                b.set_dovit_connected(False)
                b.reset_cover_motion()
                await b.dovit.close()
                LOGGER.error("Dovit connection lost/failed type=%s attempt=%s connected_seconds=%.1f retry_in=3s",
                             type(e).__name__, attempts,
                             time.monotonic() - connected_at if connected_at else 0)
                await asyncio.sleep(3)
            finally:
                b.set_dovit_connected(False)
                await b.dovit.close()
    finally:
        b.set_dovit_connected(False)
        background_tasks = [task for task in (discovery_task, status_task) if task is not None]
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        try:
            b.reset_cover_motion()
            await b.dovit.close()
        finally:
            # PUBACK waits belong outside Paho callbacks and the asyncio loop.
            await asyncio.to_thread(b.mqtt.stop)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.info("Bridge stopped by operator")
    except Exception as exc:
        LOGGER.critical("Bridge terminated unexpectedly type=%s", type(exc).__name__, exc_info=True)
        raise SystemExit(1)
