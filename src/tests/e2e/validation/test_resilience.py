#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import allure
import logging
import os
import time

import pytest

from tests.e2e.validation.constants import (
    CHATQNA_NAMESPACE,
    DATAPREP_UPLOAD_DIR,
    LLM_INFERENCE_NAMESPACE,
    VDB_NAMESPACE,
)
from tests.e2e.validation.buildcfg import cfg

# Skip all tests if chatqa pipeline is not deployed
if cfg.get("pipeline_type") != "chatqna":
    pytestmark = pytest.mark.skip(reason="ChatQA pipeline is not deployed")

logger = logging.getLogger(__name__)

# chatqa microservice selectors (thin proxies, single replica unless noted).
RETRIEVER_SVC_POD_LABEL_SELECTOR = "app=retriever-svc"
# llm-svc runs 2 replicas -> failover candidate.
LLM_SVC_POD_LABEL_SELECTOR = "app=llm-svc"
LLM_SVC_DEPLOYMENT_NAME = "llm-svc-deployment"

# vdb-redis-cluster: 3 sharded masters, NO replicas -> killing a member causes a
# brief partial outage (recovery), not a seamless failover. Data is expected to
# survive the restart (persistent storage), which is what the VDB test asserts.
VDB_POD_LABEL_SELECTOR = "app.kubernetes.io/name=redis-cluster"
# Per-pod stable label a StatefulSet stamps on each member. Used to wait for the
# specific killed member to come back, rather than a shared selector that also
# matches the surviving members (which never went down).
VDB_POD_NAME_LABEL = "statefulset.kubernetes.io/pod-name"

# Measured cold-recovery time for the LLM on spr8 was ~150-173 s (dominated by
# ~75 s vLLM engine warmup). The bge models are smaller and recover faster, but
# a single 300 s ceiling gives ~1.7x headroom for the slowest case on a loaded
# cluster without masking a genuine regression.
MODEL_SERVER_RECOVERY_TIMEOUT = 300
# Thin microservices and the redis cluster recover in seconds; 180 s is ample.
SERVICE_RECOVERY_TIMEOUT = 180

# After a model-server pod reports Ready, vLLM may still be starting its HTTP
# listener, so the first chatqa call can 5xx even though recovery is fine. Poll
# the post-recovery functional check instead of a single shot: 18 x 10 s = 3 min.
POST_RECOVERY_RETRIES = 18
POST_RECOVERY_RETRY_DELAY = 10

BASELINE_QUESTION = "What is the capital of France?"

# A document with a unique fact that cannot be answered from the model's own
# knowledge -> if chatqa surfaces it, it came from the vector DB via retrieval.
VDB_FACT_FILE = "test_chunks.txt"
VDB_FACT_QUESTION = "What is Corwenshirel?"
VDB_FACT_KEYWORD = "alderwynthiel"


def _model_workload_selector(role):
    """Label selector for the model-server workload pod serving `role`.

    The model name is read from the deployed catalog (config inference_models)
    instead of being hardcoded, because a cluster may serve any model for a
    given role. The KServe workload pod carries that name in
    app.kubernetes.io/name; kserve.io/component=workload narrows the selector to
    the pod that loads the model weights, excluding the co-located
    router-scheduler pod, which shares the name label but is a separate
    Deployment.

    Skips when no model is configured for the role — a pipeline variant may
    undeploy one (the upload variant is embedding-only).
    """
    model = next(
        (m["name"] for m in cfg.get("inference_models", []) if m.get("role") == role), None
    )
    if not model:
        pytest.skip(f"No model with role '{role}' in the deployed inference_models catalog")
    logger.info(f"Role '{role}' is served by model '{model}'")
    return f"kserve.io/component=workload,app.kubernetes.io/name={model}"


