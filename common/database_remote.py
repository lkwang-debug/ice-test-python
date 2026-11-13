"""Standalone SSH-side discovery/query helper; credentials never leave the server."""
import copy
import csv
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.parse
import uuid
import xml.etree.ElementTree as ET


def strip_prefix(value, prefix):
    return value[len(prefix):] if value.startswith(prefix) else value


def merge(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def expand(value, env):
    if not isinstance(value, str):
        return value
    def replace(match):
        name, separator, default = match.group(1).partition(':')
        if name in env:
            return env[name]
        if separator:
            return default
        raise RuntimeError('Unresolved configuration variable: ' + name)
    return re.sub(r'\$\{([^{}]+)\}', replace, value)


def process_settings(args, env):
    settings = {}
    for key in ['spring.profiles.active', 'spring.config.location', 'spring.config.additional-location',
                'spring.datasource.url', 'spring.datasource.username', 'spring.datasource.password']:
        env_key = key.upper().replace('.', '_').replace('-', '_')
        if env_key in env:
            settings[key] = env[env_key]
        for prefix in ['-D' + key + '=', '--' + key + '=']:
            for i, arg in enumerate(args):
                if arg.startswith(prefix):
                    settings[key] = arg[len(prefix):]
                elif prefix.startswith('--') and arg == '--' + key and i + 1 < len(args):
                    settings[key] = args[i + 1]
    return settings


def is_gateway_process(args):
    if not args or 'java' not in Path(args[0]).name:
        return False
    if 'com.hst.dbproxy.App' in args:
        return True
    if '-jar' in args:
        index = args.index('-jar') + 1
        return index < len(args) and bool(re.fullmatch(r'db-proxy(?:-core)?(?:-\d[\w.+-]*)?\.jar', Path(args[index]).name))
    return False


def find_process(proc_root='/proc'):
    found = []
    for folder in Path(proc_root).iterdir():
        if not folder.name.isdigit():
            continue
        try:
            args = folder.joinpath('cmdline').read_bytes().decode().strip('\0').split('\0')
            if not is_gateway_process(args):
                continue
            found.append(str(folder))
        except (OSError, UnicodeError):
            continue
    if len(found) != 1:
        raise RuntimeError('Expected exactly one running IceDBProxy process (java -jar db-proxy*.jar or com.hst.dbproxy.App); found %s' % len(found))
    return found[0]


def read_process(folder):
    path = Path(folder)
    args = path.joinpath('cmdline').read_bytes().decode().strip('\0').split('\0')
    env = dict(item.split('=', 1) for item in path.joinpath('environ').read_bytes().decode().split('\0') if '=' in item)
    return args, env, path.joinpath('cwd').resolve()


def load_yaml(path, profiles=()):
    import yaml
    result = {}
    with Path(path).open(encoding='utf-8') as stream:
        for document in yaml.safe_load_all(stream):
            if not document:
                continue
            spring = document.get('spring', {})
            activation = spring.get('config', {}).get('activate', {}).get('on-profile')
            if activation and str(activation) not in profiles:
                continue
            if spring.get('config', {}).get('import'):
                raise RuntimeError('spring.config.import requires an explicit database configuration')
            merge(result, document)
    return result


def config_locations(value, cwd):
    paths = []
    for item in value.split(','):
        item = strip_prefix(strip_prefix(item.strip(), 'optional:'), 'file:')
        if not item or item.startswith('classpath:'):
            raise RuntimeError('Unsupported Spring configuration location; use an explicit config_dir')
        path = Path(item)
        paths.append(path if path.is_absolute() else cwd / path)
    return paths


def inferred_config_dir(args, env, cwd):
    """Anchor discovery to the running deployment, never scan stale sibling installs."""
    candidates = [cwd / 'config', cwd, cwd.parent / 'config']
    if '-jar' in args:
        index = args.index('-jar') + 1
        if index < len(args):
            jar = Path(args[index])
            jar = jar if jar.is_absolute() else cwd / jar
            candidates += [jar.parent / 'config']
            if jar.parent.name in {'app', 'lib', 'bin', 'bin_node'}:
                candidates.append(jar.parent.parent / 'config')
    classpath = env.get('CLASSPATH', '')
    for option in ['-cp', '-classpath', '--class-path']:
        if option in args and args.index(option) + 1 < len(args):
            classpath = args[args.index(option) + 1]
    for entry in classpath.split(os.pathsep):
        if not entry:
            continue
        path = Path(entry)
        path = path if path.is_absolute() else cwd / path
        folder = path.parent if path.name == '*' or path.suffix == '.jar' else path
        if folder.name in {'app', 'lib', 'bin', 'bin_node'}:
            candidates.append(folder.parent / 'config')
    candidates = list(dict.fromkeys(path.resolve() for path in candidates))
    existing = [path for path in candidates if any((path / filename).is_file() for filename in ['application.yml', 'application.yaml'])]
    if len(existing) != 1:
        raise RuntimeError('Cannot uniquely infer the running gateway configuration directory; set database.config_dir '
                           '(found %s candidates)' % len(existing))
    return existing[0]


def source_selection(config):
    if config.get('backend') != 'auto':
        if not config.get('server_config'):
            raise RuntimeError('Manual SSH database configuration requires server_config')
        return {'config_files': [config['server_config']], 'profiles': [], 'process': None}
    process = find_process()
    args, env, cwd = read_process(process)
    settings = process_settings(args, env)
    configured = config.get('config_dir')
    if configured:
        path = Path(expand(configured, env))
        roots = [path if path.is_absolute() else cwd / path]
    else:
        roots = []
    if settings.get('spring.config.location'):
        roots = config_locations(expand(settings['spring.config.location'], env), cwd)
    elif settings.get('spring.config.additional-location') and not roots:
        roots = [cwd, cwd / 'config']
    elif not roots:
        roots = [inferred_config_dir(args, env, cwd)]
    if settings.get('spring.config.additional-location'):
        roots.extend(config_locations(expand(settings['spring.config.additional-location'], env), cwd))
    roots = list(dict.fromkeys(p.resolve() for p in roots))
    files, merged = [], {}
    for root in roots:
        candidates = [root] if root.is_file() else [root / 'application.yml', root / 'application.yaml']
        for path in candidates:
            if path.is_file():
                files.append(str(path)); merge(merged, load_yaml(path))
    active = settings.get('spring.profiles.active', merged.get('spring', {}).get('profiles', {}).get('active', ''))
    active = expand(active, env)
    profiles = [str(p).strip() for p in (active if isinstance(active, list) else str(active).split(',')) if str(p).strip()]
    for profile in profiles:
        if not re.fullmatch(r'[\w-]+', profile):
            raise RuntimeError('Unsupported/ambiguous active Spring profile')
        for root in roots:
            if root.is_file():
                root = root.parent
            for suffix in ['yml', 'yaml']:
                path = root / ('application-' + profile + '.' + suffix)
                if path.is_file():
                    files.append(str(path))
    if not files:
        raise RuntimeError('No active IceDBProxy YAML configuration found')
    return {'config_files': list(dict.fromkeys(files)), 'profiles': profiles, 'process': process}


def read_datasource(source):
    merged = {}
    env, settings = {}, {}
    if source.get('process'):
        args, env, _ = read_process(source['process'])
        settings = process_settings(args, env)
    for filename in source['config_files']:
        merge(merged, load_yaml(filename, source.get('profiles', [])))
    data = dict(merged.get('spring', {}).get('datasource', {}))
    for name in ['url', 'username', 'password']:
        key = 'spring.datasource.' + name
        if key in settings:
            data[name] = settings[key]
        data[name] = expand(data.get(name), env)
    if not data.get('url') or data.get('username') is None or data.get('password') is None:
        raise RuntimeError('Active datasource must specify url, username and password')
    url = urllib.parse.urlparse(strip_prefix(data['url'], 'jdbc:'))
    dialect = {'mysql': 'mysql', 'kingbase8': 'kingbase', 'kingbase': 'kingbase'}.get(url.scheme)
    if not dialect:
        raise RuntimeError('Unsupported database type: ' + url.scheme)
    if not url.netloc or not url.path.strip('/'):
        raise RuntimeError('JDBC target must specify database hosts and a database name')
    endpoints = []
    try:
        for authority in url.netloc.rsplit('@', 1)[-1].split(','):
            endpoint = urllib.parse.urlsplit('//' + authority)
            if not endpoint.hostname:
                raise ValueError('Missing database host')
            endpoints.append((endpoint.hostname, endpoint.port or (3306 if dialect == 'mysql' else 54321)))
    except ValueError:
        raise RuntimeError('Invalid JDBC database host/port configuration') from None
    if len(endpoints) > 1 and dialect != 'kingbase':
        raise RuntimeError('Multiple JDBC hosts are currently supported for Kingbase only')
    target = {'dialect': dialect, 'host': ','.join(host for host, _ in endpoints),
              'port': endpoints[0][1] if len(endpoints) == 1 else ','.join(str(port) for _, port in endpoints),
              'name': urllib.parse.unquote(url.path.strip('/'))}
    selectors = urllib.parse.parse_qs(url.query).get('targetServerType', [])
    if selectors and dialect == 'kingbase':
        choices = {'any': 'any', 'master': 'read-write', 'primary': 'read-write',
                   'slave': 'read-only', 'secondary': 'read-only'}
        normalized = {value.lower() for value in selectors}
        if len(normalized) != 1 or next(iter(normalized)) not in choices:
            raise RuntimeError('Unsupported or conflicting Kingbase targetServerType')
        target['session_attrs'] = choices[next(iter(normalized))]
    return data, target


def command(args, **kwargs):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25, **kwargs)


