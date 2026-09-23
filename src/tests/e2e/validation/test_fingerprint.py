#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import allure
import logging
import time

import pytest

from tests.e2e.validation.buildcfg import cfg

logger = logging.getLogger(__name__)


# Default the tests fall back to for a key that had no row before the test. The
# store is insert/update-only (no delete endpoint), so a key the test created
# cannot be removed; resetting it to the canonical llm default keeps the value
# deterministic instead of leaving the test's own number behind.
_DEFAULT_LLM_MAX_NEW_TOKENS = 1024

# Most of this file exercises the fingerprint store itself and runs on any
# pipeline. Two tests assert the effect of a write on a chatqna answer, which
# needs a chatqna endpoint -- elsewhere the call returns 405 and fails for a
# reason unrelated to fingerprint. They carry this skip rather than the module.
_needs_chatqna = pytest.mark.skipif(
    cfg.get("pipeline_type") not in ("chatqna", "audioqna"),
    reason=f"Needs a chatqna endpoint; pipeline_type is {cfg.get('pipeline_type')!r}")


def _current_max_new_tokens(fingerprint_api_helper, params_key):
    """Returns the stored max_new_tokens for a key, or None if it has no row yet."""
    response = fingerprint_api_helper.read_config(params_key)
    if response.status_code != 200:
        return None
    return response.json()["values"]["max_new_tokens"]


def _restore_max_new_tokens(fingerprint_api_helper, params_key, value):
    """Resets a key's max_new_tokens to its baseline (or the default if new)."""
    target = value if value is not None else _DEFAULT_LLM_MAX_NEW_TOKENS
    fingerprint_api_helper.set_component_parameters(
        params_key, params_kind="llm", max_new_tokens=target)


@pytest.mark.smoke
@allure.testcase("IEASG-T53")
def test_fingerprint_change_arguments(fingerprint_api_helper):
    """
    Retrieve current value for max_new_tokens and increase its value by 1.
    Verify if the operation succeeded.
    """
    current_arguments = fingerprint_api_helper.read_config("llm")
    assert current_arguments.status_code == 200, "Unexpected status code reading llm config"
    current_max_new_tokens = current_arguments.json()["values"]["max_new_tokens"]

    body = [
        {
            "name": "llm",
            "data": {
                "max_new_tokens": current_max_new_tokens + 1
            }
        }
    ]

    try:
        response = fingerprint_api_helper.change_arguments(body)
        assert response.status_code == 200, "Unexpected status code"
        new_arguments = fingerprint_api_helper.read_config("llm")
        assert new_arguments.status_code == 200, "Unexpected status code reading llm config"
        new_value_max_new_tokens = new_arguments.json()["values"]["max_new_tokens"]
        assert new_value_max_new_tokens == current_max_new_tokens + 1
    finally:
        logger.info(f"Reverting max_new_tokens value to {current_max_new_tokens}")
        body = [
            {
                "name": "llm",
                "data": {
                    "max_new_tokens": current_max_new_tokens
                }
            }
        ]
        fingerprint_api_helper.change_arguments(body)


@_needs_chatqna
@pytest.mark.smoke
@allure.testcase("IEASG-T151")
def test_fingerprint_change_prompt_template(fingerprint_api_helper, chatqa_api_helper):
    """
    Verifies that the system correctly applies a custom prompt template.
    The test replaces the default prompt with a template that explicitly instructs the model to always output "1234"
    regardless of the question, context, or retrieved documents.
    If the system responds with any other text, it indicates that the prompt override was not applied correctly.
    """
    current_arguments = fingerprint_api_helper.read_config("prompt_template")
    assert current_arguments.status_code == 200, "Unexpected status code reading prompt_template config"
    original_system_prompt_template = current_arguments.json()["values"]["system_prompt_template"]
    new_system_prompt_template = "No matter what the user asks, always respond only with: 1234\n{reranked_docs}\n"
    body = [{
        "name": "prompt_template",
        "data": {
            "system_prompt_template": new_system_prompt_template,
        }
    }]
    change_prompt_response = fingerprint_api_helper.change_arguments(body)
    try:
        assert change_prompt_response.status_code == 200, "Unexpected status code for prompt template modification call"
        response = chatqa_api_helper.call_chatqa("What is the capital of France?")
        assert response.status_code == 200, "Unexpected status code when calling ChatQA with modified prompt template"
        chatbot_response = chatqa_api_helper.get_text(response)
        logger.info(f"ChatQA response after modifying prompt template: {chatbot_response}")
        assert "1234" in chatbot_response, "Response does not contain the expected number '1234'"
    finally:
        logger.info(f"Reverting prompt template to the original value: {original_system_prompt_template}")
        body = [{
            "name": "prompt_template",
            "data": {
                "system_prompt_template": original_system_prompt_template
            }
        }]
        fingerprint_api_helper.change_arguments(body)


