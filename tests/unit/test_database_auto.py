"""Independent discovery, decoding and preflight regressions for both databases."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from common import database_remote as remote
from common.database import ReadonlyDatabase
from common.outcomes import PrerequisiteBlocked
from common.runtime import GatewayRuntime


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    config = tmp_path / 'config'
    config.mkdir()
    config.joinpath('application.yml').write_text('spring:\n  profiles:\n    active: mysql\n', encoding='utf-8')
    for profile, scheme in [('mysql', 'mysql'), ('kingbase', 'kingbase8')]:
        config.joinpath('application-' + profile + '.yml').write_text(
            'spring:\n  datasource:\n    url: jdbc:' + scheme + '://db.example:12345/meeting\n'
            '    username: test_user\n    password: secret\n', encoding='utf-8')
    state = {'args': ['java', '-jar', 'db-proxy.jar', '--spring.config.additional-location=../config/'], 'env': {}}
    monkeypatch.setattr(remote, 'find_process', lambda: 'test-process')
    monkeypatch.setattr(remote, 'read_process', lambda _: (state['args'], state['env'], tmp_path / 'bin'))
    return {'backend': 'auto', 'config_dir': str(config)}, state


@pytest.mark.parametrize('profile,dialect', [('mysql', 'mysql'), ('kingbase', 'kingbase')])
def test_detect_active_profile_and_jdbc_target(deployment, profile, dialect):
    config, state = deployment
    state['env']['SPRING_PROFILES_ACTIVE'] = profile
    source = remote.source_selection(config)
    _, target = remote.read_datasource(source)
    assert source['profiles'] == [profile]
    assert target == {'dialect': dialect, 'host': 'db.example', 'port': 12345, 'name': 'meeting'}
    assert 'password' not in json.dumps(source)


def test_launch_arguments_win_over_environment_and_yaml(deployment):
    config, state = deployment
    state['env']['SPRING_PROFILES_ACTIVE'] = 'mysql'
    state['args'] += ['-Dspring.profiles.active=mysql', '--spring.profiles.active=kingbase']
    state['env']['DB_PASSWORD'] = 'remote-only'
    state['env']['SPRING_DATASOURCE_PASSWORD'] = '${DB_PASSWORD}'
    source = remote.source_selection(config)
    data, target = remote.read_datasource(source)
    assert target['dialect'] == 'kingbase'
    assert data['password'] == 'remote-only'
    assert 'remote-only' not in json.dumps(source)


def test_manual_source_ignores_unrelated_profiles(deployment):
    config, _ = deployment
    source = remote.source_selection({'backend': 'ssh_mysql',
                                     'server_config': str(Path(config['config_dir']) / 'application-mysql.yml')})
    assert source['process'] is None
    assert remote.read_datasource(source)[1]['dialect'] == 'mysql'


def test_unknown_database_does_not_fall_back_to_mysql(deployment):
    config, state = deployment
    state['env']['SPRING_DATASOURCE_URL'] = 'jdbc:postgresql://db/meeting'
    with pytest.raises(RuntimeError, match='Unsupported database type'):
        remote.read_datasource(remote.source_selection(config))


def test_ambiguous_processes_are_rejected(tmp_path):
    for pid in ['1', '2']:
        folder = tmp_path / pid
        folder.mkdir()
        folder.joinpath('cmdline').write_bytes(b'java\0-jar\0db-proxy.jar\0')
    with pytest.raises(RuntimeError, match='found 2'):
        remote.find_process(tmp_path)


@pytest.mark.parametrize('args', [
    ['java', '-jar', 'db-proxy.jar'],
    ['/opt/java/bin/java', '-jar', '/deploy/db-proxy-4.40.0.5.jar'],
    ['java', '-jar', '/deploy/db-proxy-core-1.0.0-SNAPSHOT.jar'],
    ['java', '-cp', '/hst/meeting/dbproxy/lib/*', 'com.hst.dbproxy.App',
     '--spring.config.additional-location=../config/'],
])
def test_gateway_launch_styles_are_recognized(tmp_path, args):
    process = tmp_path / '123'
    process.mkdir()
    process.joinpath('cmdline').write_bytes(('\0'.join(args) + '\0').encode())
    assert remote.find_process(tmp_path) == str(process)


@pytest.mark.parametrize('args', [
    ['java', '-cp', '/lib/db-proxy.jar', 'com.example.Client'],
    ['java', '-jar', '/lib/db-proxy-interface-4.40.0.5.jar'],
    ['java', '-jar'],
    ['python3', '-c', 'com.hst.dbproxy.App'],
])
def test_non_gateway_processes_are_not_selected(args):
    assert not remote.is_gateway_process(args)


def test_classpath_deployment_uses_its_actual_config_directory(deployment):
    config, state = deployment
    state['args'] = ['java', '-cp', '/hst/meeting/dbproxy/lib/*', 'com.hst.dbproxy.App',
                     '--spring.config.additional-location=../config/']
    state['env']['SPRING_PROFILES_ACTIVE'] = 'kingbase'
    config['config_dir'] = str(Path(config['config_dir']).parent / 'old-missing-directory')
    source = remote.source_selection(config)
    assert all('old-missing-directory' not in name for name in source['config_files'])
    assert remote.read_datasource(source)[1]['dialect'] == 'kingbase'


@pytest.mark.parametrize('directory,launch', [
    ('IceDBProxy', 'jar'), ('dbproxy', 'classpath'),
])
def test_automatic_directory_follows_running_install_when_both_versions_exist(tmp_path, monkeypatch, directory, launch):
    for name,profile in [('IceDBProxy','mysql'),('dbproxy','kingbase')]:
        folder = tmp_path / name
        (folder/'config').mkdir(parents=True)
        (folder/'bin').mkdir()
        (folder/'config/application.yml').write_text('spring:\n  profiles:\n    active: '+profile+'\n', encoding='utf-8')
        (folder/('config/application-'+profile+'.yml')).write_text(
            'spring:\n  datasource:\n    url: jdbc:'+('mysql' if profile=='mysql' else 'kingbase8')+'://db/meeting\n'
            '    username: user\n    password: secret\n', encoding='utf-8')
    active = tmp_path / directory
    args = ['java','-jar','db-proxy.jar'] if launch=='jar' else ['java','-cp',str(active/'lib/*'),'com.hst.dbproxy.App']
    monkeypatch.setattr(remote,'find_process',lambda:'test-process')
    monkeypatch.setattr(remote,'read_process',lambda _: (args,{},active/'bin'))
    selected = remote.source_selection({'backend':'auto','config_dir':None})
    assert all(str(active/'config') in filename for filename in selected['config_files'])
    assert remote.read_datasource(selected)[1]['dialect'] == ('mysql' if launch=='jar' else 'kingbase')


@pytest.mark.parametrize('launch', ['jar','classpath'])
def test_deployment_can_be_inferred_from_launch_path_outside_working_directory(tmp_path, launch):
    root = tmp_path/'custom-install'
    (root/'config').mkdir(parents=True)
    (root/'config/application.yml').write_text('spring: {}\n',encoding='utf-8')
    cwd = tmp_path/'unrelated-workdir'
    cwd.mkdir()
    args = ['java','-jar',str(root/'app/db-proxy.jar')] if launch=='jar' else ['java','-cp',str(root/'lib/*'),'com.hst.dbproxy.App']
    assert remote.inferred_config_dir(args,{},cwd)==(root/'config').resolve()


def test_explicit_config_directory_supports_custom_deployments(deployment):
    config,state = deployment
    state['args']=['java','-cp','/custom/lib/*','com.hst.dbproxy.App']
    selected = remote.source_selection(config)
    assert selected['config_files'][0]==str(Path(config['config_dir'])/'application.yml')


def test_ambiguous_inferred_config_directories_require_explicit_configuration(tmp_path):
    cwd=tmp_path/'bin'
    cwd.mkdir()
    for folder in [cwd/'config',tmp_path/'config']:
        folder.mkdir()
        (folder/'application.yml').write_text('spring: {}\n',encoding='utf-8')
    with pytest.raises(RuntimeError,match='database.config_dir'):
        remote.inferred_config_dir(['java','-jar','db-proxy.jar'],{},cwd)


@pytest.mark.parametrize('url,dialect,host,port', [
    ('jdbc:mysql://single-host/meeting','mysql','single-host',3306),
    ('jdbc:mysql://single-host:22007/meeting','mysql','single-host',22007),
    ('jdbc:kingbase8://single-host/FASTMEETING','kingbase','single-host',54321),
    ('jdbc:kingbase8://single-host:54322/FASTMEETING','kingbase','single-host',54322),
])
def test_single_address_is_detected_without_a_topology_switch(deployment,url,dialect,host,port):
    config,state=deployment
    state['env']['SPRING_DATASOURCE_URL']=url
    target=remote.read_datasource(remote.source_selection(config))[1]
    assert target=={'dialect':dialect,'host':host,'port':port,'name':url.rsplit('/',1)[1]}


@pytest.mark.parametrize('authority,hosts,ports', [
    ('192.168.6.160:54321,192.168.6.161:54321', '192.168.6.160,192.168.6.161', '54321,54321'),
    ('[2001:db8::1]:54321,[2001:db8::2]:54322', '2001:db8::1,2001:db8::2', '54321,54322'),
])
def test_kingbase_cluster_preserves_all_hosts_and_primary_selection(deployment, authority, hosts, ports):
    config, state = deployment
    state['env']['SPRING_DATASOURCE_URL'] = 'jdbc:kingbase8://' + authority + '/FASTMEETING?targetServerType=master'
    target = remote.read_datasource(remote.source_selection(config))[1]
    assert target['host'] == hosts and target['port'] == ports
    assert target['session_attrs'] == 'read-write'


def test_kingbase_client_receives_primary_selection_without_credentials_in_argv(monkeypatch):
    target = {'dialect': 'kingbase', 'host': 'db1,db2', 'port': '54321,54321',
              'name': 'meeting', 'session_attrs': 'read-write'}
    monkeypatch.setattr(remote, 'read_datasource', lambda _: ({'username': 'user', 'password': 'secret'}, target))
    def run(args, **kwargs):
        assert kwargs['env']['PGTARGETSESSIONATTRS'] == 'read-write'
        assert args[args.index('-h') + 1] == 'db1,db2'
        assert args[args.index('-p') + 1] == '54321,54321'
        assert 'secret' not in ' '.join(args)
        return SimpleNamespace(returncode=0, stdout=b'oracle_available\n1\n', stderr=b'')
    monkeypatch.setattr(remote, 'command', run)
    assert remote.execute({}, target, {'container': 'client', 'client': 'ksql', 'library_path': '/lib'}, 'SELECT 1') == [{'oracle_available': '1'}]


@pytest.mark.parametrize('url,message', [
    ('jdbc:kingbase8://db:not-a-port/meeting', 'Invalid JDBC'),
    ('jdbc:kingbase8://db/meeting?targetServerType=master&targetServerType=slave', 'conflicting'),
])
def test_invalid_cluster_configuration_has_an_actionable_error(deployment, url, message):
    config, state = deployment
    state['env']['SPRING_DATASOURCE_URL'] = url
    with pytest.raises(RuntimeError, match=message):
        remote.read_datasource(remote.source_selection(config))


def test_missing_client_and_manual_backend_mismatch(deployment, monkeypatch):
    config, _ = deployment
    monkeypatch.setattr(remote, 'candidate_clients', lambda *_: iter([]))
    with pytest.raises(RuntimeError, match='No usable mysql client'):
        remote.resolve(config)
    config = dict(config, backend='ssh_kingbase', server_config=str(Path(config['config_dir']) / 'application-mysql.yml'))
    with pytest.raises(RuntimeError, match='disagrees'):
        remote.resolve(config)


def test_mysql_xml_preserves_null_literal_null_empty_unicode_and_multiline():
    text = '''<?xml version="1.0"?><resultset xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <row><field name="missing" xsi:nil="true"/><field name="literal">NULL</field>
      <field name="empty"></field><field name="value">中文,&amp;'\\
second\tline</field></row></resultset>'''
    assert remote.decode_mysql_xml(text) == [{'missing': None, 'literal': 'NULL', 'empty': '',
                                             'value': "中文,&'\\\nsecond\tline"}]


@pytest.mark.parametrize('dialect', ['mysql', 'kingbase'])
def test_client_uses_readonly_transaction_and_never_puts_password_in_argv(monkeypatch, dialect):
    target = {'dialect': dialect, 'host': 'db', 'port': 1234, 'name': 'meeting'}
    monkeypatch.setattr(remote, 'read_datasource', lambda _: ({'username': 'user', 'password': 'secret'}, target))
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        if dialect == 'mysql':
            text = '<resultset><row><field name="value">NULL</field></row></resultset>'
        else:
            marker = next(value[5:] for value in args if value.startswith('null='))
            text = 'missing,empty,value\n' + marker + ',,"中文,第一行\n第二行"\n'
        return SimpleNamespace(returncode=0, stdout=text.encode(), stderr=b'')
    monkeypatch.setattr(remote, 'command', run)
    result = remote.execute({}, target, {'container': 'client', 'client': 'db-client', 'library_path': '/lib'}, 'SELECT value FROM example')
    args, options = calls[0]
    assert 'secret' not in ' '.join(args)
    query = options['input'].decode()
    assert 'TRANSACTION READ ONLY;' in query and query.endswith('; ROLLBACK;')
    if dialect == 'mysql':
        assert options['env']['MYSQL_PWD'] == 'secret'
        assert result == [{'value': 'NULL'}]
    else:
        assert options['env']['PGPASSWORD'] == 'secret'
        assert result == [{'missing': None, 'empty': '', 'value': '中文,第一行\n第二行'}]


def test_query_error_redacts_password(monkeypatch):
    target = {'dialect': 'mysql', 'host': 'db', 'port': 3306, 'name': 'meeting'}
    monkeypatch.setattr(remote, 'read_datasource', lambda _: ({'username': 'u', 'password': 'secret'}, target))
    monkeypatch.setattr(remote, 'command', lambda *_args, **_kw: SimpleNamespace(returncode=1, stderr=b'password=secret'))
    result = remote.main({'operation': 'fetch', 'resolved': {'source': {}, 'target': target,
                          'client': {'container': None, 'client': 'mysql'}}, 'sql': 'SELECT 1'})
    assert 'secret' not in result['error'] and '[REDACTED]' in result['error']


def test_discovery_is_cached_and_automatic_queries_use_the_detected_dialect(monkeypatch):
    oracle = ReadonlyDatabase({'backend': 'auto'})
    calls = []
    def rpc(request):
        calls.append(request)
        return {'backend': 'ssh_kingbase'} if request['operation'] == 'resolve' else []
    monkeypatch.setattr(oracle, '_remote', rpc)
    oracle.fetch('SELECT name FROM example WHERE name=%s', ["中文'\\"])
    oracle.fetch('SELECT 1')
    assert sum(r['operation'] == 'resolve' for r in calls) == 1
    assert 'CONVERT(0x' not in calls[1]['sql']
    assert "中文''\\" in calls[1]['sql']


@pytest.mark.parametrize('backend,epoch,metadata', [('ssh_mysql', 'UNIX_TIMESTAMP', 'information_schema'),
                                                 ('ssh_kingbase', 'EXTRACT(EPOCH', 'pg_')])
def test_time_length_and_partition_sql_follow_resolved_database(backend, epoch, metadata):
    oracle = ReadonlyDatabase({'backend': backend})
    queries = []
    oracle.fetch = lambda sql, params=(): queries.append((sql, params)) or []
    assert epoch in oracle.epoch_expression('UpdateTime')
    oracle.text_column_length('t_userinfo', 'Sex')
    oracle.room_log_tables()
    assert all(metadata in sql for sql, _ in queries)
    assert queries[0][1] == ['t_userinfo', 'Sex']


@pytest.mark.parametrize('room,global_value,expected', [(0, 1, 0), (None, 1, 1), (1, None, 1)])
def test_recording_expectation_prefers_room_then_global(room, global_value, expected):
    runtime = GatewayRuntime({})
    calls = []
    def fetch(sql, params):
        calls.append((sql, params))
        if 't_roominfo' in sql:
            return [{'RoomID': '10001'}]
        value = room if params == [10001] else global_value
        return [] if value is None else [{'global_switch': str(value)}]
    runtime.database = SimpleNamespace(fetch=fetch)
    assert runtime.record_switch(10001) == expected
    assert len(calls) == (3 if room is None else 2)


@pytest.mark.parametrize('exists', [True, False])
def test_missing_recording_settings_or_room_is_explicitly_blocked(exists):
    runtime = GatewayRuntime({})
    runtime.database = SimpleNamespace(fetch=lambda sql, _: [{'RoomID': '10001'}] if exists and 't_roominfo' in sql else [])
    with pytest.raises(PrerequisiteBlocked):
        runtime.record_switch(10001)


@pytest.mark.parametrize('kind', ['service', 'route', 'master'])
def test_business_resource_conflict_blocks_writes(kind):
    runtime = GatewayRuntime({'test_master_server_type': 54013})
    runtime._env = {'test_service_app_id': 54011, 'test_route_app_id': 54012, 'primary': {'device_id': 'MainDev'}}
    def fetch(sql, _):
        if kind == 'service' and 't_serviceinfo' in sql:
            return [{'ServiceName': 'FMWebProxy'}]
        if kind == 'route' and 't_roomroute' in sql:
            return [{'RoomID': 10001}]
        if kind == 'master' and 't_master_slave' in sql:
            return [{'devid': 'license'}]
        return []
    runtime.database = SimpleNamespace(fetch=fetch)
    with pytest.raises(RuntimeError, match={'service': 'test_service_app_id', 'route': 'test_route_app_id', 'master': 'test_master_server_type'}[kind]):
        runtime.validate_test_resources()
    assert not runtime._resources_validated


def test_own_disabled_service_record_can_be_reused():
    runtime = GatewayRuntime({})
    runtime._env = {'test_service_app_id': 54011, 'test_route_app_id': 54012, 'primary': {'device_id': 'MainDev'}}
    runtime.database = SimpleNamespace(fetch=lambda sql, _: [{'ServiceName': 'autotest_updated'}] if 't_serviceinfo' in sql else [])
    runtime.validate_test_resources()
    assert runtime._resources_validated


def test_database_preflight_failure_returns_false_and_closes_runtime(monkeypatch):
    import common.runtime
    import runner
    closed = []
    class Runtime:
        def __init__(self, profile):
            pass
        def preflight(self, scope):
            raise RuntimeError('No usable database client')
        def close(self):
            closed.append(True)
    monkeypatch.setattr(common.runtime, 'GatewayRuntime', Runtime)
    assert runner.preflight({'scope': 'global'}) is False
    assert closed == [True]


def test_explicit_recording_override_does_not_query_expected_value():
    runtime = GatewayRuntime({'primary_device_id': 'MainDev', 'record_global_switch': 1})
    runtime.query = lambda cls, method, params: {'data': [{'devId': 'MainDev', 'devNodeId': 'node'}]} if method == 'checkDevList' else {'data': []}
    runtime.database = SimpleNamespace(fetch=lambda *_: pytest.fail('Explicit expected value must not query the database'))
    assert runtime.env['record_global_switch'] == 1


def test_failed_preflight_stops_before_pytest_and_preserves_previous_report(monkeypatch, tmp_path):
    import runner
    import common.runtime
    previous = tmp_path / 'html'
    previous.mkdir()
    previous.joinpath('index.html').write_text('previous report', encoding='utf-8')
    monkeypatch.setattr(runner.sys, 'argv', ['run.py'])
    monkeypatch.setattr(common.runtime, 'load_profile', lambda *_: {'database': {}, 'scope': 'global'})
    monkeypatch.setattr(runner, 'HTML_DIR', previous)
    monkeypatch.setattr(runner, 'setup_logging', lambda: tmp_path / 'run.log')
    monkeypatch.setattr(runner, 'banner', lambda: None)
    monkeypatch.setattr(runner, 'preflight', lambda _: False)
    monkeypatch.setattr(runner, 'run_pytest', lambda *_: pytest.fail('pytest must not run'))
    assert runner.main() == runner.EXIT_PREFLIGHT_FAILED
    assert previous.joinpath('index.html').read_text(encoding='utf-8') == 'previous report'


def test_unknown_manual_backend_is_rejected_without_connecting():
    with pytest.raises(RuntimeError, match='Unsupported database backend'):
        ReadonlyDatabase({'backend': 'unknown'}).fetch('SELECT 1')


@pytest.mark.parametrize('has_visibility', [True, False])
def test_preparation_credential_query_adapts_to_schema_without_leaking_secrets(has_visibility):
    from common.user_fixtures import UserPreparationApi
    queries = []
    def fetch(sql, params):
        queries.append(sql)
        return [{'account': 'test-account', 'secret': 'test-secret'}]
    database = SimpleNamespace(table_columns=lambda _: {'is_show'} if has_visibility else set(), fetch=fetch)
    runtime = SimpleNamespace(database=database, profile={'host': 'test-host'})
    api = UserPreparationApi(runtime)
    assert api.account == 'test-account'
    assert ('is_show=0' in queries[0]) == has_visibility
    assert 'test-secret' not in queries[0]


def test_multiple_active_preparation_accounts_require_explicit_selection():
    from common.user_fixtures import UserPreparationApi
    database = SimpleNamespace(table_columns=lambda _: set(), fetch=lambda *_: [
        {'account': 'one', 'secret': 'secret1'}, {'account': 'two', 'secret': 'secret2'}])
    with pytest.raises(PrerequisiteBlocked, match='exactly one'):
        UserPreparationApi(SimpleNamespace(database=database, profile={'host': 'test-host'}))


@pytest.mark.parametrize('method', ['devUnRegister', 'devRegister', 'devUpdate2'])
def test_device_cleanup_restores_routes_after_registration_side_effects(method):
    from common.scenarios import Scenario
    original = {'RoomID': '10000', 'SvrAppID': '11', 'SvrNodeID': 'NID:n$DID:other-device',
                'SvrAddr': 'TCP:original:28091;', 'SvrAuthCode': 'original-auth'}
    stored = [dict(original)]
    device = {'DevID': 'meeting2', 'DevIP': 'original', 'DevType': '1', 'CurOnline': '0',
              'CurBandwidth': '0', 'CurRoomCount': '0', 'CPULoad': '1', 'DevStatus': '1'}
    env = {'secondary': {'device_id': 'meeting2', 'verify_code': 'test', 'route_node': 'NID:n$DID:meeting2'}}
    scenario = Scenario(SimpleNamespace(env=env), {'case_id': 'unregister', 'fixture': 'device',
                        'topology': 'dual', 'method': method, 'requires': []})
    def rows(sql, params=()):
        if 't_devinfo' in sql:
            return [dict(device)]
        if 't_roomroute' in sql:
            if 'WHERE SvrNodeID=' in sql:
                return [dict(r) for r in stored if r['SvrNodeID'] == params[0]]
            return [dict(r) for r in stored]
        return []
    calls = []
    def api(cls, method, params, **kwargs):
        calls.append(method)
        if method == 'devRegister':
            stored.clear()
        if method == 'replaceRoomRoute':
            stored[:] = [{'RoomID': str(params['roomId']), 'SvrAppID': str(params['svrAppId']),
                          'SvrNodeID': params['svrNodeId'], 'SvrAddr': params['svrAddress'], 'SvrAuthCode': params['svrAuthCode']}]
        return {}
    scenario.rows, scenario.api = rows, api
    scenario.prepare()
    stored.clear()
    scenario.close()
    assert stored == [original]
    assert calls.count('replaceRoomRoute') == 1
