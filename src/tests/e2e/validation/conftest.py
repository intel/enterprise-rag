#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for the validation suite.

The autouse restore_chatqa_llm_params fixture only wraps test_chatqa_pipeline
(selected by the test module name); for every other module it yields
immediately without reading or writing the fingerprint helper.
"""

import logging

import pytest

from tests.e2e.validation.buildcfg import cfg

logger = logging.getLogger(__name__)

# The chatqna pipeline tests toggle these llm parameters on the scope the running
# router reads, so their prior values are captured and put back around each test.
_CHATQA_PARAM_MODULE = "test_chatqa_pipeline"
_CHATQA_LLM_KEY = "llm"
_CHATQNA_PIPELINE = "chatqna"
_CHATQA_TENANT = "_global"
_SNAPSHOT_PARAMS = ("stream", "max_new_tokens")


@pytest.fixture(autouse=True)
def restore_chatqa_llm_params(request):
    """Restore the chatqna._global llm stream/max_new_tokens after each chatqna test.

    Reads the current values for the chatqna router's scope before the test runs,
    then writes back any that the test changed, so the chatqna pipeline tests are
    order-independent. Only the chatqna pipeline test module is wrapped; for every
    other module the fixture yields immediately without touching the fingerprint
    helper.
    """
    if request.module.__name__.rsplit(".", 1)[-1] != _CHATQA_PARAM_MODULE:
        yield
        return
    if cfg.get("pipeline_type") != _CHATQNA_PIPELINE:
        yield
        return

    fingerprint_api_helper = request.getfixturevalue("fingerprint_api_helper")
    read = fingerprint_api_helper.read_config(
        _CHATQA_LLM_KEY, pipeline=_CHATQNA_PIPELINE, tenant=_CHATQA_TENANT)
    snapshot = _snapshot_params(read)
    missing = [key for key in _SNAPSHOT_PARAMS if key not in snapshot]
    if missing:
        # Without a full baseline a mutation could not be undone on teardown, so
        # fail before the test runs rather than let it leak state into later tests.
        pytest.fail(
            f"Incomplete chatqna._global llm baseline; cannot guarantee restore after the test. "
            f"Missing keys: {missing}. Snapshot read: {snapshot} "
            f"(/config status {read.status_code}: {read.text[:200]})")
    try:
        yield
    finally:
        current = _snapshot_params(fingerprint_api_helper.read_config(
            _CHATQA_LLM_KEY, pipeline=_CHATQNA_PIPELINE, tenant=_CHATQA_TENANT))
        changed = {key: value for key, value in snapshot.items() if current.get(key) != value}
        if changed:
            logger.info(f"Restoring chatqna._global llm parameters: {changed}")
            write = fingerprint_api_helper.set_component_parameters(
                _CHATQA_LLM_KEY,
                pipeline=_CHATQNA_PIPELINE,
                tenant=_CHATQA_TENANT,
                **changed,
            )
            if write.status_code != 200:
                # The scope is still mutated, so surface it rather than let a
                # failed restore leak state into later tests as a silent pass.
                pytest.fail(
                    f"Failed to restore chatqna._global llm parameters {changed} "
                    f"(/change_arguments status {write.status_code}: {write.text[:200]})")


def _snapshot_params(response):
    """Returns the snapshot-tracked llm values present in a /config response."""
    if response.status_code != 200:
        return {}
    values = response.json().get("values", {})
    return {key: values[key] for key in _SNAPSHOT_PARAMS if key in values}
