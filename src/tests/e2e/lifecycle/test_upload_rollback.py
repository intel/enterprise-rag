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
from tests.e2e.validation.constants import CHATQNA_NAMESPACE, LLM_USVC_POD_LABEL, RERANKING_USVC_POD_LABEL

logger = logging.getLogger(__name__)

STATE_FILE = "/tmp/upload_variant_state.json"

# Matches the distinctive document ingested in the upload phase (test_upload_variant.py).
QUESTION = "How many shards does the Qwindell artifact contain?"
EXPECTED = ["88"]


@allure.testcase("IEASG-T720")
def test_upload_rollback_restores_chat_models(k8s_helper):
    """After switching back to base, the LLM and reranking model servers are redeployed (the
    machine-filling upload embedding is undeployed first to free the machine)."""
    if cfg.get("pipeline_type") != "chatqna":
        pytest.skip("ChatQnA pipeline is not deployed")

    assert k8s_helper.get_pod_by_label(namespace=CHATQNA_NAMESPACE, label_selector=LLM_USVC_POD_LABEL), \
        "LLM model server should be redeployed after switching back to base"
    assert k8s_helper.get_pod_by_label(namespace=CHATQNA_NAMESPACE, label_selector=RERANKING_USVC_POD_LABEL), \
        "Reranking model server should be redeployed after switching back to base"


@allure.testcase("IEASG-T721")
def test_upload_rollback_ingested_data_persists_and_queryable(edp_helper, chatqa_api_helper):
    """Data continuity end-to-end: the document ingested via the upload pipeline survives the switch
    back to base (the vector store is a separate namespace) AND is now answerable via chat — the
    upload -> base round-trip must preserve the bulk-ingested data and make it queryable."""
    if cfg.get("pipeline_type") != "chatqna":
        pytest.skip("ChatQnA pipeline is not deployed")

    assert os.path.exists(STATE_FILE), \
        "Upload-phase state missing; the upload phase (test_upload_variant.py) must run first"
    with open(STATE_FILE) as fh:
        doc_file = json.load(fh)["doc_file"]

    # 1. The document ingested in the upload phase still exists in EDP after the switch back to base.
    record = next((f for f in edp_helper.list_files().json()
                   if f.get("object_name", "").endswith(doc_file)), None)
    assert record is not None, \
        f"'{doc_file}' ingested via the upload pipeline is missing after switching back to base"
    logger.info(f"Upload-ingested document still present after rollback: {record.get('object_name')}")

    # 2. Chat can answer about its content (retrieval over the upload-ingested doc + LLM back online).
    response = chatqa_api_helper.call_chatqa(QUESTION)
    assert response.status_code == 200, f"ChatQA returned unexpected status: {response.status_code}"
    response_text = chatqa_api_helper.get_text(response)
    logger.info(f"ChatQA response after rollback: {response_text}")
    assert chatqa_api_helper.words_in_response(EXPECTED, response_text), (
        f"Chat could not answer about the upload-ingested document: expected one of {EXPECTED}, "
        f"got: {response_text}"
    )
