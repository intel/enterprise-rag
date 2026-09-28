#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import os

import allure
import pytest

from tests.e2e.validation.buildcfg import cfg
from tests.e2e.validation.constants import CHATQNA_NAMESPACE

logger = logging.getLogger(__name__)

LLM_POD_LABEL_SELECTOR = "app.kubernetes.io/name=llm-usvc"


@allure.testcase("IEASG-T288")
def test_update_llm_model(k8s_helper):
    """
    Verify the LLM microservice pod serves the model selected in the config's
    `inference_models` list (role: llm) — i.e. its LLM_MODEL_NAME env var matches the
    configured catalog name after an LLM-model update.
    """
    # In an update scenario the target is passed via EXPECTED_MODEL_NAME; the config buildcfg reads
    # on the test host is a PRE-UPDATE snapshot, so it also serves as the original/baseline model.
    original_model = next(
        (m["name"] for m in cfg.get("inference_models", []) if m.get("role") == "llm"), None
    )
    target_model = os.environ.get("EXPECTED_MODEL_NAME")
    expected_model_name = target_model or original_model
    assert expected_model_name, (
        "No expected LLM model: set EXPECTED_MODEL_NAME (scenario) or an "
        "inference_models entry with role 'llm' in config"
    )
    # When both are known, confirm the update actually changes the model (not a no-op).
    if target_model and original_model:
        assert target_model != original_model, (
            f"LLM model did not change — config still '{original_model}'. The update was a no-op."
        )
    logger.info(f"Expected LLM model name: {expected_model_name}")
    llm_pod = k8s_helper.get_pod_by_label(namespace=CHATQNA_NAMESPACE,
                                          label_selector=LLM_POD_LABEL_SELECTOR)

    command = ["sh", "-c", "echo $LLM_MODEL_NAME"]
    logger.info(f"Checking environment variable $LLM_MODEL_NAME in pod: {llm_pod.name}")
    try:
        env_value = k8s_helper.exec_in_pod(llm_pod, command)
        logger.info(f"Pod '{llm_pod.name}' reports LLM_MODEL_NAME = '{env_value}'")
    except Exception as e:
        pytest.fail(f"Test failed while executing command in pod '{llm_pod.name}'. Error: {e}")

    assert env_value == expected_model_name, \
        f"Pod '{llm_pod.name}' has an incorrect model name. Expected: '{expected_model_name}', Found: '{env_value}'"
