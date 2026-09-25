#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2025-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os

import allure
import pytest

from tests.e2e.validation.buildcfg import cfg
from tests.e2e.validation.constants import CHATQNA_NAMESPACE

logger = logging.getLogger(__name__)

EMBEDDING_POD_LABEL_SELECTOR = "app.kubernetes.io/name=embedding-usvc"
STATE_FILE = "/tmp/pre_update_embedding_state.json"


def _load_pre_update_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        pytest.fail(
            f"Pre-update state file not found: {STATE_FILE}. "
            "Run test_pre_update_embedding.py (CLUSTER_STATE=before-update) first."
        )


@allure.testcase("IEASG-T311")
def test_update_embedding_model(k8s_helper, edp_helper, chatqa_api_helper):
    """
    Verify an embedding-model update took effect end to end (CLUSTER_STATE=after-update).

    1. The embedding microservice pod serves the NEW model (EXPECTED_MODEL_NAME, passed by the
       scenario) and it actually differs from the model recorded before the update.
    2. The document ingested in the before-update phase is still embedded with the OLD model, so
       it is flagged for re-ingestion (changing the embedding model changes the vector dimensions
       and invalidates the existing index).
    3. Re-ingesting it via the EDP retry endpoint (the Admin Panel "Reingest" action) re-embeds it
       with the new model, after which ChatQA retrieves and answers from it again.
    """
    if cfg.get("pipeline_type") != "chatqna":
        pytest.skip("ChatQnA pipeline is not deployed")

    state = _load_pre_update_state()
    original_model = state["original_pod_model"]
    expected_model = os.environ.get("EXPECTED_MODEL_NAME")
    assert expected_model, "EXPECTED_MODEL_NAME is not set — the scenario must pass the update target"

    # 1) The embedding pod serves the new model, and the model actually changed.
    embedding_pod = k8s_helper.get_pod_by_label(namespace=CHATQNA_NAMESPACE,
                                                label_selector=EMBEDDING_POD_LABEL_SELECTOR)
    found = k8s_helper.exec_in_pod(embedding_pod, ["sh", "-c", "echo $EMBEDDING_MODEL_NAME"])
    logger.info(f"Embedding pod '{embedding_pod.name}' reports EMBEDDING_MODEL_NAME = '{found}'")
    assert found == expected_model, (
        f"Pod '{embedding_pod.name}' serves '{found}', expected the new model '{expected_model}'"
    )
    assert expected_model != original_model, (
        f"Embedding model did not change — still '{original_model}'. The update was a no-op."
    )
    logger.info(f"Embedding model changed: '{original_model}' -> '{found}'")

    # 2) The document ingested before the update is still embedded with the OLD model
    #    (i.e. it needs re-ingestion — the condition the Admin Panel uses to surface "Reingest").
    object_name = state["object_name"]
    record = next(
        (f for f in edp_helper.list_files().json()
         if f.get("object_name", "") == object_name), None
    )
    assert record, f"Pre-update document '{object_name}' is missing after the model switch"
    assert record.get("embedding_model") == original_model, (
        f"Expected '{object_name}' to still be embedded with the old model '{original_model}' "
        f"(needing re-ingestion), but its embedding_model is '{record.get('embedding_model')}'"
    )

    # 3) Re-ingest the existing document (UI "Reingest" == POST /file/{id}/retry) and confirm it
    #    is re-embedded with the new model.
    logger.info(f"Re-ingesting '{object_name}' (id={record['id']}) with the new embedding model")
    retry_response = edp_helper.retry_file(record["id"])
    assert retry_response.status_code in (200, 202, 204), (
        f"Re-ingest request failed: {retry_response.status_code} {retry_response.text}"
    )
    edp_helper.wait_for_reingest(object_name, expected_model)

    # 4) Retrieval works again on the re-embedded document.
    response = chatqa_api_helper.call_chatqa(state["question"])
    assert response.status_code == 200, f"ChatQA returned unexpected status: {response.status_code}"
    response_text = chatqa_api_helper.get_text(response)
    logger.info(f"ChatQA response after re-ingestion: {response_text}")
    assert chatqa_api_helper.words_in_response(state["expected"], response_text), (
        f"Retrieval failed after re-ingesting with the new embedding model: "
        f"expected one of {state['expected']}, got: {response_text}"
    )
