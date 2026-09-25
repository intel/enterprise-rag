#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os

import allure
import pytest

from tests.e2e.validation.buildcfg import cfg
from tests.e2e.validation.constants import CHATQNA_NAMESPACE, DATAPREP_UPLOAD_DIR

logger = logging.getLogger(__name__)

EMBEDDING_POD_LABEL_SELECTOR = "app.kubernetes.io/name=embedding-usvc"
STATE_FILE = "/tmp/pre_update_embedding_state.json"

# Distinctive, made-up content so a correct answer can only come from retrieval over the
# ingested document, not from the LLM's prior knowledge.
DOC_FILE = "multi_doc_retrieval_1.txt"  # "Marianooo has 20 balls for a game called Marianoball."
QUESTION = "How many balls does Marianooo have for the game called Marianoball?"
EXPECTED = ["20"]


@pytest.fixture(autouse=True)
def edp_cleanup_after_test():
    """No-op override: the ingested document must persist across the embedding-model switch
    so the post-update phase can re-ingest it."""
    yield


@pytest.fixture(scope="session", autouse=True)
def edp_cleanup_after_session():
    """No-op override: keep the ingested document for the post-update phase."""
    yield


@allure.testcase("IEASG-T722")
def test_pre_update_embedding(k8s_helper, edp_helper, chatqa_api_helper):
    """
    Baseline before an embedding-model update (CLUSTER_STATE=before-update).

    Records the currently deployed embedding model, ingests a document with it, and confirms the
    document is retrievable. State is persisted so the post-update phase can assert the model
    changed and re-ingest this same document with the new model.
    """
    if cfg.get("pipeline_type") != "chatqna":
        pytest.skip("ChatQnA pipeline is not deployed")

    embedding_pod = k8s_helper.get_pod_by_label(namespace=CHATQNA_NAMESPACE,
                                                label_selector=EMBEDDING_POD_LABEL_SELECTOR)
    original_model = k8s_helper.exec_in_pod(embedding_pod, ["sh", "-c", "echo $EMBEDDING_MODEL_NAME"])
    assert original_model, "Could not read the current embedding model from the embedding pod"
    logger.info(f"Original embedding model (pre-update): {original_model}")

    logger.info(f"Ingesting '{DOC_FILE}' with the original embedding model")
    edp_helper.upload_file_and_wait_for_ingestion(os.path.join(DATAPREP_UPLOAD_DIR, DOC_FILE))

    response = chatqa_api_helper.call_chatqa(QUESTION)
    assert response.status_code == 200, f"ChatQA returned unexpected status: {response.status_code}"
    response_text = chatqa_api_helper.get_text(response)
    logger.info(f"Baseline ChatQA response: {response_text}")
    assert chatqa_api_helper.words_in_response(EXPECTED, response_text), (
        f"Baseline retrieval failed before the update: expected one of {EXPECTED}, got: {response_text}"
    )

    record = next(
        (f for f in edp_helper.list_files().json()
         if f.get("object_name", "").endswith(DOC_FILE)), None
    )
    assert record, f"'{DOC_FILE}' not found in EDP after ingestion"

    state = {
        "object_name": record.get("object_name"),
        "file_id": record.get("id"),
        "original_embedding_model": record.get("embedding_model") or original_model,
        "original_pod_model": original_model,
        "question": QUESTION,
        "expected": EXPECTED,
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    logger.info(f"Saved pre-update state to {STATE_FILE}: {state}")