def _verify_recovery_after_pod_deletion(
    chatqa_api_helper, k8s_helper, component, namespace, label_selector,
    timeout=MODEL_SERVER_RECOVERY_TIMEOUT,
):
    """
    Shared recovery scenario: verify chatqa works, kill the pod(s) matching
    label_selector, wait for a fresh pod to become Ready, then verify chatqa
    works again.

    This is a recovery test (single replica -> a brief outage is expected), not
    a failover test. The assertion is functional (a chatqa request succeeds),
    not merely that the pod reports Ready, because model servers can report
    Ready before the inference engine is warmed up. The covered components
    (LLM, embedding, reranker, retriever) all sit on the chatqa request path, so
    a broken one surfaces as a failed chatqa call.
    """
    logger.info(f"Baseline: verifying chatqa answers before killing the {component} pod")
    chatqa_api_helper.ask_and_assert_answer(BASELINE_QUESTION, context="baseline")

    logger.info(f"Deleting the {component} pod to simulate a crash...")
    k8s_helper.delete_pods_by_label(namespace=namespace, label_selector=label_selector)

    logger.info(f"Waiting for a fresh {component} pod to become Ready...")
    start = time.monotonic()
    k8s_helper.wait_for_fresh_pod_ready(
        namespace=namespace,
        label_selector=label_selector,
        timeout=timeout,
    )
    recovery_time = round(time.monotonic() - start, 1)
    logger.info(f"{component} pod became Ready {recovery_time}s after deletion")

    logger.info(f"Verifying chatqa answers again after {component} recovery")
    chatqa_api_helper.ask_and_assert_answer(
        BASELINE_QUESTION, context="after recovery",
        retries=POST_RECOVERY_RETRIES, retry_delay=POST_RECOVERY_RETRY_DELAY,
    )


@allure.testcase("IEASG-T732")
def test_llm_recovery_after_pod_deletion(chatqa_api_helper, k8s_helper):
    """
    Kill the LLM workload pod (whatever model serves the 'llm' role) and verify
    the chatqa pipeline recovers: the pod comes back Ready and answers a real
    question again.
    """
    _verify_recovery_after_pod_deletion(
        chatqa_api_helper, k8s_helper,
        component="LLM", namespace=LLM_INFERENCE_NAMESPACE,
        label_selector=_model_workload_selector("llm"),
    )


@allure.testcase("IEASG-T733")
def test_embedding_recovery_after_pod_deletion(chatqa_api_helper, k8s_helper):
    """
    Kill the embedding workload pod (whatever model serves the 'embedding'
    role) and verify the chatqa pipeline recovers: the pod comes back Ready and
    answers a real question again.
    """
    _verify_recovery_after_pod_deletion(
        chatqa_api_helper, k8s_helper,
        component="embedding", namespace=LLM_INFERENCE_NAMESPACE,
        label_selector=_model_workload_selector("embedding"),
    )


@allure.testcase("IEASG-T734")
def test_reranker_recovery_after_pod_deletion(chatqa_api_helper, k8s_helper):
    """
    Kill the reranker workload pod (whatever model serves the 'reranking'
    role) and verify the chatqa pipeline recovers: the pod comes back Ready and
    answers a real question again.
    """
    _verify_recovery_after_pod_deletion(
        chatqa_api_helper, k8s_helper,
        component="reranker", namespace=LLM_INFERENCE_NAMESPACE,
        label_selector=_model_workload_selector("reranking"),
    )


@allure.testcase("IEASG-T735")
def test_retriever_svc_recovery_after_pod_deletion(chatqa_api_helper, k8s_helper):
    """
    Kill the retriever microservice pod (chatqa namespace) and verify the
    pipeline recovers: the pod comes back Ready and chatqa answers again. The
    retriever sits between the router and the vector DB, so its crash must not
    leave the pipeline permanently broken.
    """
    _verify_recovery_after_pod_deletion(
        chatqa_api_helper, k8s_helper,
        component="retriever-svc", namespace=CHATQNA_NAMESPACE,
        label_selector=RETRIEVER_SVC_POD_LABEL_SELECTOR,
        timeout=SERVICE_RECOVERY_TIMEOUT,
    )


