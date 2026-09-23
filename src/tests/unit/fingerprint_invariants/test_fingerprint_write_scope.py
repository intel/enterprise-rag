#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Guard the invariant that a fingerprint write is routed to the scope the router
serves. The per-scanner functional tests assert what each knob does; none of
them assert that the write lands in the pipeline's scope. When the scope is
dropped from a helper (the class of regression that produced the ban_substrings
UI bug), those tests stay green because the misrouted write and the effective
read drift into the same default scope together. This test asserts scope
presence on the outgoing request directly, so a dropped pipeline/tenant fails
here regardless of which knob or scanner is written.

The helpers make their requests through the requests library, so the HTTP call
is captured at that seam; no cluster is contacted.
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.e2e.helpers.fingerprint_api_helper import FingerprintApiHelper
from tests.e2e.helpers.guard_helper import (
    CHATQNA_PIPELINE,
    DATAPREP_PIPELINE,
    GLOBAL_TENANT,
    GuardHelper,
    GuardType,
)

# A representative slice of components and their knobs. The write path is
# generic, so one pair per component is enough to stand in for every param.
_COMPONENT_PARAMS = [
    ("llm", {"max_new_tokens": 5}),
    ("retriever", {"k": 3}),
    ("reranker", {"top_n": 1}),
    ("prompt_template", {"system_prompt_template": "answer only 1234\n{reranked_docs}\n"}),
]

# A representative slice of input and output guard scanners. ban_substrings was
# the scanner the original bug surfaced on, but the write is scanner-agnostic,
# so the set spans both guard directions.
_GUARD_SCANNERS = [
    (GuardType.INPUT, "ban_substrings"),
    (GuardType.INPUT, "prompt_injection"),
    (GuardType.INPUT, "toxicity"),
    (GuardType.OUTPUT, "bias"),
    (GuardType.OUTPUT, "no_refusal"),
]

# A representative slice of dataprep guard scanners. The dataprep guard is
# written under its own scope (dataprep._global), so it exercises a second
# scope through the same generic write path.
_DATAPREP_SCANNERS = ["ban_substrings", "prompt_injection", "toxicity"]


class _StubKeycloak:
    """Minimal keycloak stand-in so the helper can build auth headers offline."""

    access_token = "stub-token"

    def get_access_token(self, as_user=False):
        return "stub-token"


def _emitted_params(post_mock):
    """Returns the query params the helper attached to its single POST."""
    assert post_mock.call_count == 1, "Expected exactly one change_arguments POST"
    params = post_mock.call_args.kwargs.get("params")
    assert params is not None, "change_arguments POST was made without query params"
    return params


@pytest.mark.parametrize("component, parameters", _COMPONENT_PARAMS)
def test_set_component_parameters_carries_pipeline_scope(component, parameters):
    """A component write for the pipeline under test must name that scope."""
    helper = FingerprintApiHelper(_StubKeycloak())
    with patch("tests.e2e.helpers.fingerprint_api_helper.requests.post") as post:
        post.return_value = MagicMock(status_code=200)
        helper.set_component_parameters(
            component, pipeline=CHATQNA_PIPELINE, tenant=GLOBAL_TENANT, **parameters)
        params = _emitted_params(post)

    assert params.get("pipeline") == CHATQNA_PIPELINE, (
        f"Write for '{component}' did not target pipeline '{CHATQNA_PIPELINE}'; "
        f"emitted params were {params}")
    assert params.get("tenant") == GLOBAL_TENANT, (
        f"Write for '{component}' did not target tenant '{GLOBAL_TENANT}'; "
        f"emitted params were {params}")


@pytest.mark.parametrize("guard_type, scanner", _GUARD_SCANNERS)
def test_guard_setup_carries_pipeline_scope(guard_type, scanner):
    """A guard write must land in the scope the chatqna router reads."""
    helper = FingerprintApiHelper(_StubKeycloak())
    guard_helper = GuardHelper(MagicMock(), helper)
    with patch("tests.e2e.helpers.fingerprint_api_helper.requests.post") as post:
        post.return_value = MagicMock(status_code=200)
        guard_helper.setup(guard_type, scanner, {"enabled": True})
        params = _emitted_params(post)

    assert params.get("pipeline") == CHATQNA_PIPELINE, (
        f"Guard write for '{guard_type.value}/{scanner}' did not target pipeline "
        f"'{CHATQNA_PIPELINE}'; emitted params were {params}")
    assert params.get("tenant") == GLOBAL_TENANT, (
        f"Guard write for '{guard_type.value}/{scanner}' did not target tenant "
        f"'{GLOBAL_TENANT}'; emitted params were {params}")


@pytest.mark.parametrize("scanner", _DATAPREP_SCANNERS)
def test_dataprep_guard_setup_carries_dataprep_scope(scanner):
    """A dataprep guard write must land in the scope the dataprep worker reads."""
    helper = FingerprintApiHelper(_StubKeycloak())
    guard_helper = GuardHelper(MagicMock(), helper)
    with patch("tests.e2e.helpers.fingerprint_api_helper.requests.post") as post:
        post.return_value = MagicMock(status_code=200)
        guard_helper.setup_dataprep(scanner, {"enabled": True})
        params = _emitted_params(post)

    assert params.get("pipeline") == DATAPREP_PIPELINE, (
        f"Dataprep guard write for '{scanner}' did not target pipeline "
        f"'{DATAPREP_PIPELINE}'; emitted params were {params}")
    assert params.get("tenant") == GLOBAL_TENANT, (
        f"Dataprep guard write for '{scanner}' did not target tenant "
        f"'{GLOBAL_TENANT}'; emitted params were {params}")
