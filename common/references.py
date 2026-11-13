"""Scenario-local, type-preserving references; intentionally no global cache."""
import re
from common.cases import validate_references

TOKEN = re.compile(r"\$\{((?:env|fixture|case)\.[A-Za-z_0-9.]+)\}")


def resolve(value, context):
    if isinstance(value, dict):
        return {k: resolve(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, context) for v in value]
    if not isinstance(value, str):
        return value
    validate_references(value)

    def lookup(match):
        item = context
        for part in match.group(1).split("."):
            if not isinstance(item, dict) or part not in item:
                raise ValueError("Scenario reference not available: " + match.group(1))
            item = item[part]
        return item

    full = TOKEN.fullmatch(value)
    if full:
        return lookup(full)
    return TOKEN.sub(lambda m: str(lookup(m)), value)
