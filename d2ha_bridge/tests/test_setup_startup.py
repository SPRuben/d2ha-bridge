import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from dovit_bridge.config import Config
from dovit_bridge.main import main, run_setup_only
from dovit_bridge.mqtt_service import MqttServiceError
from dovit_bridge.setup_config import SetupConfig


class SetupStartupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'devices.json'
        self.path.write_text('{"lights":{},"shutters":{},"thermostats":{}}')
        self.cfg = Config(devices_file=self.path,
                          cover_position_file=self.path.with_name('positions.json'))

    def test_service_failure_enters_ui_only_without_transports(self):
        with patch('dovit_bridge.main.load_config', return_value=self.cfg), \
             patch('dovit_bridge.main.apply_setup_overrides', side_effect=lambda cfg: cfg), \
             patch('dovit_bridge.main.setup_logging'), \
             patch('dovit_bridge.main.resolve_mqtt_config', side_effect=MqttServiceError('mqtt_service_unavailable')), \
             patch('dovit_bridge.main.run_setup_only', new_callable=AsyncMock) as repair, \
             patch('dovit_bridge.main.DovitBridge') as bridge, \
             patch('dovit_bridge.main.start_monitor') as web:
            asyncio.run(main())
            repair.assert_awaited_once_with(self.cfg, 'mqtt_service_unavailable')
            bridge.assert_not_called()
            web.assert_not_called()

    def test_bad_overrides_never_start_transports(self):
        with patch('dovit_bridge.main.load_config', return_value=self.cfg), \
             patch('dovit_bridge.main.apply_setup_overrides', side_effect=ValueError('setup_storage_error')), \
             patch('dovit_bridge.main.setup_logging'), \
             patch('dovit_bridge.main.run_setup_only', new_callable=AsyncMock) as repair, \
             patch('dovit_bridge.main.DovitBridge') as bridge:
            asyncio.run(main())
            repair.assert_awaited_once_with(self.cfg, 'setup_storage_error')
            bridge.assert_not_called()

    def test_unpreservable_setup_file_keeps_actual_repair_ui_alive_without_transports(self):
        setup_path = self.path.with_name('setup.json')
        original_open = Path.open
        for failure in ('unreadable', 'oversized'):
            with self.subTest(failure=failure):
                original = (b'{"private":"stored secret"}' if failure == 'unreadable'
                            else b'x' * (1024 * 1024 + 1))
                setup_path.write_bytes(original)
                server = Mock()
                event = Mock(wait=AsyncMock(side_effect=asyncio.CancelledError))

                def read_source(path, *args, **kwargs):
                    if failure == 'unreadable' and path == setup_path:
                        raise PermissionError('stored secret must not enter GUI')
                    return original_open(path, *args, **kwargs)

                with patch('dovit_bridge.setup_config.setup_path', return_value=setup_path), \
                     patch('dovit_bridge.setup_config.Path.open', new=read_source), \
                     patch('dovit_bridge.main.load_config', return_value=self.cfg), \
                     patch('dovit_bridge.main.setup_logging'), \
                     patch('dovit_bridge.main.start_monitor', return_value=server) as web, \
                     patch('dovit_bridge.main.asyncio.Event', return_value=event), \
                     patch('dovit_bridge.main.DovitBridge') as bridge, \
                     patch('dovit_bridge.main.resolve_mqtt_config') as resolver, \
                     patch('dovit_bridge.main.CandidateStore') as candidates:
                    with self.assertRaises(asyncio.CancelledError):
                        asyncio.run(main())
                    monitor = web.call_args.args[0]
                    self.assertIsInstance(monitor.setup_config, SetupConfig)
                    self.assertFalse(monitor.setup_config.snapshot()['writable'])
                    self.assertEqual(monitor.snapshot()['setup']['configuration_error'], 'setup_storage_error')
                    self.assertIsNone(monitor.device_control)
                    self.assertIsNone(monitor.light_control)
                    bridge.assert_not_called()
                    resolver.assert_not_called()
                    candidates.assert_not_called()
                    server.shutdown.assert_called_once()
                    server.server_close.assert_called_once()
                self.assertEqual(setup_path.read_bytes(), original)
                self.assertFalse((setup_path.parent / 'dovit_setup_backups').exists())

    def test_setup_repair_does_not_present_invalid_inventory_as_empty_installation(self):
        for content, configured in [('{"lights":{},"shutters":{},"thermostats":{}}', True),
                                    ('{"lights":{"19":{"name":"Bad","statetype":-1}}}', False),
                                    ('{broken', False), (None, False)]:
            with self.subTest(content=content):
                if content is None:
                    self.path.unlink(missing_ok=True)
                else:
                    self.path.write_text(content)
                server = Mock()
                event = Mock(wait=AsyncMock(side_effect=asyncio.CancelledError))
                with patch('dovit_bridge.main.SetupConfig'), \
                     patch('dovit_bridge.main.start_monitor', return_value=server) as web, \
                     patch('dovit_bridge.main.asyncio.Event', return_value=event), \
                     patch('dovit_bridge.main.DovitBridge') as bridge:
                    with self.assertRaises(asyncio.CancelledError):
                        asyncio.run(run_setup_only(self.cfg, 'invalid_configuration'))
                    monitor = web.call_args.args[0]
                    self.assertIs(monitor.snapshot()['inventory_configured'], configured)
                    if not configured:
                        self.assertEqual(monitor.snapshot()['devices'], [])
                    bridge.assert_not_called()
                    server.shutdown.assert_called_once()
                    server.server_close.assert_called_once()

    def test_resolved_credentials_are_runtime_only_and_redacted(self):
        resolved = replace(self.cfg, mqtt_user='service-user', mqtt_pass='service-private')
        fake_bridge = Mock()
        with patch('dovit_bridge.main.load_config', return_value=self.cfg), \
             patch('dovit_bridge.main.apply_setup_overrides', side_effect=lambda cfg: cfg), \
             patch('dovit_bridge.main.setup_logging') as logging, \
             patch('dovit_bridge.main.resolve_mqtt_config', return_value=resolved), \
             patch('dovit_bridge.main.SetupConfig') as setup, \
             patch('dovit_bridge.main.DovitBridge', return_value=fake_bridge) as bridge, \
             patch('dovit_bridge.main.CandidateStore') as candidates, \
             patch('dovit_bridge.main.start_monitor'), \
             patch('dovit_bridge.main.run_bridge', new_callable=AsyncMock):
            candidates.return_value.run = AsyncMock()
            asyncio.run(main())
            bridge.assert_called_once_with(resolved)
            setup.assert_called_once_with(self.cfg)
            self.assertIn('service-private', logging.call_args.args[0])
            self.assertIs(fake_bridge.monitor.setup_config, setup.return_value)
