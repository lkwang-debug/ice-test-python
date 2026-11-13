from types import SimpleNamespace
import pytest
from common.gateway_response import decode_response


def response(code=0, raw=b""):
    return SimpleNamespace(resultCode=code, result=raw)


def test_empty_success_has_no_fake_business_payload():
    r = decode_response(0, response(), "r", 1)
    assert r.payload is None and r.legacy() == {"resultCode": 0}


def test_empty_payload_cannot_hide_response_error():
    r = decode_response(0, response(4107), "r", 1)
    assert r.invoke_code == 0 and r.response_code == 4107
    assert r.legacy()["resultCode"] == 4107


def test_payload_code_cannot_replace_envelope_code():
    r = decode_response(0, response(4107, b'{"resultCode":0,"result":0}'), "r", 1)
    assert r.payload["resultCode"] == 0
    assert r.legacy()["resultCode"] == 4107


@pytest.mark.parametrize("raw", [b'{"broken":', b'garbage', b'\xff'])
def test_malformed_response_is_not_success(raw):
    r = decode_response(0, response(0, raw), "r", 1)
    assert r.error and r.legacy()["resultCode"] != 0


def test_invocation_error_and_response_code_are_preserved():
    r = decode_response(4107, response(0), "r", 1)
    assert r.invoke_code == 4107 and r.response_code == 0
    assert r.legacy()["resultCode"] == 4107


def test_missing_envelope_is_a_client_error():
    assert decode_response(0, None, "r", 1).error
