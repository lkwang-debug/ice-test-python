"""Regression coverage for NULL snapshots, membership and independent device reads."""
import copy
from types import SimpleNamespace

import pytest

from common.outcomes import PrerequisiteBlocked
from common.scenarios import Scenario
from common.runtime import GatewayRuntime


def parameter_scenario(initial):
    stored = [{'ParamName': 'emailhost', 'ParamValue': initial}]
    calls = []
    scenario = Scenario(SimpleNamespace(env={}), {'case_id': 'parameter', 'fixture': 'system_param',
                        'params': {'paramName': 'emailhost'}, 'requires': []})
    scenario.rows = lambda *_: copy.deepcopy(stored)
    def api(cls, method, params):
        calls.append((method, params.copy()))
        if method == 'updateSystemParam':
            if stored:
                stored[0]['ParamValue'] = params['paramValue']
            return {}
        if not stored or stored[0]['ParamValue'] is None:
            return {}
        return {'paramValue': stored[0]['ParamValue']}
    scenario.api = api
    return scenario, stored, calls


@pytest.mark.parametrize('initial', [None, '', 'smtp.example.invalid'])
@pytest.mark.parametrize('updated', [None, ''])
def test_parameter_snapshots_preserve_null_and_empty_through_api_cleanup(initial, updated):
    scenario, stored, calls = parameter_scenario(initial)
    scenario.prepare()
    assert not calls  # Preparation uses an independent SELECT, not the lossy API response.
    assert scenario.context['fixture']['original_value'] == initial
    scenario.api('device', 'updateSystemParam', {'paramName': 'emailhost', 'paramValue': updated})
    scenario.verify_state('system_param', {'paramName': 'emailhost', 'paramValue': updated}, None)
    scenario.close()
    assert stored == [{'ParamName': 'emailhost', 'ParamValue': initial}]
    assert any(method == 'updateSystemParam' and params['paramValue'] == initial for method, params in calls)


@pytest.mark.parametrize('count', [0, 2])
def test_missing_or_ambiguous_parameter_blocks_before_mutation(count):
    scenario, stored, calls = parameter_scenario(None)
    stored[:] = [{'ParamName': 'emailhost', 'ParamValue': None} for _ in range(count)]
    with pytest.raises(PrerequisiteBlocked, match='exactly one'):
        scenario.prepare()
    assert not calls and not scenario.cleanups


def test_empty_api_object_does_not_hide_a_deleted_parameter_row():
    scenario, stored, _ = parameter_scenario(None)
    scenario.prepare()
    stored.clear()
    with pytest.raises(AssertionError, match='row/value'):
        scenario.verify_state('system_param', {'paramName': 'emailhost', 'paramValue': None}, None)


def test_parameter_cleanup_checks_database_not_just_empty_api_response():
    scenario, stored, _ = parameter_scenario(None)
    scenario.prepare()
    stored.clear()
    with pytest.raises(RuntimeError, match='snapshot did not restore'):
        scenario.close()


def test_missing_room_member_blocks_before_meeting_log_or_start():
    scenario = Scenario(SimpleNamespace(env={'room_id': 10011, 'user_id': 21}),
                        {'case_id': 'meeting', 'fixture': 'meeting', 'requires': [], 'method': 'confRoomStart'})
    scenario.rows = lambda sql, _: [{'RoomID': 10011, 'CurUserCount': 0, 'CurrentServiceID': 0}] if 't_roominfo' in sql else []
    scenario.api = lambda *_args, **_kwargs: pytest.fail('No gateway write is allowed before the member check')
    with pytest.raises(PrerequisiteBlocked, match='member'):
        scenario.prepare()
    assert not scenario.cleanups


def test_valid_member_returns_independent_restore_snapshot():
    scenario = Scenario(SimpleNamespace(env={'room_id': 10011, 'user_id': 21}), {'case_id': 'member'})
    row = {'UserID': '21', 'UserOnline': '0'}
    scenario.rows = lambda *_: [row.copy()]
    assert scenario.require_room_membership() == [row]


def device_list_scenario():
    env = {'topology': 'dual', 'primary': {'device_id': 'MainDev'}, 'secondary': {'device_id': 'meeting2'}}
    stored = [{'DevID': device, 'DevName': device, 'DevType': '1', 'DevIP': address}
              for device, address in [('MainDev', '192.0.2.1'), ('meeting2', '192.0.2.2')]]
    response = [{'devId': row['DevID'], 'devName': row['DevName'], 'devType': row['DevType'],
                 'devIp': row['DevIP'], 'cpuLoad': 4} for row in stored]
    scenario = Scenario(SimpleNamespace(env=env), {'case_id': 'device-list'})
    scenario.rows = lambda *_: copy.deepcopy(stored)
    result = SimpleNamespace(legacy=lambda: {'data': response})
    return scenario, response, result


@pytest.mark.parametrize('cpu', [0, 4, 10, 99, 100])
def test_device_list_checks_live_contract_without_previous_case_cpu_dependency(cpu):
    scenario, response, result = device_list_scenario()
    response[1]['cpuLoad'] = cpu
    scenario.verify_state('device_list', {}, result)


@pytest.mark.parametrize('cpu', [None, True, '10', -1, 101, 2.5])
def test_device_list_still_rejects_invalid_cpu_values(cpu):
    scenario, response, result = device_list_scenario()
    response[1]['cpuLoad'] = cpu
    with pytest.raises(AssertionError, match='CPU'):
        scenario.verify_state('device_list', {}, result)


def test_device_list_still_checks_database_identity():
    scenario, response, result = device_list_scenario()
    response[1]['devName'] = 'wrong-device-name'
    with pytest.raises(AssertionError, match='identities'):
        scenario.verify_state('device_list', {}, result)


@pytest.mark.parametrize('duplicate', [True, False])
def test_device_list_requires_each_configured_device_exactly_once(duplicate):
    scenario, response, result = device_list_scenario()
    if duplicate:
        response.append(response[1].copy())
    else:
        response.pop()
    with pytest.raises(AssertionError, match='exactly once'):
        scenario.verify_state('device_list', {}, result)


@pytest.mark.parametrize('value,wanted', [('1',True),('0',False),('t',True),('f',False),('true',True),(None,False)])
def test_extended_recording_expectation_comes_from_database(value,wanted):
    runtime=GatewayRuntime({})
    runtime.database=SimpleNamespace(table_columns=lambda _: {'enable_ext_full_record'},
                                     fetch=lambda *_: [{'enable_ext_full_record':value}])
    assert runtime.record_extra_switch(10013) is wanted


def test_extended_recording_uses_global_only_when_room_row_missing():
    runtime=GatewayRuntime({});calls=[]
    def fetch(sql,params):
        calls.append(params)
        return [] if params==[10013] else [{'enable_ext_full_record':'0'}]
    runtime.database=SimpleNamespace(table_columns=lambda _: {'enable_ext_full_record'},fetch=fetch)
    assert runtime.record_extra_switch(10013) is False
    assert calls==[[10013],[0]]


def test_legacy_recording_schema_without_extra_flag_keeps_documented_default():
    runtime=GatewayRuntime({})
    runtime.database=SimpleNamespace(table_columns=lambda _: set(),fetch=lambda *_: pytest.fail('Missing column must not be queried'))
    assert runtime.record_extra_switch(10013) is False
