"""Loopback-only UI preview with synthetic data. Never connects to Dovit/MQTT."""
from dovit_bridge.web_monitor import Monitor, make_server
from dovit_bridge.light_control import LightControl
from dovit_bridge.device_control import DeviceControl
from dovit_bridge.device_editor import DeviceEditor
from pathlib import Path
import json
import tempfile
import argparse
import shutil
from dovit_bridge.recovery_service import RecoveryManager
from dovit_bridge.config import Config
from dovit_bridge.setup_config import SetupConfig, apply_setup_overrides
from dovit_bridge.recovery import validate_recovery_document
from dovit_bridge.storage import as_int_keys

def create_preview(state_directory=None):
    """Create the simulation without a listener; caller owns cleanup."""
    temporary = tempfile.TemporaryDirectory(prefix='dovit_preview_')
    try:
        maps = {
            'lights': {
                19: {'name': 'Test Bureau', 'statetype': 0},
                22: {'name': 'Test Wohnbereich mit einem besonders langen Geraetenamen', 'statetype': 0},
                23: {'name': 'TODO_Light_23', 'statetype': 0},
            },
            'shutters': {20: {'name': 'Test Bureau Fenster', 'statetype': 1, 'command_statetype': 0}},
            'thermostats': {44: {
                'name': 'Test Thermostat', 'target': {'statetype': 1},
                'current': {'id': 42, 'statetype': 1}, 'mode': {'id': 46, 'statetype': 0},
                'min_temp': 16, 'max_temp': 26, 'temp_step': .5,
            }},
            'motions': {77: {'name': 'Test Flur', 'statetype': 0}},
            'contacts': {
                124: {'name': 'Test Eingang', 'statetype': 0, 'device_class': 'door'},
                125: {'name': 'Test Esszimmer Fenster', 'statetype': 0, 'device_class': 'window'},
            },
            # One occupied role and one free role demonstrate assignment rules.
            'alarms': {87: {
                'name': 'Test Alarm Bewegung', 'partition_role': 'motion',
                'state_statetype': 1, 'text_statetype': 10,
                'trigger_statetype': 13, 'command_statetype': 0,
            }},
        }
        path = Path(temporary.name) / 'devices.json'
        if state_directory is None:
            path.write_text(json.dumps(maps, indent=2), encoding='utf-8')
        else:
            # Resume in a disposable copy, never write into the saved source.
            shutil.copytree(state_directory, temporary.name, dirs_exist_ok=True)
            maps = validate_recovery_document(path.read_bytes())
        setup_file = Path(temporary.name) / 'setup.json'
        cfg = apply_setup_overrides(Config(devices_file=path), setup_file)
        monitor = Monitor()
        monitor.configure(maps, include_system=True)
        monitor.light_control = LightControl(monitor, simulation=True)
        control_maps = {category: as_int_keys(maps.get(category, {}))
                        for category in ('shutters', 'thermostats')}
        monitor.device_control = DeviceControl(monitor, simulation=True, maps=control_maps)
        monitor.device_editor = DeviceEditor(path)
        monitor.setup_config = SetupConfig(cfg, setup_file, simulation=True)
        for dev, statetype, values in [
            (19, 0, ['0', '1']), (22, 0, ['0']), (23, 0, ['0']), (20, 1, ['2', '0']),
            (42, 1, ['21.8']), (44, 1, ['22.5']), (46, 0, ['1']),
            (77, 0, ['0', '1']), (124, 0, ['0']), (125, 0, ['1']),
            (87, 1, ['0']), (87, 10, ['Synthetic alarm status - no real alarm']),
            (39, 111, ['15;44']), (999, 3, ['0', '1']), (19, 9, ['raw-unknown']),
        ]:
            for value in values:
                monitor.observe(dev, statetype, value)
        return monitor, temporary
    except Exception:
        temporary.cleanup()
        raise


def create_recovery_preview():
    """Disposable damaged target and sample backups; no device control objects."""
    temporary = tempfile.TemporaryDirectory(prefix='dovit_recovery_preview_')
    try:
        path = Path(temporary.name) / 'devices.json'
        path.write_bytes(b'{ invalid synthetic configuration')
        directory = path.parent / 'dovit_device_backups'
        directory.mkdir()
        (directory / 'demo_valid.json').write_text(json.dumps({
            'lights': {'19': {'name': 'Synthetic Bureau', 'statetype': 0}},
            'alarms': {'87': {'name': 'Synthetic motion partition', 'partition_role': 'motion',
                             'state_statetype': 1, 'text_statetype': 10, 'trigger_statetype': 13}},
        }), encoding='utf-8')
        (directory / 'demo_invalid.json').write_bytes(b'{ invalid backup')
        monitor = Monitor()
        monitor.recovery = RecoveryManager(path)
        return monitor, temporary
    except Exception:
        temporary.cleanup()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovery', action='store_true', help='Preview restricted recovery with disposable files')
    parser.add_argument('--restore-state', type=Path,
                        help='Copy saved synthetic preview files into a new disposable directory')
    args = parser.parse_args()
    if args.recovery and args.restore_state:
        parser.error('--restore-state is only available for the normal synthetic preview')
    monitor, temporary = create_recovery_preview() if args.recovery else create_preview(args.restore_state)
    server = None
    try:
        print('SYNTHETIC preview: http://127.0.0.1:8097 - no Dovit/MQTT; edits are temporary', flush=True)
        print(f'Synthetic state directory: {temporary.name}', flush=True)
        server = make_server(monitor, '127.0.0.1', 8097, '127.0.0.1')
        server.serve_forever()
    finally:
        if server is not None:
            server.server_close()
        temporary.cleanup()


if __name__ == '__main__':
    main()
