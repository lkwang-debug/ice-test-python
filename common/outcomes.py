"""Explicit run outcomes that must never be counted as business passes."""
import json
import allure
import pytest


class PrerequisiteBlocked(RuntimeError):
    """An applicable scenario cannot run because its real data is unavailable."""


def label_outcome(kind, reason, evidence=None):
    allure.dynamic.label("outcome_type", kind)
    allure.attach(json.dumps({"outcome": kind, "reason": reason, "evidence": evidence},
                             ensure_ascii=False, indent=2, default=str),
                  name="Outcome classification", attachment_type=allure.attachment_type.JSON)


def blocked(reason, evidence=None):
    label_outcome("prerequisite_blocked", reason, evidence)
    raise PrerequisiteBlocked(reason)


def unsupported(api, evidence):
    reason = "Target version does not support " + api
    label_outcome("version_unsupported", reason, evidence)
    pytest.skip(reason)


def contract_review(reason, observations):
    label_outcome("contract_review", reason, observations)
    # XFAIL records an executed unresolved rule; it is neither a pass nor an
    # unexecuted capability skip. The observations include response/state checks.
    pytest.xfail("Contract review: " + reason)