def candidate_clients(config, dialect):
    binary = 'mysql' if dialect == 'mysql' else 'ksql'
    paths = [config['client']] if config.get('client') else [binary]
    if dialect == 'kingbase' and not config.get('client'):
        paths += ['/opt/kingbase/ksql', '/opt/Kingbase/ES/V8/Server/bin/ksql']
    if 'container' in config:
        containers = [config['container']]
    else:
        containers = [None]
        if shutil.which('docker'):
            result = command(['docker', 'ps', '--format', '{{.Names}}'])
            if result.returncode:
                raise RuntimeError('Cannot list running database clients/containers')
            names = result.stdout.decode().splitlines()
            preferred = 'hst-mysql' if dialect == 'mysql' else 'hst-kingbase-client'
            containers += sorted(names, key=lambda n: (n != preferred, n))
    for container in containers:
        for path in paths:
            if container:
                # Only the fixed binary names/paths above or explicit operator configuration enter argv.
                result = command(['docker', 'exec', container, 'sh', '-c', 'command -v "$1"', 'sh', path])
                executable = result.stdout.decode().strip() if result.returncode == 0 else None
            else:
                executable = shutil.which(path)
            if executable:
                yield {'container': container, 'client': executable,
                       'library_path': config.get('library_path', str(Path(executable).parent) + ':' + str(Path(executable).parent.parent / 'lib'))}


