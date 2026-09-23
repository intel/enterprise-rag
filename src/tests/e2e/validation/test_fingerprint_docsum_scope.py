#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Prove that a docsum deployment gets its fingerprint parameter rows seeded and
that they are readable and writable under docsum's own scope.

This is the case that regressed: docsum declares paramsKind on two steps (llm
and docsum), the GMC controller seeds a row for each before reconciling the
resources, and that seeding retries until the fingerprint service answers. A
docsum pipeline whose rows are missing never finishes reconciling, so the
symptom is an endless requeue rather than a failure -- which is why it needs a
test that reads the rows rather than only checking that pods are up.

The other fingerprint suites cover the chatqa scope; nothing covered docsum.

Needs a running docsum deployment; skipped on other pipeline types.
"""

import allure
import logging

import pytest

from tests.e2e.validation.buildcfg import cfg

if cfg.get("pipeline_type") != "docsum":
    pytestmark = pytest.mark.skip(
        reason=f"Requires a docsum deployment; pipeline_type is {cfg.get('pipeline_type')!r}")

logger = logging.getLogger(__name__)

# The parameter groups docsum's steps declare, as {params_key: params_kind}.
# These are the keys the controller seeds for this pipeline, so a missing row
# here is the reconcile-loop condition rather than a cosmetic gap.
DOCSUM_PARAM_GROUPS = {
    "llm": "llm",
    "docsum": "docsum",
}

# Fields each group must carry once seeded. Only the ones docsum actually drives
# are asserted, so the test does not break when an unrelated field is added.
REQUIRED_FIELDS = {
    "llm": {"max_new_tokens", "stream"},
    "docsum": {"max_new_tokens", "stream", "summary_type"},
}

# The canonical default for a key that has no row yet, used only as a restore
# fallback. Stored values are runtime-tunable, so this is not asserted: the
# control plane or an operator can legitimately change them.
_DEFAULT_MAX_NEW_TOKENS = 1024


def _assert_group_seeded(fingerprint_api_helper, params_key):
    """Asserts one parameter group has a seeded row of the declared kind."""
    response = fingerprint_api_helper.read_config(params_key)
    assert response.status_code == 200, (
        f"No fingerprint row for docsum's '{params_key}' group "
        f"(HTTP {response.status_code}). The GMC controller seeds a row for every "
        f"step that declares paramsKind before reconciling resources, and retries "
        f"until it succeeds, so a missing row means the pipeline cannot finish "
        f"reconciling. {response.text[:200]}")

    body = response.json()
    expected_kind = DOCSUM_PARAM_GROUPS[params_key]
    assert body["params_kind"] == expected_kind, (
        f"'{params_key}' was seeded as kind '{body['params_kind']}', "
        f"expected '{expected_kind}'")

    values = body.get("values", {})
    missing = REQUIRED_FIELDS[params_key] - set(values)
    assert not missing, (
        f"'{params_key}' is missing seeded field(s) {sorted(missing)}; "
        f"got {sorted(values)}")

    logger.info(f"docsum scope '{params_key}' seeded as '{expected_kind}'")


@pytest.mark.smoke
@allure.testcase("IEASG-T701")
def test_docsum_param_groups_are_seeded(fingerprint_api_helper):
    """
    Each parameter group docsum declares must have a row under docsum's scope,
    carrying the kind the step declared and the fields that kind defines. A 404
    here is the state that makes the controller requeue forever.

    Both groups are checked in one test so the run maps to a single reported
    result; each gets its own allure step so a failure still names the group.
    """
    for params_key in sorted(DOCSUM_PARAM_GROUPS):
        with allure.step(f"params_key '{params_key}' is seeded"):
            _assert_group_seeded(fingerprint_api_helper, params_key)


@allure.testcase("IEASG-T702")
def test_docsum_scope_write_is_read_back(fingerprint_api_helper):
    """
    A write to docsum's llm group must be readable back from the same scope, so
    the pipeline's parameters are tunable and not merely present.
    """
    params_key = "llm"
    before = fingerprint_api_helper.read_config(params_key)
    assert before.status_code == 200, (
        f"Cannot read docsum's '{params_key}' baseline (HTTP {before.status_code})")
    baseline = before.json()["values"].get("max_new_tokens", _DEFAULT_MAX_NEW_TOKENS)
    target = baseline + 7

    try:
        write = fingerprint_api_helper.set_component_parameters(
            params_key, max_new_tokens=target)
        assert write.status_code == 200, (
            f"Write to docsum's '{params_key}' scope failed with "
            f"{write.status_code}: {write.text[:200]}")

        after = fingerprint_api_helper.read_config(params_key)
        assert after.status_code == 200, "Cannot read back after the write"
        assert after.json()["values"]["max_new_tokens"] == target, (
            f"Write did not land in docsum's scope: expected {target}, "
            f"got {after.json()['values']['max_new_tokens']}")
    finally:
        # The store is insert/update-only, so the row is reset rather than
        # removed. A silent failure here leaves the bumped value in place for
        # every later run, so it is asserted.
        restore = fingerprint_api_helper.set_component_parameters(
            params_key, max_new_tokens=baseline)
        assert restore.status_code == 200, (
            f"Failed to restore docsum '{params_key}' max_new_tokens to {baseline} "
            f"(HTTP {restore.status_code}); later runs will see the test's value. "
            f"{restore.text[:200]}")
        logger.info(f"Restored docsum '{params_key}' max_new_tokens to {baseline}")