@allure.testcase("IEASG-T240")
def test_fingerprint_regular_user_can_access_fingerprint_api(fingerprint_api_helper, temporarily_remove_regular_user_required_actions):
    """Verify that change_arguments and config APIs are not accessible by regular users"""
    # Test change_arguments API
    current_arguments = fingerprint_api_helper.read_config("llm")
    assert current_arguments.status_code == 200, "Unexpected status code reading llm config"
    current_max_new_tokens = current_arguments.json()["values"]["max_new_tokens"]
    body = [
        {
            "name": "llm",
            "data": {
                "max_new_tokens": current_max_new_tokens + 1
            }
        }
    ]
    response = fingerprint_api_helper.change_arguments(body, as_user=True)
    assert response.status_code == 403

    # Test the per-key config read API
    config_response = fingerprint_api_helper.read_config("llm", as_user=True)
    assert config_response.status_code == 403, "Regular user should not be able to call config"


@allure.testcase("IEASG-T691")
def test_fingerprint_multi_instance_keyed_storage(fingerprint_api_helper):
    """
    Two instances of the same kind (llm) addressed by distinct params_keys must
    hold independent values.
    Write max_new_tokens=1024 to "llm_primary" and 512 to "llm_secondary", then
    read each back through /config?params_key=<key> and assert the values are
    distinct and match what was written.
    """
    primary_key = "llm_primary"
    secondary_key = "llm_secondary"
    original_primary = _current_max_new_tokens(fingerprint_api_helper, primary_key)
    original_secondary = _current_max_new_tokens(fingerprint_api_helper, secondary_key)
    body = [
        {"name": primary_key, "params_kind": "llm", "data": {"max_new_tokens": 1024}},
        {"name": secondary_key, "params_kind": "llm", "data": {"max_new_tokens": 512}},
    ]
    try:
        response = fingerprint_api_helper.change_arguments(body)
        assert response.status_code == 200, "Unexpected status code"

        primary = fingerprint_api_helper.read_config(primary_key)
        secondary = fingerprint_api_helper.read_config(secondary_key)
        assert primary.status_code == 200, "Unexpected status code reading llm_primary"
        assert secondary.status_code == 200, "Unexpected status code reading llm_secondary"

        primary_tokens = primary.json()["values"]["max_new_tokens"]
        secondary_tokens = secondary.json()["values"]["max_new_tokens"]
        assert primary_tokens == 1024, "llm_primary must keep its own value"
        assert secondary_tokens == 512, "llm_secondary must keep its own value"
        assert primary_tokens != secondary_tokens, "Instances must hold distinct values"
        assert primary.json()["params_kind"] == "llm"
        assert secondary.json()["params_kind"] == "llm"
    finally:
        _restore_max_new_tokens(fingerprint_api_helper, primary_key, original_primary)
        _restore_max_new_tokens(fingerprint_api_helper, secondary_key, original_secondary)


@_needs_chatqna
@pytest.mark.skipif(
    not cfg.get("gmc_multi_instance_pipeline_enabled"),
    reason="Requires a pipeline CR with two LLM steps (paramsKey llm_primary/llm_secondary)")
@allure.testcase("IEASG-T692")
def test_fingerprint_multi_instance_injection(fingerprint_api_helper, chatqa_api_helper):
    """
    With a pipeline deploying two LLM steps keyed llm_primary and llm_secondary,
    write distinct max_new_tokens to each, confirm each key keeps its own value
    on the read path, and confirm a ChatQnA request still succeeds end to end
    with the two-step pipeline. Needs a live cluster running the multi-instance
    pipeline; skipped otherwise.
    """
    original_primary = _current_max_new_tokens(fingerprint_api_helper, "llm_primary")
    original_secondary = _current_max_new_tokens(fingerprint_api_helper, "llm_secondary")
    body = [
        {"name": "llm_primary", "params_kind": "llm", "data": {"max_new_tokens": 1024}},
        {"name": "llm_secondary", "params_kind": "llm", "data": {"max_new_tokens": 512}},
    ]
    try:
        response = fingerprint_api_helper.change_arguments(body)
        assert response.status_code == 200, "Unexpected status code"

        # Each step is injected only the params_key it declares, so the two keys
        # must keep their own max_new_tokens value on the read path.
        primary = fingerprint_api_helper.read_config("llm_primary")
        secondary = fingerprint_api_helper.read_config("llm_secondary")
        assert primary.json()["values"]["max_new_tokens"] == 1024
        assert secondary.json()["values"]["max_new_tokens"] == 512

        chat_response = chatqa_api_helper.call_chatqa("What is the capital of France?")
        assert chat_response.status_code == 200, "ChatQA request must succeed with two LLM steps"
    finally:
        _restore_max_new_tokens(fingerprint_api_helper, "llm_primary", original_primary)
        _restore_max_new_tokens(fingerprint_api_helper, "llm_secondary", original_secondary)


