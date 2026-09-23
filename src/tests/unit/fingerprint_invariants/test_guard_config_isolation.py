#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Guard the invariant that a guard write fully determines the scanner's config.

The fingerprint write path merges field by field, so a payload that omits a
field leaves it at whatever is already stored. Because disable_all_guards only
turns scanners off, a field set by one test survives into the next test and into
the next run of the suite: the same guard test then passes or fails on run order
alone (a leftover regex is_blocked=False makes a banned pattern allowed, a
leftover sentiment threshold=0.9 makes a neutral question blocked). The
per-scanner functional tests cannot catch this — they assert the scanner's
behaviour, and the inherited field is invisible to them.

These tests assert on the outgoing payload instead: every field the scanner's
value model declares must be present, so a helper that starts sending partial
writes fails here rather than intermittently in e2e. The helpers make their
requests through the requests library, so the HTTP call is captured at that
seam; no cluster is contacted.
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.e2e.helpers.fingerprint_api_helper import FingerprintApiHelper
from tests.e2e.helpers.guard_helper import (
    GUARD_PARAMS_MODELS,
    GUARD_READ_FIELDS,
    GuardHelper,
    GuardType,
)

# Scanners whose omitted fields silently invert or retune what the guard does,
# which is what made the guard failures nondeterministic: regex.is_blocked flips
# patterns between 'bad' and 'good', sentiment.threshold retunes what counts as
# negative, ban_substrings.contains_all switches OR to AND.
_INPUT_SCANNERS = ["regex", "sentiment", "ban_substrings", "code", "toxicity",
                   "prompt_injection", "token_limit", "ban_topics"]
_OUTPUT_SCANNERS = ["regex", "sentiment", "ban_substrings", "toxicity"]
_DATAPREP_SCANNERS = ["ban_substrings", "regex", "toxicity"]


class _StubKeycloak:
    """Minimal keycloak stand-in so the helper can build auth headers offline."""

    access_token = "stub-token"

    def get_access_token(self, as_user=False):
        return "stub-token"


def _expected_fields(guard_type, scanner):
    """Returns every field name the scanner's value model declares."""
    field = GUARD_PARAMS_MODELS[guard_type].model_fields[scanner]
    scanner_model = field.annotation.__args__[0]
    return set(scanner_model.model_fields)


def _emitted_scanner_config(post_mock, guard_type, scanner):
    """Returns the scanner config the helper put in its single POST body."""
    assert post_mock.call_count == 1, "Expected exactly one change_arguments POST"
    body = post_mock.call_args.kwargs.get("json")
    assert body is not None, "change_arguments POST was made without a JSON body"
    groups = [item for item in body if item["name"] == guard_type.value]
    assert groups, f"POST body carried no '{guard_type.value}' group; body was {body}"
    return groups[0]["data"][scanner]


def _assert_fully_specified(guard_type, scanner, emitted):
    missing = _expected_fields(guard_type, scanner) - set(emitted)
    assert not missing, (
        f"Write for '{guard_type.value}/{scanner}' omitted {sorted(missing)}, so those "
        f"fields keep whatever a previous test or run stored. Send the scanner's "
        f"full config; emitted keys were {sorted(emitted)}")


@pytest.mark.parametrize("scanner", _INPUT_SCANNERS)
def test_input_guard_setup_sends_every_field(scanner):
    """An input guard write must specify every field, not only the ones a test sets."""
    helper = FingerprintApiHelper(_StubKeycloak())
    guard_helper = GuardHelper(MagicMock(), helper)
    with patch("tests.e2e.helpers.fingerprint_api_helper.requests.post") as post:
        post.return_value = MagicMock(status_code=200)
        guard_helper.setup(GuardType.INPUT, scanner, {"enabled": True})
        emitted = _emitted_scanner_config(post, GuardType.INPUT, scanner)

    _assert_fully_specified(GuardType.INPUT, scanner, emitted)


