#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import allure
import logging
import pytest

from tests.e2e.validation.buildcfg import cfg
from tests.e2e.validation.constants import CHATQNA_NAMESPACE

logger = logging.getLogger(__name__)

VLLM_POD_LABEL_SELECTOR = "app.kubernetes.io/name=vllm"


@allure.testcase("IEASG-T288")
def test_update_llm_model(k8s_helper):
    """
    Test verifies if vllm pod have the expected LLM_VLLM_MODEL_NAME env variable set.
    """
    try:
        vllm_pod = k8s_helper.get_pod_by_label(namespace=CHATQNA_NAMESPACE, label_selector=VLLM_POD_LABEL_SELECTOR)
        inference_models = cfg.get("inference_models", [])
        expected_model_name = next((m["name"] for m in inference_models if m.get("role") == "llm"), None)

        logger.info(f"Expected LLM model name from config: {expected_model_name}")
        command = ["sh", "-c", "echo $LLM_VLLM_MODEL_NAME"]
        logger.info(f"Checking environment variable $LLM_VLLM_MODEL_NAME in pod: {vllm_pod.name}")
        env_value = k8s_helper.exec_in_pod(vllm_pod, command)
        logger.info(f"Pod '{vllm_pod.name}' reports LLM_VLLM_MODEL_NAME = '{env_value}'")
    except Exception as e:
        pytest.fail(f"Test failed while executing command in pod '{vllm_pod.name}'. Error: {e}")

    assert env_value == expected_model_name, \
        f"Pod '{vllm_pod.name}' has an incorrect model name. Expected: '{expected_model_name}', Found: '{env_value}'"
