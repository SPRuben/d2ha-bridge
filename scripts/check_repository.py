"""Offline release/configuration/privacy checks; never contact HA or devices."""
import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'd2ha_bridge'
URL = 'https://github.com/SPRuben/d2ha-bridge'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_yaml(path, base=yaml.SafeLoader):
    class UniqueLoader(base):
        pass

    def mapping(loader, node):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node)
            require(key not in result, f'Duplicate YAML key in {path.name}')
            result[key] = loader.construct_object(value_node)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    return yaml.load(path.read_text(encoding='utf-8-sig'), Loader=UniqueLoader)


def release_notes(version):
    text = (APP / 'CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(r'^## ' + re.escape(version) + r'[^\n]*\n(.*?)(?=^## |\Z)',
                      text, re.MULTILINE | re.DOTALL)
    require(match is not None, 'Version missing from changelog')
    return f'# D2HA Bridge {version}\n\n' + match[1].strip() + '\n'


def check(inventory=None, notes=None, app='d2ha_bridge'):
    global APP
    APP = ROOT / app
    config = load_yaml(APP / 'config.yaml')
    repository = load_yaml(ROOT / 'repository.yaml')
    version = config['version']
    require(re.fullmatch(r'\d+\.\d+\.\d+', version), 'Use a three-part version')
    require(config['slug'] == 'd2ha_bridge', 'Incorrect app identity')
    require(config['version'] == '3.1.1', 'Incorrect app release version')
    require(config['boot'] == 'manual', 'Incorrect app boot default')
    app_definitions = sorted(path.parent.name for path in ROOT.glob('*/config.yaml'))
    require(app_definitions == ['d2ha_bridge'], 'Only the current app may be advertised')
    require(config['name'] == config['panel_title'] == repository['name'] == 'D2HA Bridge',
            'Product names differ')
    require(config['panel_icon'] == 'mdi:bridge', 'Incorrect panel branding')
    require(repository['url'] == config['url'] == URL, 'Repository URLs differ')
    require(set(config['arch']) == {'amd64', 'aarch64'}, 'Architecture mismatch')
    require(config['image'] == 'ghcr.io/spruben/d2ha-bridge', 'Incorrect image reference')
    require(config['ingress'] and config['ingress_port'] == 8099 and config['panel_admin'],
            'Ingress configuration mismatch')
    require(not config.get('host_network') and not config.get('ports') and not config.get('webui'),
            'Web interface must remain internal to Ingress')
    require(config['map'] == [{'type': 'share', 'read_only': False}], 'Share mapping changed')
    require(config['services'] == ['mqtt:want'] and not config.get('hassio_api'),
            'Unexpected Supervisor permissions')
    require(config['stage'] == 'experimental', 'Live acceptance is still outstanding')
    options = config['options']
    compatibility = json.loads((ROOT / 'scripts/compatibility_baseline.json').read_text(encoding='utf-8'))
    require(options == compatibility['options'] and config['schema'] == compatibility['schema'],
            'Existing option/schema contract changed')
    for name, digest in compatibility['protected_files'].items():
        reviewed = compatibility['reviewed_changes'].get(name)
        expected = reviewed['sha256'] if reviewed else digest
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected,
                'Unreviewed runtime/identity/test change: ' + name)
    artwork = json.loads((ROOT / 'docs/assets/branding/manifest.json').read_text(encoding='utf-8'))
    for name, entry in artwork.items():
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == entry['sha256'],
                'Supplied artwork modified: ' + name)
    require((APP / 'icon.png').is_file() and (APP / 'logo.png').is_file(), 'App artwork missing')
    require(set(options) == set(config['schema']), 'Options and schema differ')
    require(options['dovit_host'] == '127.0.0.1', 'Dovit default must stay neutral')
    require(all(options[key] == '' for key in ('mqtt_user', 'mqtt_pass', 'alarm_code')),
            'Credentials must be empty')
    require(not any(options[key] for key in ('enable_discovery', 'publish_discovery',
                                            'web_light_control', 'web_device_control')),
            'Public control/discovery defaults changed')
    seed = json.loads((APP / 'dovit_devices.json').read_text(encoding='utf-8'))
    require(set(seed) == {'lights', 'switches', 'shutters', 'thermostats', 'motions', 'contacts', 'alarms'}
            and all(value == {} for value in seed.values()), 'Public seed must be empty')
    dockerfile = (APP / 'Dockerfile').read_text(encoding='utf-8')
    require(re.search(r'^FROM python:3\.11\.\d+-alpine3\.\d+@sha256:[a-f0-9]{64}$',
                      dockerfile, re.MULTILINE), 'Python/Alpine base must be pinned by digest')
    require(f'ARG BUILD_VERSION="{version}"' in dockerfile and 'io.hass.type="app"' in dockerfile,
            'Docker labels/version differ')
    require(not (APP / 'build.yaml').exists(), 'Obsolete build configuration')
    require('version=' + version + ' timestamps=UTC' in
            (APP / 'dovit_bridge' / 'main.py').read_text(encoding='utf-8'), 'Runtime version differs')
    require('D2HA / ' + version + '</span>' in
            (APP / 'dovit_bridge' / 'web' / 'index.html').read_text(encoding='utf-8'), 'UI version differs')

    files = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '--cached',
                                     '--others', '--exclude-standard', '-z']).decode().split('\0')
    files = sorted({name for name in files if name and (ROOT / name).is_file()})
    obsolete = ('172.30.' + '32.2', 'io.hass.type="' + 'addon"')
    secrets = re.compile(r'(?:ghp_|github_pat_|gho_)[A-Za-z0-9_]{20,}|'
                         r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|'
                         r'AKIA[A-Z0-9]{16}')
    private_paths = re.compile(r'[A-Z]:[\\/]+Users[\\/]+[^\\/\s]+')
    private_addresses = re.compile(r'(?<!\d)(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|'
                                   r'172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b')
    for name in files:
        path = ROOT / name
        require(not path.is_symlink(), f'Symlink in public files: {name}')
        require(not {'backups', 'backup', 'data', 'share', '.venv', 'venv'}.intersection(path.relative_to(ROOT).parts),
                f'Private directory tracked: {name}')
        require(path.name not in {'options.json', '.env', 'dovit_setup.json'} and not path.name.startswith('.env.'),
                f'Private configuration tracked: {name}')
        require(path.suffix not in {'.pem', '.key', '.bak', '.backup', '.log', '.pyc', '.zip', '.tar', '.gz'},
                f'Private/generated file tracked: {name}')
        if path.suffix.lower() in {'.jpg', '.png'}:
            continue
        text = path.read_text(encoding='utf-8-sig')
        require(not any(value in text for value in obsolete), f'Obsolete reference in {name}')
        require(not secrets.search(text) and not private_paths.search(text), f'Privacy check failed: {name}')
        if 'tests' not in path.parts and 'integration_tests' not in path.parts:
            require(not private_addresses.search(text), f'Private LAN address in {name}')
        if path.suffix == '.py':
            ast.parse(text, filename=name)
        elif path.suffix in {'.yaml', '.yml'}:
            load_yaml(path, yaml.BaseLoader if name.startswith('.github/') else yaml.SafeLoader)
        elif path.suffix == '.json':
            json.loads(text)
        elif path.suffix == '.md':
            for link in re.findall(r'\]\(([^)]+)\)', text):
                if re.match(r'(?:https?://|mailto:|#)', link):
                    continue
                target = link.split('#', 1)[0]
                require(not target or (path.parent / target).is_file(), f'Broken link in {name}: {target}')
    for name in ('USER_DE.md', 'USER_FR.md', 'DEVELOPER.md'):
        require((ROOT / 'docs' / name).read_bytes() ==
                (APP / 'dovit_bridge' / 'manuals' / name).read_bytes(), 'Bundled manual differs: ' + name)

    ignore_examples = ['backups/private.json', '.env', '.env.production', 'options.json',
                       'dovit_bridge/options.json', 'dovit_devices.private.json', 'data/dovit_setup.json',
                       'private.key', 'dovit_bridge/dovit_device_backups/mapping.json',
                       'private.bundle', 'migration-private/source-info.json']
    ignored = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-z', '--stdin'],
                             input=('\0'.join(ignore_examples) + '\0').encode(),
                             capture_output=True, check=True).stdout.decode().rstrip('\0').split('\0')
    require(set(ignored) == set(ignore_examples), 'Gitignore misses private paths')
    workflow = load_yaml(ROOT / '.github' / 'workflows' / 'ci.yml', yaml.BaseLoader)
    require({'pull_request', 'push', 'workflow_dispatch'} <= set(workflow['on']), 'CI triggers missing')
    require(workflow['on']['push']['branches'] == ['main'], 'CI must run on main')
    for job in workflow['jobs'].values():
        for step in job.get('steps', []):
            if 'uses' in step:
                require(re.fullmatch(r'[\w-]+/[\w-]+@[a-f0-9]{40}', step['uses']), 'Unpinned CI action')
    if inventory:
        production = [APP / name for name in ('Dockerfile', 'config.yaml', '.dockerignore',
                                               'requirements.txt', 'dovit_devices.json')]
        production += sorted(path for path in (APP / 'dovit_bridge').rglob('*')
                             if path.is_file() and '__pycache__' not in path.parts)
        with Path(inventory).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(('RelativePath', 'Length', 'SHA256'))
            for path in production:
                writer.writerow((path.relative_to(APP).as_posix(), path.stat().st_size,
                                 hashlib.sha256(path.read_bytes()).hexdigest()))
    generated = release_notes(version)
    if notes:
        Path(notes).write_text(generated, encoding='utf-8', newline='\n')
    else:
        require((ROOT / 'release' / f'v{version}.md').read_text(encoding='utf-8') == generated,
                'Release notes differ from changelog')
    print(json.dumps({'status': 'passed', 'app': app, 'version': version, 'public_files': len(files),
                      'configuration_syntax_links_privacy': 'passed', 'seed': 'empty'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', help='Write production SHA256 inventory outside the repository')
    parser.add_argument('--release-notes', help='Generate release notes directly from the current changelog')
    parser.add_argument('--app', choices=['d2ha_bridge'], default='d2ha_bridge')
    args = parser.parse_args()
    check(args.inventory, args.release_notes, args.app)