@allure.testcase("IEASG-T736")
def test_llm_svc_failover_on_single_replica_deletion(chatqa_api_helper, k8s_helper):
    """
    Failover test: llm-svc runs 2 replicas. Kill ONE replica and verify chatqa
    still answers (the surviving replica serves the request), then confirm the
    deployment returns to full strength.

    This is sequential, not concurrent-load: it proves the service survives the
    loss of a replica, not that there was zero request interruption.
    """
    logger.info("Baseline: verifying chatqa answers before killing one llm-svc replica")
    chatqa_api_helper.ask_and_assert_answer(BASELINE_QUESTION, context="baseline")

    logger.info("Deleting a single llm-svc replica (the other should keep serving)...")
    deleted_pod = k8s_helper.delete_one_pod_by_label(
        namespace=CHATQNA_NAMESPACE,
        label_selector=LLM_SVC_POD_LABEL_SELECTOR,
    )
    logger.info(f"Deleted llm-svc replica '{deleted_pod}'")

    logger.info("Verifying chatqa still answers via the surviving replica")
    chatqa_api_helper.ask_and_assert_answer(
        BASELINE_QUESTION, context="during failover",
        retries=POST_RECOVERY_RETRIES, retry_delay=POST_RECOVERY_RETRY_DELAY,
    )

    # Confirm the killed pod is actually gone before checking for full
    # availability: a Deployment's readyReplicas can still count the Terminating
    # pod for a moment, which would let the availability check pass prematurely.
    logger.info(f"Waiting for the killed replica '{deleted_pod}' to be gone...")
    k8s_helper.wait_for_pod_gone(namespace=CHATQNA_NAMESPACE, pod_name=deleted_pod)

    logger.info("Waiting for the llm-svc deployment to return to full strength...")
    k8s_helper.wait_for_deployment_available(
        namespace=CHATQNA_NAMESPACE,
        name=LLM_SVC_DEPLOYMENT_NAME,
        timeout=SERVICE_RECOVERY_TIMEOUT,
    )
    logger.info("llm-svc deployment is fully available again")


@allure.testcase("IEASG-T737")
def test_vdb_data_survives_pod_deletion(chatqa_api_helper, edp_helper, k8s_helper):
    """
    Kill a vdb-redis-cluster member and verify ingested data survives the
    restart. vdb-redis-cluster is 3 sharded masters with no replicas, so a
    member deletion causes a brief partial outage (recovery), not a seamless
    failover.

    Flow: ingest a document with a unique fact, confirm the fact is retrievable
    (appears in the reranked docs), kill a redis member, wait for the cluster
    pod to be Ready again, then confirm the same fact is STILL retrievable -
    proving the data persisted across the restart. Grounding is asserted on the
    reranked docs (what the vector DB returned), not the LLM wording.
    """
    fact_file = os.path.join(DATAPREP_UPLOAD_DIR, VDB_FACT_FILE)
    with edp_helper.ephemeral_upload(fact_file):
        logger.info("Baseline: verifying the ingested fact is retrievable from the vector DB")
        response = chatqa_api_helper.call_chatqa(VDB_FACT_QUESTION)
        reranked_docs = chatqa_api_helper.get_reranked_docs(response)
        assert any(VDB_FACT_KEYWORD in doc.get("text", "").lower() for doc in reranked_docs), (
            f"baseline: expected '{VDB_FACT_KEYWORD}' in reranked docs before the VDB restart, "
            f"got {reranked_docs}"
        )

        logger.info("Deleting a vdb-redis-cluster member to simulate a crash...")
        deleted_pod = k8s_helper.delete_one_pod_by_label(
            namespace=VDB_NAMESPACE,
            label_selector=VDB_POD_LABEL_SELECTOR,
        )
        logger.info(f"Deleted vdb-redis-cluster member '{deleted_pod}'")

        # Wait for the specific killed member to come back. A StatefulSet reuses
        # the pod name and, right after deletion, still reports the old pod as
        # Ready, so waiting on the whole set (or the shared selector) can return
        # before the killed shard is actually back. Pinning to the pod-name
        # label restricts the wait to exactly the member that went down.
        logger.info(f"Waiting for the killed member '{deleted_pod}' to become Ready again...")
        k8s_helper.wait_for_fresh_pod_ready(
            namespace=VDB_NAMESPACE,
            label_selector=f"{VDB_POD_NAME_LABEL}={deleted_pod}",
            timeout=SERVICE_RECOVERY_TIMEOUT,
        )

        logger.info("Verifying the fact is STILL retrievable after the VDB restart")
        response = chatqa_api_helper.call_chatqa(VDB_FACT_QUESTION)
        reranked_docs = chatqa_api_helper.get_reranked_docs(response)
        assert any(VDB_FACT_KEYWORD in doc.get("text", "").lower() for doc in reranked_docs), (
            f"after recovery: expected '{VDB_FACT_KEYWORD}' in reranked docs after the VDB restart "
            f"(data should have survived), got {reranked_docs}"
        )