@allure.testcase("IEASG-T693")
def test_fingerprint_realtime_propagation(fingerprint_api_helper):
    """
    A change_arguments write must become visible on the per-key read path within
    1 second (P99), exercising the write-to-read propagation. Repeat 10 times
    and require at least 9 rounds under the threshold to tolerate network jitter.
    """
    threshold_seconds = 1.0
    poll_interval_seconds = 0.05
    timeout_seconds = 5.0
    rounds = 10
    fast_rounds = 0
    original = fingerprint_api_helper.read_config("llm").json()["values"]["max_new_tokens"]
    current = original

    try:
        for _ in range(rounds):
            current += 1
            write = fingerprint_api_helper.set_component_parameters("llm", max_new_tokens=current)
            assert write.status_code == 200, "change_arguments write failed before polling"

            start = time.monotonic()
            deadline = start + timeout_seconds
            observed = None
            while time.monotonic() < deadline:
                observed = fingerprint_api_helper.read_config("llm").json()["values"]["max_new_tokens"]
                if observed == current:
                    break
                time.sleep(poll_interval_seconds)
            elapsed = time.monotonic() - start
            assert observed == current, f"Write did not propagate within {timeout_seconds}s (last seen {observed})"
            if elapsed < threshold_seconds:
                fast_rounds += 1
            logger.info(f"Propagation round observed in {round(elapsed, 3)}s")

        assert fast_rounds >= 9, \
            f"Only {fast_rounds}/{rounds} propagations were under {threshold_seconds}s"
    finally:
        logger.info(f"Reverting llm max_new_tokens to {original}")
        fingerprint_api_helper.set_component_parameters("llm", max_new_tokens=original)


@allure.testcase("IEASG-T694")
def test_fingerprint_change_and_read_non_default_scope(fingerprint_api_helper):
    """
    A change_arguments write that names an explicit pipeline/tenant must land in
    that scope and be readable back through /config for the same scope, so a
    caller can target a scope other than the microservice's configured default.
    """
    pipeline = "chatqna"
    tenant = "550e8400-e29b-41d4-a716-446655440000"  # UUID, as a Keycloak sub is
    params_key = "llm"
    target_value = 777

    default_before = _current_max_new_tokens(fingerprint_api_helper, params_key)
    scoped_response = fingerprint_api_helper.read_config(params_key, pipeline=pipeline, tenant=tenant)
    scoped_before = (
        scoped_response.json()["values"]["max_new_tokens"]
        if scoped_response.status_code == 200 else None)

    body = [{"name": params_key, "params_kind": "llm", "data": {"max_new_tokens": target_value}}]
    try:
        write = fingerprint_api_helper.change_arguments(body, pipeline=pipeline, tenant=tenant)
        assert write.status_code == 200, "Unexpected status code writing a non-default scope"

        scoped = fingerprint_api_helper.read_config(params_key, pipeline=pipeline, tenant=tenant)
        assert scoped.status_code == 200, "The non-default scope must be readable back"
        assert scoped.json()["values"]["max_new_tokens"] == target_value, \
            "The value read back must match what was written to the scope"

        # The write must not have touched the microservice's own default scope.
        default_now = _current_max_new_tokens(fingerprint_api_helper, params_key)
        assert default_now == default_before, \
            "A scoped write must not leak into the microservice's default scope"
    finally:
        # Restore the scoped row to the value it held before the test (or the
        # canonical default if the scope had no row yet), so no persistent state
        # is left behind. The store is insert/update-only, so a row the test
        # created cannot be removed.
        restore_value = scoped_before if scoped_before is not None else _DEFAULT_LLM_MAX_NEW_TOKENS
        fingerprint_api_helper.change_arguments(
            [{"name": params_key, "params_kind": "llm", "data": {"max_new_tokens": restore_value}}],
            pipeline=pipeline, tenant=tenant)


@allure.testcase("IEASG-T695")
def test_fingerprint_change_arguments_rejects_bad_tenant(fingerprint_api_helper):
    """
    A tenant outside [A-Za-z0-9_-] must be rejected with a 400 at write time,
    never silently accepted, so it cannot become a key the broker cannot hold.
    """
    body = [{"name": "llm", "params_kind": "llm", "data": {"max_new_tokens": 512}}]
    response = fingerprint_api_helper.change_arguments(body, tenant="user:alice")
    assert response.status_code == 400, "A tenant outside the allowed charset must be a 400"


@allure.testcase("IEASG-T594")
def test_fingerprint_maintainer_cannot_call_change_arguments(fingerprint_api_helper, temporarily_remove_maintainer_required_actions):
    """Verify that the maintainer user is not able to call the change_arguments API"""
    current_arguments = fingerprint_api_helper.read_config("llm")
    assert current_arguments.status_code == 200, "Unexpected status code reading llm config"
    current_max_new_tokens = current_arguments.json()["values"]["max_new_tokens"]
    body = [
        {
            "name": "llm",
            "data": {
                "max_new_tokens": current_max_new_tokens + 1
            }
        }
    ]
    response = fingerprint_api_helper.change_arguments(body, as_user="maintainer")
    assert response.status_code == 403, "Maintainer should not be able to call change_arguments"
