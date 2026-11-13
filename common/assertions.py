"""Small, strict assertion vocabulary; no recursive global field search."""
import re

MISSING = object()
OPS = {"eq", "type", "exists", "not_null", "not_empty", "contains_record", "length", "range", "not_in"}
TYPES = {"int": int, "number": (int, float), "string": str, "bool": bool,
         "object": dict, "array": list, "null": type(None)}
PATH = re.compile(r"^\$(?:\.[A-Za-z_][A-Za-z_0-9]*|\[\d+\])*$")


def get_path(value, path):
    if not isinstance(path, str) or not PATH.fullmatch(path):
        raise ValueError("Invalid assertion path: %r" % path)
    for token in re.findall(r"\.([A-Za-z_][A-Za-z_0-9]*)|\[(\d+)\]", path[1:]):
        key, index = token
        if key:
            if not isinstance(value, dict) or key not in value:
                return MISSING
            value = value[key]
        else:
            if not isinstance(value, list) or int(index) >= len(value):
                return MISSING
            value = value[int(index)]
    return value


def strict_equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(strict_equal(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(strict_equal(a, b) for a, b in zip(actual, expected))
    return actual == expected


def subset(actual, expected):
    """A subset matches in one object, preserving explicit nesting and types."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and subset(actual[k], v) for k, v in expected.items())
    return strict_equal(actual, expected)


def validate_assertions(assertions):
    if not isinstance(assertions, list):
        raise ValueError("assertions must be a JSON array")
    for rule in assertions:
        if not isinstance(rule, dict) or rule.get("op") not in OPS:
            raise ValueError("Unknown assertion operation: %r" % rule)
        if not PATH.fullmatch(str(rule.get("path", ""))):
            raise ValueError("Invalid assertion path: %r" % rule)
        op = rule["op"]
        if op not in {"exists", "not_null", "not_empty"} and "value" not in rule:
            raise ValueError("Assertion requires value: %r" % rule)
        if op == "type" and rule["value"] not in TYPES:
            raise ValueError("Unknown assertion type")
        if op == "contains_record" and not isinstance(rule["value"], dict):
            raise ValueError("contains_record requires an object")
        if op == "not_in" and not isinstance(rule["value"], list):
            raise ValueError("not_in requires an array")
        if op == "length" and (type(rule["value"]) is not int or rule["value"] < 0):
            raise ValueError("length requires a nonnegative integer")
        if op == "range" and (not isinstance(rule["value"], list) or len(rule["value"]) != 2
                              or any(type(v) not in (int, float) for v in rule["value"])
                              or rule["value"][0] > rule["value"][1]):
            raise ValueError("range requires ordered numeric bounds")
        if "count" in rule and (type(rule["count"]) is not int or rule["count"] < 0 or op != "contains_record"):
            raise ValueError("count is only valid for contains_record")


def assert_rules(value, assertions):
    validate_assertions(assertions)
    for rule in assertions:
        actual = get_path(value, rule["path"])
        op, expected = rule["op"], rule.get("value")
        if op == "exists":
            ok = (actual is not MISSING) == rule.get("value", True)
        elif actual is MISSING:
            ok = False
        elif op == "eq":
            ok = strict_equal(actual, expected)
        elif op == "not_in":
            ok = not any(strict_equal(actual, item) for item in expected)
        elif op == "type":
            ok = type(actual) in ((int, float) if expected == "number" else (TYPES[expected],))
        elif op == "not_null":
            ok = actual is not None
        elif op == "not_empty":
            ok = isinstance(actual, (str, list, dict)) and len(actual) > 0
        elif op == "contains_record":
            matches = [item for item in actual if subset(item, expected)] if isinstance(actual, list) else []
            ok = len(matches) == rule["count"] if "count" in rule else bool(matches)
        elif op == "length":
            ok = isinstance(actual, (str, list, dict)) and len(actual) == expected
        else:
            ok = type(actual) in (int, float) and expected[0] <= actual <= expected[1]
        shown = "<missing>" if actual is MISSING else repr(actual)
        assert ok, "%s %s %r: actual=%s" % (rule["path"], op, expected, shown)


def assert_expected(expected, actual):
    """Compatibility assertion checks every supplied field at its exact location."""
    assert isinstance(expected, dict), "expected must be an object"
    for key, wanted in expected.items():
        found = get_path(actual, "$." + key)
        if wanted == "!null":
            assert found is not MISSING and found is not None, "%s must exist and not be null" % key
        else:
            assert found is not MISSING and subset(found, wanted), "%s expected=%r actual=%r" % (key, wanted, found)
