#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os

import allure
import pytest

from tests.e2e.helpers.k8s_helper import ResourceNotFound
from tests.e2e.validation.buildcfg import cfg
from tests.e2e.validation.constants import (
    CHATQNA_NAMESPACE,
    DATAPREP_UPLOAD_DIR,
    EMBEDDING_USVC_POD_LABEL,
    LLM_USVC_POD_LABEL,
    RERANKING_USVC_POD_LABEL,
)

logger = logging.getLogger(__name__)

# Distinctive, made-up content so a correct chat answer (after switching back to base) can only come
# from retrieval over this document, not from the LLM's prior knowledge.
DOC_FILE = "upload_variant_doc.txt"  # "The Qwindell artifact contains exactly 88 shards, ..."
STATE_FILE = "/tmp/upload_variant_state.json"

# The upload variant re-sizes embedding to fill the machine with freed LLM/reranking cores (its
# steps.yaml.j2 declares 5 replicas). Assert it scaled to several replicas without pinning the exact
# count (which the variant may retune).
UPLOAD_EMBEDDING_MIN_REPLICAS = 3


def _pod_absent(k8s_helper, label):
    try:
        k8s_helper.get_pod_by_label(namespace=CHATQNA_NAMESPACE, label_selector=label)
        return False
    except ResourceNotFound:
        return True


# The document ingested here must survive the switch back to base, so this phase must NOT clean it up.
@pytest.fixture(autouse=True)
def edp_cleanup_after_test():
    """No-op override: keep the upload-ingested document for the base (rollback) phase."""
    yield


@pytest.fixture(scope="session", autouse=True)
def edp_cleanup_after_session():
    """No-op override: keep the upload-ingested document for the base (rollback) phase."""
    yield


@allure.testcase("IEASG-T717")
def test_upload_variant_disables_chat_models(k8s_helper):
    """Upload is an embedding-only variant: the LLM and reranking model servers must be undeployed
    (reconcile frees their cores) and only embedding remains."""
    if cfg.get("pipeline_type") != "chatqna":
        pytest.skip("ChatQnA pipeline is not deployed")

    assert _pod_absent(k8s_helper, LLM_USVC_POD_LABEL), \
        "LLM model server should be undeployed in the upload variant"
    assert _pod_absent(k8s_helper, RERANKING_USVC_POD_LABEL), \
        "Reranking model server should be undeployed in the upload variant"
    embedding_pod = k8s_helper.get_pod_by_label(namespace=CHATQNA_NAMESPACE,
                                                label_selector=EMBEDDING_USVC_POD_LABEL)
    assert embedding_pod, "Embedding model server should be running in the upload variant"


@allure.testcase("IEASG-T718")
def test_upload_variant_embedding_scaled_up(k8s_helper):
    """The upload variant reclaims the freed LLM/reranking cores and scales embedding out to several
    replicas (its upload footprint)."""
    if cfg.get("pipeline_type") != "chatqna":
        pytest.skip("ChatQnA pipeline is not deployed")

    replicas = k8s_helper.count_pods_by_label(namespace=CHATQNA_NAMESPACE,
                                              label_selector=EMBEDDING_USVC_POD_LABEL)
    logger.info(f"Embedding replicas in the upload variant: {replicas}")
    assert replicas >= UPLOAD_EMBEDDING_MIN_REPLICAS, (
        f"Embedding should scale out in the upload variant: expected >= {UPLOAD_EMBEDDING_MIN_REPLICAS} "
        f"replicas, found {replicas}"
    )


@allure.testcase("IEASG-T719")
def test_upload_variant_bulk_ingestion(edp_helper):
    """The upload variant exists for bulk ingestion. Ingest a distinctive document through the
    embedding-only pipeline and confirm it is ingested; record it so the base phase can verify it
    persisted and is queryable via chat."""
    if cfg.get("pipeline_type") != "chatqna":
        pytest.skip("ChatQnA pipeline is not deployed")

    logger.info(f"Ingesting '{DOC_FILE}' via the upload (embedding-only) pipeline")
    edp_helper.upload_file_and_wait_for_ingestion(os.path.join(DATAPREP_UPLOAD_DIR, DOC_FILE))

    record = next((f for f in edp_helper.list_files().json()
                   if f.get("object_name", "").endswith(DOC_FILE)), None)
    assert record is not None, f"'{DOC_FILE}' was not ingested by the upload pipeline"
    assert record.get("status") == "ingested", \
        f"'{DOC_FILE}' status is {record.get('status')}, expected 'ingested'"

    with open(STATE_FILE, "w") as fh:
        json.dump({"doc_file": DOC_FILE, "object_name": record.get("object_name")}, fh)
    logger.info(f"Recorded upload-ingested document for the base phase: {record.get('object_name')}")
