"""Keep request evidence useful without persisting authentication secrets."""
SECRET_KEYS = {"password", "verifypass", "verifycode", "nodecheckcode", "authseq", "upassword"}


def redact(value):
    if isinstance(value, dict):
        return {k: "<redacted>" if str(k).lower() in SECRET_KEYS else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value