@pytest.mark.parametrize("scanner", _OUTPUT_SCANNERS)
def test_output_guard_setup_sends_every_field(scanner):
    """An output guard write must specify every field too."""
    helper = FingerprintApiHelper(_StubKeycloak())
    guard_helper = GuardHelper(MagicMock(), helper)
    with patch("tests.e2e.helpers.fingerprint_api_helper.requests.post") as post:
        post.return_value = MagicMock(status_code=200)
        guard_helper.setup(GuardType.OUTPUT, scanner, {"enabled": True})
        emitted = _emitted_scanner_config(post, GuardType.OUTPUT, scanner)

    _assert_fully_specified(GuardType.OUTPUT, scanner, emitted)


@pytest.mark.parametrize("scanner", _DATAPREP_SCANNERS)
def test_dataprep_guard_setup_sends_every_field(scanner):
    """A dataprep guard write is merged the same way, so it must be complete too."""
    helper = FingerprintApiHelper(_StubKeycloak())
    guard_helper = GuardHelper(MagicMock(), helper)
    with patch("tests.e2e.helpers.fingerprint_api_helper.requests.post") as post:
        post.return_value = MagicMock(status_code=200)
        guard_helper.setup_dataprep(scanner, {"enabled": True})
        emitted = _emitted_scanner_config(post, GuardType.DATAPREP, scanner)

    _assert_fully_specified(GuardType.DATAPREP, scanner, emitted)


def test_guard_setup_keeps_the_values_the_test_asked_for():
    """Defaults must fill only the gaps, never override what the test set."""
    helper = FingerprintApiHelper(_StubKeycloak())
    guard_helper = GuardHelper(MagicMock(), helper)
    requested = {"enabled": True, "is_blocked": False, "patterns": [r"\d{5}"]}
    with patch("tests.e2e.helpers.fingerprint_api_helper.requests.post") as post:
        post.return_value = MagicMock(status_code=200)
        guard_helper.setup(GuardType.INPUT, "regex", requested)
        emitted = _emitted_scanner_config(post, GuardType.INPUT, "regex")

    for key, value in requested.items():
        assert emitted[key] == value, (
            f"Default for '{key}' overrode the value the test set: "
            f"expected {value!r}, got {emitted[key]!r}")


def test_setup_refuses_the_dataprep_guard():
    """setup writes to chatqa, so the dataprep guard must not go through it.

    A dataprep config written to the chatqa scope is stored successfully and
    never read by the ingestion-time guard, so the mistake would surface as a
    guard that silently does nothing rather than as a failed write.
    """
    guard_helper = GuardHelper(MagicMock(), MagicMock())
    with pytest.raises(AssertionError, match="setup_dataprep"):
        guard_helper.setup(GuardType.DATAPREP, "ban_substrings", {"enabled": True})


@pytest.mark.parametrize("guard_type, scanner", [
    (GuardType.INPUT, "regex"),
    (GuardType.INPUT, "sentiment"),
    (GuardType.OUTPUT, "regex"),
])
def test_disable_all_guards_resets_fields_not_just_enabled(guard_type, scanner):
    """Disabling must clear the tuned fields, or the next run inherits them.

    A disable that writes only ``enabled`` leaves a threshold or an is_blocked
    from the finished test in the store, which is exactly how a passing suite
    poisons the next one.
    """
    fingerprint = MagicMock()
    # disable_all_guards discovers the scanners to reset from the stored config.
    fingerprint.read_config.side_effect = lambda params_key, **kwargs: MagicMock(
        status_code=200,
        json=lambda: {"values": {
            GUARD_READ_FIELDS[GuardType(params_key)]: {
                s: {"enabled": True} for s in (
                    _INPUT_SCANNERS if params_key == GuardType.INPUT.value
                    else _OUTPUT_SCANNERS)}}})
    guard_helper = GuardHelper(MagicMock(), fingerprint)

    with patch("tests.e2e.helpers.guard_helper.time.sleep"):
        guard_helper.disable_all_guards()

    bodies = [call.args[0] for call in fingerprint.change_arguments.call_args_list]
    groups = [item for body in bodies for item in body if item["name"] == guard_type.value]
    assert groups, f"disable_all_guards wrote no '{guard_type.value}' group"
    emitted = groups[0]["data"][scanner]

    assert emitted["enabled"] is False, f"'{scanner}' was not disabled"
    _assert_fully_specified(guard_type, scanner, emitted)
