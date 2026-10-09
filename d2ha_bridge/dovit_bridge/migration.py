"""Offline, private transfer bundles for the owner-authorized 3.0 -> 3.1 migration.

Never contacts HA/MQTT/Dovit or starts/stops an app. Input is a decrypted,
stopped source snapshot plus Supervisor info. Output is a NEW staging directory,
not a live /data or /share directory. Supervisor continues to manage options.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

from .config import Config
from .recovery import validate_recovery_document
from .setup_config import FIELDS, apply_setup_overrides, validate_settings
from .storage import _decode_positions

SOURCE_VERSION = '3.0.0'
TARGET_VERSION = '3.1.0'
SOURCE_SLUG = 'local_dovit_bridge'
TARGET_SLUG = 'd2ha_bridge'
FLAGS = ('enable_discovery', 'publish_discovery', 'web_light_control', 'web_device_control')
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_FILES = 2048
OPTIONS = ('mqtt_mode', 'mqtt_tls', 'mqtt_protocol', *FLAGS, 'dovit_host', 'dovit_port',
           'mqtt_host', 'mqtt_port', 'mqtt_user', 'mqtt_pass', 'devices_file',
           'cover_position_mode', 'cover_position_file', 'alarm_code')


class MigrationError(ValueError):
    """Safe error codes only: never include credentials or file contents."""


def require(condition, code):
    if not condition:
        raise MigrationError(code)


def decode(raw):
    require(len(raw) <= MAX_FILE, 'file_too_large')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def constant(_):
        raise MigrationError('nonfinite_json')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except MigrationError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise MigrationError('invalid_json') from None


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def safe_name(name):
    require(isinstance(name, str) and len(name) <= 512 and
            re.fullmatch(r'[A-Za-z0-9_./-]+', name) is not None, 'unsafe_path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and name == path.as_posix() and
            all(part not in ('.', '..') and not part.endswith('.') for part in path.parts), 'unsafe_path')
    # Prevent Windows device names, including names with an extension.
    require(all(part.split('.')[0].upper() not in
                {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)),
                 *(f'LPT{i}' for i in range(10))} for part in path.parts), 'unsafe_path')
    return path


def no_link(path):
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode) and
            not getattr(info, 'st_file_attributes', 0) & 0x400, 'link_not_allowed')


def read_file(path, root):
    path, root = Path(path), Path(root)
    require(path.resolve().is_relative_to(root.resolve()), 'path_outside_snapshot')
    current = path
    while True:
        no_link(current)
        if current == root:
            break
        require(current != current.parent, 'path_outside_snapshot')
        current = current.parent
    require(path.is_file() and path.stat().st_size <= MAX_FILE, 'invalid_source_file')
    with path.open('rb') as stream:
        raw = stream.read(MAX_FILE + 1)
    require(len(raw) <= MAX_FILE, 'file_too_large')
    return raw


def walk_files(root):
    root = Path(root)
    require(root.is_dir(), 'snapshot_directory_missing')
    no_link(root)
    result = {}
    entries_seen = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        entries_seen += len(dirs) + len(files)
        require(entries_seen <= MAX_FILES, 'snapshot_too_large')
        for name in dirs:
            no_link(Path(directory) / name)
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            safe_name(relative)
            result[relative] = read_file(path, root)
            require(len(result) <= MAX_FILES and sum(map(len, result.values())) <= MAX_TOTAL,
                    'snapshot_too_large')
    return result


def supervisor_info(raw, slug, version):
    info = decode(raw)
    require(isinstance(info, dict), 'invalid_supervisor_info')
    if 'result' in info:
        require(info.get('result') == 'ok', 'supervisor_request_failed')
        info = info.get('data')
    require(isinstance(info, dict), 'invalid_supervisor_info')
    app_id = info.get('slug')
    require(isinstance(app_id, str) and re.fullmatch(r'[a-z0-9_]+', app_id) is not None
            and app_id.endswith('_' + slug), 'unexpected_app_identity')
    require(info.get('version') == version, 'unexpected_app_version')
    require(info.get('state') == 'stopped', 'app_not_stopped')
    require(info.get('boot') == 'manual' and info.get('watchdog') is False
            and info.get('auto_update') is False, 'start_protection_missing')
    return info, app_id[:-len(slug) - 1]


def configured_path(value):
    require(isinstance(value, str) and value.startswith('/'), 'unsupported_configured_path')
    path = safe_name(value[1:])
    require(path.parts[0] in ('data', 'share') and len(path.parts) > 1,
            'unsupported_configured_path')
    return path.as_posix()


def config_from_options(raw):
    options = decode(raw)
    require(isinstance(options, dict) and options and set(options) <= set(OPTIONS),
            'incomplete_or_unknown_options')
    require({'dovit_host', 'dovit_port', 'mqtt_host', 'mqtt_port', 'devices_file'} <= set(options),
            'incomplete_or_unknown_options')
    values = {key: options.get(key, getattr(Config(), key)) for key in OPTIONS}
    try:
        validate_settings({key: values[key] for key in FIELDS})
        require(all(type(values[key]) is bool for key in FLAGS), 'invalid_options')
        require(values['cover_position_mode'] in ('legacy', 'timed'), 'invalid_options')
        require(all(isinstance(values[key], str) and len(values[key]) <= 1024
                    for key in ('mqtt_pass', 'alarm_code')), 'invalid_options')
        device = configured_path(str(values['devices_file']))
        positions = configured_path(str(values['cover_position_file']))
        values['devices_file'] = Path('/' + device)
        values['cover_position_file'] = Path('/' + positions)
        return options, Config(**values), device, positions
    except MigrationError:
        raise
    except (ValueError, TypeError):
        raise MigrationError('invalid_options') from None


def validate_setup(cfg, raw):
    if raw is None:
        return cfg
    # Exercise the production decoder without writing to a live private path.
    with tempfile.TemporaryDirectory(prefix='d2ha-setup-validation-') as tmp:
        path = Path(tmp) / 'setup.json'
        path.write_bytes(raw)
        try:
            return apply_setup_overrides(cfg, path)
        except (ValueError, OSError):
            raise MigrationError('invalid_private_setup') from None


def patched_setup(raw):
    document = decode(raw)
    document['settings']['publish_discovery'] = False
    return encode(document)


def approved_data(name, device, positions, reviewed):
    forbidden = ('token', 'ingress', 'auth', 'session', 'supervisor')
    require(not any(part in name.lower() for part in forbidden), 'runtime_access_data_forbidden')
    fixed = {'dovit_setup.json', device.removeprefix('data/'), positions.removeprefix('data/')}
    parent = str(PurePosixPath(device).parent).removeprefix('data/')
    adjacent = {'dovit_observed_candidates.json', 'dovit_device_backups', 'dovit_mapping_drafts'}
    known_adjacent = device.startswith('data/') and any(
        name == (PurePosixPath(parent) / part).as_posix() or
        name.startswith((PurePosixPath(parent) / part).as_posix() + '/') for part in adjacent)
    return name in fixed or name.startswith('dovit_setup_backups/') or known_adjacent or name in reviewed


def build_bundle(data_dir, share_dir, source_info_raw, reviewed_data=()):
    info, prefix = supervisor_info(source_info_raw, SOURCE_SLUG, SOURCE_VERSION)
    data = walk_files(data_dir)
    require('options.json' in data, 'source_options_missing')
    options_raw = data.pop('options.json')
    options, cfg, device, positions = config_from_options(options_raw)
    require(isinstance(info.get('options'), dict) and info['options'], 'supervisor_options_redacted')
    require(info['options'] == options, 'source_options_disagree')
    require(device != positions, 'overlapping_configured_paths')
    reviewed = sorted(set(str(safe_name(name)) for name in reviewed_data))
    for name in data:
        require(approved_data(name, device, positions, reviewed), 'unknown_private_file_needs_review')
    require(set(reviewed) <= set(data), 'reviewed_file_missing')
    # Read only files belonging to the bridge, not other apps' shared files.
    shared = {}
    def capture(logical, required=False):
        namespace, name = logical.split('/', 1)
        if namespace == 'data':
            require(not required or name in data, 'active_mapping_missing')
            return data.get(name)
        path = Path(share_dir).joinpath(*PurePosixPath(name).parts)
        if not os.path.lexists(path):
            require(not required, 'active_mapping_missing')
            return None
        raw = read_file(path, Path(share_dir))
        shared[name] = raw
        return raw
    mapping = capture(device, required=True)
    pending = str(PurePosixPath(device).with_name(PurePosixPath(device).stem + '.pending.json'))
    require(capture(pending) is None, 'pending_mapping_blocks_migration')
    try:
        maps = validate_recovery_document(mapping)
        require(any(maps.get(category) for category in
                    ('lights', 'switches', 'shutters', 'thermostats', 'motions', 'contacts', 'alarms')),
                'empty_mapping_needs_review')
        positions_raw = capture(positions)
        if positions_raw is not None:
            decode(positions_raw)
            _decode_positions(positions_raw)
    except MigrationError:
        raise
    except (ValueError, TypeError, OSError, RecursionError):
        raise MigrationError('invalid_mapping_or_positions') from None
    if device.startswith('share/'):
        parent = PurePosixPath(device).parent
        capture((parent / 'dovit_observed_candidates.json').as_posix())
        for directory in ('dovit_device_backups', 'dovit_mapping_drafts'):
            logical = parent / directory
            path = Path(share_dir).joinpath(*logical.parts[1:])
            if os.path.lexists(path):
                for name, raw in walk_files(path).items():
                    shared[(logical / name).relative_to('share').as_posix()] = raw
    source_effective = validate_setup(cfg, data.get('dovit_setup.json'))
    target_options = dict(options, **{key: False for key in FLAGS})
    target_cfg = replace(cfg, **{key: False for key in FLAGS})
    target_data = dict(data)
    if 'dovit_setup.json' in target_data:
        target_data['dovit_setup.json'] = patched_setup(target_data['dovit_setup.json'])
    target_effective = validate_setup(target_cfg, target_data.get('dovit_setup.json'))
    require(target_effective == replace(source_effective, **{key: False for key in FLAGS}),
            'effective_configuration_changed')
    blobs = {'source/options.json': options_raw, 'target/options.json': encode(target_options)}
    for name, raw in data.items():
        blobs['source/data/' + name] = raw
        blobs['target/data/' + name] = target_data[name]
    for name, raw in shared.items():
        blobs['source/share/' + name] = raw
    manifest = dict(format='D2HA_PHASE2_TRANSFER', format_version=1,
        source_version=SOURCE_VERSION, target_version=TARGET_VERSION,
        source_app_id=info['slug'], expected_target_app_id=prefix + '_' + TARGET_SLUG,
        created_at=datetime.now(timezone.utc).isoformat(), reviewed_data=reviewed,
        configured_paths=dict(devices_file='/' + device, cover_position_file='/' + positions),
        private_setup_present='dovit_setup.json' in data,
        cover_positions_present=positions_raw is not None,
        source_start_protected=True, source_reported_stopped=True,
        original_flags={key: getattr(source_effective, key) for key in FLAGS},
        files=[dict(path=name, length=len(raw), sha256=hashlib.sha256(raw).hexdigest())
               for name, raw in sorted(blobs.items())])
    require(len(blobs) <= MAX_FILES and sum(map(len, blobs.values())) <= MAX_TOTAL, 'bundle_too_large')
    require(walk_files(data_dir) == dict(data, **{'options.json': options_raw}), 'source_snapshot_changed')
    for name, raw in shared.items():
        require(read_file(Path(share_dir).joinpath(*PurePosixPath(name).parts), Path(share_dir)) == raw,
                'source_snapshot_changed')
    require(capture(pending) is None, 'pending_mapping_blocks_migration')
    return manifest, blobs


def write_bundle(path, manifest, blobs):
    # Exclusive creation; no existing backup/bundle can be overwritten.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('manifest.json', encode(manifest))
            for name, raw in sorted(blobs.items()):
                archive.writestr(name, raw)


def read_bundle(path):
    require(Path(path).stat().st_size <= MAX_TOTAL + 2 * 1024 * 1024, 'bundle_too_large')
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            require(len(entries) <= MAX_FILES + 1, 'bundle_too_large')
            names = [entry.filename for entry in entries]
            require(len({name.casefold() for name in names}) == len(names), 'duplicate_archive_path')
            require('manifest.json' in names, 'manifest_missing')
            total = 0
            blobs = {}
            for entry in entries:
                safe_name(entry.orig_filename)
                safe_name(entry.filename)
                require(entry.orig_filename == entry.filename, 'unsafe_path')
                mode = entry.external_attr >> 16
                require(not entry.is_dir() and stat.S_IFMT(mode) in (0, stat.S_IFREG)
                        and not entry.flag_bits & 1, 'unsupported_archive_entry')
                require(entry.file_size <= MAX_FILE, 'file_too_large')
                total += entry.file_size
                require(total <= MAX_TOTAL + MAX_FILE, 'bundle_too_large')
                with archive.open(entry) as stream:
                    raw = stream.read(MAX_FILE + 1)
                require(len(raw) == entry.file_size, 'archive_length_mismatch')
                blobs[entry.filename] = raw
    except MigrationError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError):
        raise MigrationError('invalid_archive') from None
    manifest = decode(blobs.pop('manifest.json'))
    require(isinstance(manifest, dict) and manifest.get('format') == 'D2HA_PHASE2_TRANSFER'
            and manifest.get('format_version') == 1, 'unsupported_bundle_format')
    require(manifest.get('source_version') == SOURCE_VERSION and
            manifest.get('target_version') == TARGET_VERSION, 'unexpected_bundle_version')
    records = manifest.get('files')
    require(isinstance(records, list) and all(isinstance(item, dict) and
            isinstance(item.get('path'), str) for item in records),
            'invalid_manifest_inventory')
    require({item.get('path') for item in records} == set(blobs) and len(records) == len(blobs),
            'archive_inventory_mismatch')
    for record in records:
        raw = blobs[record['path']]
        require(type(record.get('length')) is int and len(raw) == record['length'] and
                hashlib.sha256(raw).hexdigest() == record.get('sha256'), 'archive_hash_mismatch')
    # Rebuild from source blobs with the same production validation. This checks
    # allowed paths, original identities and the ONLY permitted target changes.
    with tempfile.TemporaryDirectory(prefix='d2ha-bundle-validation-') as tmp:
        root = Path(tmp)
        (root / 'data').mkdir()
        (root / 'share').mkdir()
        require('source/options.json' in blobs, 'source_options_missing')
        (root / 'data/options.json').write_bytes(blobs['source/options.json'])
        for name, raw in blobs.items():
            if name.startswith(('source/data/', 'source/share/')):
                destination = root / name.removeprefix('source/')
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
        info = dict(slug=manifest.get('source_app_id'), version=SOURCE_VERSION, state='stopped',
                    boot='manual', watchdog=False, auto_update=False,
                    options=decode(blobs['source/options.json']))
        rebuilt, expected = build_bundle(root / 'data', root / 'share', encode(info),
                                         manifest.get('reviewed_data', ()))
        require(expected == blobs, 'unexpected_target_change_or_file')
        for key in ('source_app_id', 'expected_target_app_id', 'configured_paths',
                    'private_setup_present', 'cover_positions_present', 'original_flags',
                    'source_start_protected', 'source_reported_stopped'):
            require(manifest.get(key) == rebuilt[key], 'manifest_configuration_mismatch')
    return manifest, blobs


def write_private(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'staged_copy_mismatch')


def stage_bundle(bundle, destination, target_info_raw):
    manifest, blobs = read_bundle(bundle)
    info, _ = supervisor_info(target_info_raw, TARGET_SLUG, TARGET_VERSION)
    require(info['slug'] == manifest['expected_target_app_id'], 'installation_source_changed')
    destination = Path(destination).absolute()
    require(not os.path.lexists(destination), 'staging_destination_exists')
    require(destination.parent.is_dir(), 'staging_parent_missing')
    no_link(destination.parent)
    temporary = Path(tempfile.mkdtemp(prefix='.d2ha-phase2-', dir=destination.parent))
    try:
        for name, raw in blobs.items():
            write_private(temporary / name, raw)
        write_private(temporary / 'manifest.json', encode(manifest))
        require(not os.path.lexists(destination), 'staging_destination_exists')
        os.rename(temporary, destination)
    finally:
        if temporary.exists():
            # Remove only the newly created, owned staging directory.
            require(temporary.resolve().parent == destination.parent.resolve(), 'invalid_cleanup_path')
            shutil.rmtree(temporary)
    return manifest


def summary(manifest):
    # Deliberately omit even app options, file contents and private path values.
    return dict(status='verified', source_version=SOURCE_VERSION, target_version=TARGET_VERSION,
                files=len(manifest['files']), private_setup_present=manifest['private_setup_present'],
                cover_positions_present=manifest['cover_positions_present'],
                live_app_state_verified=False, ha_actions_performed=False,
                staged_data_requires_separate_authorized_install=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export', help='Create a PRIVATE bundle from stopped snapshots')
    export.add_argument('--data-dir', required=True)
    export.add_argument('--share-dir', required=True)
    export.add_argument('--source-info', required=True)
    export.add_argument('--output', required=True)
    export.add_argument('--reviewed-data', action='append', default=[])
    inspect = commands.add_parser('inspect', help='Validate without importing or connecting')
    inspect.add_argument('bundle')
    stage = commands.add_parser('stage', help='Write only a NEW private staging directory')
    stage.add_argument('bundle')
    stage.add_argument('--destination', required=True)
    stage.add_argument('--target-info', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'export':
            manifest, blobs = build_bundle(args.data_dir, args.share_dir,
                Path(args.source_info).read_bytes(), args.reviewed_data)
            write_bundle(args.output, manifest, blobs)
            read_bundle(args.output)
        elif args.command == 'inspect':
            manifest, _ = read_bundle(args.bundle)
        else:
            manifest = stage_bundle(args.bundle, args.destination, Path(args.target_info).read_bytes())
        print(json.dumps(summary(manifest)))
    except MigrationError as error:
        parser.exit(2, 'Migration refused: ' + str(error) + '\n')
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        parser.exit(2, 'Migration refused: invalid_input_or_io_error\n')


if __name__ == '__main__':
    main()