def decode_mysql_xml(text):
    root = ET.fromstring(text)
    result = []
    for row in root.findall('row'):
        result.append({field.attrib['name']: None if field.attrib.get('{http://www.w3.org/2001/XMLSchema-instance}nil') == 'true'
                       else (field.text or '') for field in row.findall('field')})
    return result


def execute(source, target, client, sql):
    data, actual_target = read_datasource(source)
    if actual_target != target:
        raise RuntimeError('Datasource changed during the test run; rerun preflight')
    env = os.environ.copy()
    marker = '__ORACLE_NULL_' + uuid.uuid4().hex + '__'
    if target['dialect'] == 'mysql':
        env['MYSQL_PWD'] = str(data['password'])
        variables = ['MYSQL_PWD']
        args = [client['client'], '--default-character-set=utf8mb4', '--xml', '--binary-mode',
                '-h', target['host'], '-P', str(target['port']), '-u', str(data['username']), '-D', target['name']]
        query = 'START TRANSACTION READ ONLY; ' + sql + '; ROLLBACK;'
    else:
        env.update(PGPASSWORD=str(data['password']), KINGBASE_PASSWORD=str(data['password']),
                   LD_LIBRARY_PATH=client['library_path'], PGTARGETSESSIONATTRS=target.get('session_attrs', 'any'))
        variables = ['PGPASSWORD', 'KINGBASE_PASSWORD', 'LD_LIBRARY_PATH', 'PGTARGETSESSIONATTRS']
        args = [client['client'], '-X', '-w', '-q', '--csv', '-P', 'footer=off', '-P', 'null=' + marker,
                '-v', 'ON_ERROR_STOP=1', '-h', target['host'], '-p', str(target['port']),
                '-U', str(data['username']), '-d', target['name']]
        query = 'SET standard_conforming_strings=on; BEGIN TRANSACTION READ ONLY; ' + sql + '; ROLLBACK;'
    if client['container']:
        prefix = ['docker', 'exec', '-i']
        for variable in variables:
            prefix += ['-e', variable]
        args = prefix + [client['container']] + args
    result = command(args, input=query.encode('utf-8'), env=env)
    if result.returncode:
        error = result.stderr.decode('utf-8', 'replace')[-1200:]
        if data['password']:
            error = error.replace(str(data['password']), '[REDACTED]')
        raise RuntimeError('Read-only database query failed: ' + error)
    text = result.stdout.decode('utf-8')
    if target['dialect'] == 'mysql':
        return decode_mysql_xml(text)
    reader = csv.reader(io.StringIO(text))
    headers = next(reader, [])
    rows = []
    for values in reader:
        if not values and len(headers) == 1:
            values = ['']
        if len(values) != len(headers):
            raise RuntimeError('Database CSV column count differs from its header')
        rows.append({key: None if value == marker else value for key, value in zip(headers, values)})
    return rows


def resolve(config):
    source = source_selection(config)
    _, target = read_datasource(source)
    requested = config.get('backend')
    backend = 'ssh_' + target['dialect']
    if requested not in ('auto', backend):
        raise RuntimeError('Configured backend disagrees with datasource: ' + requested)
    errors = []
    for client in candidate_clients(config, target['dialect']):
        try:
            rows = execute(source, target, client, 'SELECT 1 AS oracle_available')
            if rows != [{'oracle_available': '1'}]:
                raise RuntimeError('Unexpected SELECT 1 response')
            return {'backend': backend, 'source': source, 'target': target, 'client': client}
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            errors.append((client['container'] or 'host') + ': ' + str(exc)[:500])
    raise RuntimeError('No usable ' + target['dialect'] + ' client for configured datasource; checked: ' + ', '.join(errors))


def main(request):
    try:
        if request['operation'] == 'resolve':
            result = resolve(request['config'])
        else:
            selected = request['resolved']
            result = execute(selected['source'], selected['target'], selected['client'], request['sql'])
        return {'result': result}
    except Exception as exc:
        # Never return tracebacks/local variables, which could contain datasource secrets.
        return {'error': str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__}
