import pytest
from common.assertions import assert_rules, assert_expected, validate_assertions


def test_conditions_cannot_match_different_devices():
    value = {"data": [{"devId": "MainDev", "online": "0"}, {"devId": "meeting2", "online": "1"}]}
    with pytest.raises(AssertionError):
        assert_rules(value, [{"path": "$.data", "op": "contains_record", "value": {"devId": "MainDev", "online": "1"}}])


@pytest.mark.parametrize("value", [[], {}, ""])
def test_empty_is_not_nonempty(value):
    with pytest.raises(AssertionError):
        assert_rules({"v": value}, [{"path": "$.v", "op": "not_empty"}])


@pytest.mark.parametrize("actual,expected", [(True, 1), (False, 0), ("1", 1), (1.0, 1)])
def test_equality_does_not_coerce_types(actual, expected):
    with pytest.raises(AssertionError):
        assert_rules({"v": actual}, [{"path": "$.v", "op": "eq", "value": expected}])


def test_missing_null_and_empty_are_distinct():
    assert_rules({"v": None}, [{"path": "$.v", "op": "eq", "value": None}])
    with pytest.raises(AssertionError):
        assert_rules({}, [{"path": "$.v", "op": "eq", "value": None}])
    assert_rules({"v": []}, [{"path": "$.v", "op": "eq", "value": []}])
    with pytest.raises(AssertionError):
        assert_rules({"v": None}, [{"path": "$.v", "op": "eq", "value": []}])


def test_business_fields_are_never_silently_ignored():
    with pytest.raises(AssertionError):
        assert_expected({"resultCode": 0, "result": 0}, {"resultCode": 0, "result": -1})
    with pytest.raises(AssertionError):
        assert_expected({"result": 0}, {"nested": {"result": 0}})


def test_no_business_fields_are_invented_for_code_only_case():
    assert_expected({"resultCode": 0}, {"resultCode": 0})


def test_unique_record_match_and_reordered_results():
    rule = [{"path": "$.data", "op": "contains_record", "value": {"id": 2}, "count": 1}]
    assert_rules({"data": [{"id": 2}, {"id": 1}]}, rule)
    with pytest.raises(AssertionError):
        assert_rules({"data": [{"id": 2}, {"id": 2}]}, rule)


@pytest.mark.parametrize("rule", [{"path": "data", "op": "eq", "value": 1},
                                   {"path": "$.data", "op": "anything"},
                                   {"path": "$", "op": "type", "value": "unknown"},
                                   {"path": "$", "op": "range", "value": [4, 1]}])
def test_invalid_assertions_are_configuration_errors(rule):
    with pytest.raises(ValueError):
        validate_assertions([rule])
