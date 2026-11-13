"""Decode the ICE envelope without confusing invocation and business results."""
from dataclasses import dataclass
from typing import Any, Optional
import json


@dataclass(frozen=True)
class GatewayResult:
    invoke_code: Optional[int]
    response_code: Optional[int]
    payload: Any
    raw_result: bytes
    request_id: str
    elapsed_ms: float
    error: Optional[str] = None

    def legacy(self):
        """Keep method.py's dict API; envelope metadata remains on the result."""
        code = self.invoke_code if self.invoke_code not in (None, 0) else self.response_code
        if self.error:
            return {"resultCode": code if code not in (None, 0) else -999,
                    "message": self.error}
        data = dict(self.payload) if isinstance(self.payload, dict) else {}
        if self.payload is not None and not isinstance(self.payload, dict):
            data["data"] = self.payload
        data["resultCode"] = code
        return data

    def evidence(self):
        return {"invoke_code": self.invoke_code, "response_code": self.response_code,
                "payload": self.payload, "raw_result": self.raw_result.decode("utf-8", "replace"),
                "request_id": self.request_id, "elapsed_ms": self.elapsed_ms, "error": self.error}


def decode_response(code, response, request_id, elapsed_ms):
    raw = bytes(response.result or b"") if response is not None else b""
    response_code = getattr(response, "resultCode", None)
    try:
        if response is None:
            raise ValueError("ICE response envelope is missing")
        if type(code) is not int or type(response_code) is not int:
            raise ValueError("ICE envelope codes must be integers")
        text = raw.decode("utf-8").strip()
        # An empty wire payload is legal. Do not invent data="" or business result=0.
        if not text:
            payload = None
        elif text.lower() in ("ok", "success"):
            payload = text
        else:
            payload = json.loads(text)
        return GatewayResult(code, response_code, payload, raw, request_id, elapsed_ms)
    except (ValueError, TypeError, UnicodeError) as exc:
        return GatewayResult(code, response_code, None, raw, request_id, elapsed_ms,
                             "Response decoding failed: " + str(exc))
