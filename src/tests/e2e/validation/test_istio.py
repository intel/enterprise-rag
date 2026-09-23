#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import allure
import logging
import pytest
import kr8s

from tests.e2e.helpers.istio_helper import ConnectionType
from tests.e2e.validation.buildcfg import cfg

# Skip all tests if istio is not deployed
istio_enabled = cfg.get("istio_enabled")
if not istio_enabled:
    pytestmark = pytest.mark.skip(reason="Istio is not deployed")

logger = logging.getLogger(__name__)


# List of endpoints to test
http_endpoints = [
    # Ingress endpoints - allowed from anywhere
    # "ingress-nginx-controller.ingress-nginx.svc.cluster.local:80",
    # "ingress-nginx-controller-admission.ingress-nginx.svc.cluster.local:443",
    # # Rag-ui endpoints
    "ui-chart.rag-ui.svc.cluster.local:4173"
    # System endpoints
    # disabled because gmc needs to be open to connections from kube-apiserver
    # "gmc-controller.system.svc.cluster.local:9443"
]

chatqna_endpoints = [
    "embedding-svc.chatqna.svc.cluster.local:6000",
    "input-scan-svc.chatqna.svc.cluster.local:8050",
    "llm-svc.chatqna.svc.cluster.local:9000",
    # Output guards disabled
    # "output-scan-svc.chatqna.svc.cluster.local:8060",
    "prompt-template-svc.chatqna.svc.cluster.local:7900",
    # "redis-vector-db.chatqna.svc.cluster.local:6379",
    "reranking-svc.chatqna.svc.cluster.local:8000",
    "retriever-svc.chatqna.svc.cluster.local:6620",
    "router-service.chatqna.svc.cluster.local:8080",
    # Model servers are no longer deployed in the pipeline namespace: every model is served by
    # Model Manager as <model-name>-kserve-workload-svc.<inference-ns>.svc:8000, reached through
    # the AI gateway for the LLM. Those services are outside the pipeline authorization policies,
    # so they are not listed here.
]
if cfg.get("pipeline_type") == "chatqna":
    http_endpoints.extend(chatqna_endpoints)

edp_endpoints = [
    "edp-text-extractor-headless.edp.svc.cluster.local:9398",
    "edp-text-compression.edp.svc.cluster.local:9397",
    "edp-text-splitter.edp.svc.cluster.local:9399",
    "edp-ingestion.edp.svc.cluster.local:6120",
    "edp-backend.edp.svc.cluster.local:5000",
    # edp-celery is a Celery worker with no listener on 5000; ztunnel logs a transport error
    # instead of a policy rejection, so the query can never be verified either way.
    # "edp-celery.edp.svc.cluster.local:5000",
    "edp-flower.edp.svc.cluster.local:5555",
]
if cfg.get("edp_enabled"):
    http_endpoints.extend(edp_endpoints)

seaweedfs_endpoints = [
    "seaweedfs-s3.seaweedfs.svc.cluster.local:8333",
]
if cfg.get("edp_enabled") and cfg.get("edp_storage_type", "seaweedfs") == "seaweedfs":
    http_endpoints.extend(seaweedfs_endpoints)

fingerprint_endpoints = [
    "fingerprint-svc.fingerprint.svc.cluster.local:6012",
]
http_endpoints.extend(fingerprint_endpoints)

docsum_endpoints = [
    "docsum-svc.docsum.svc.cluster.local:9001",
    "llm-svc.docsum.svc.cluster.local:9000",
    "router-service.docsum.svc.cluster.local:8080",
    "text-compression-svc.docsum.svc.cluster.local:9397",
    "text-extractor-svc.docsum.svc.cluster.local:9398",
    "text-splitter-svc.docsum.svc.cluster.local:9399",
]
if cfg.get("pipeline_type") == "docsum":
    http_endpoints.extend(docsum_endpoints)

# Service names follow the Helm release names pinned in the core installer's
# roles/observability/tasks/install.yaml (kube-prometheus-stack, loki, tempo,
# opentelemetry-collector), all in the single `monitoring` namespace.
telemetry_endpoints = [
    # alertmanager-operated:9094 is the Alertmanager cluster gossip port with no listener
    # reachable outside the peer set; ztunnel logs a transport error rather than a policy
    # rejection, so the query can never be verified. The authz policy still protects it.
    # "alertmanager-operated.monitoring.svc.cluster.local:9094",
    "loki-canary.monitoring.svc.cluster.local:3500",
    # loki-memberlist is a headless service; ready_pods() returns [] so ztunnel log lines
    # can never be matched — verify_query_blocked always TIMEOUTs. The authz policy still protects it.
    # "loki-memberlist.monitoring.svc.cluster.local:7946",
    # prometheus-adapter serves Kubernetes aggregated API called by kube-apiserver (not in mesh)
    # "prometheus-adapter.monitoring.svc.cluster.local:443",
    "prometheus-operated.monitoring.svc.cluster.local:9090",
    "kube-prometheus-stack-grafana.monitoring.svc.cluster.local:80",
    "kube-prometheus-stack-alertmanager.monitoring.svc.cluster.local:8080",
    "kube-prometheus-stack-operator.monitoring.svc.cluster.local:443",
    "kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090",
    "kube-prometheus-stack-kube-state-metrics.monitoring.svc.cluster.local:8080",
    "loki.monitoring.svc.cluster.local:3100",
    "loki.monitoring.svc.cluster.local:9095",
    "kube-prometheus-stack-alertmanager.monitoring.svc.cluster.local:9093",
    # The trace pipeline runs in this namespace under the release names the installer
    # pins, not in a separate monitoring-traces namespace.
    "tempo.monitoring.svc.cluster.local:3200",
    "tempo.monitoring.svc.cluster.local:4318",
    "opentelemetry-collector.monitoring.svc.cluster.local:4317",
    "opentelemetry-collector.monitoring.svc.cluster.local:4318",
    # Loki caches only exist when observability_loki_cache_enabled is set (default false).
    # Loki object storage is the platform object_store, not a Loki-owned MinIO release.
    # Node exporter access cannot be restricted
    # "kube-prometheus-stack-prometheus-node-exporter.monitoring.svc.cluster.local:9100",
]
if cfg.get("telemetry_enabled") or cfg.get("observability_enabled"):
    http_endpoints.extend(telemetry_endpoints)

audio_endpoints = [
    "asr-svc.audio.svc.cluster.local:9009",
    "namespace-status-watcher-svc.audio.svc.cluster.local:9010",
    "tts-fastapi-model-server.audio.svc.cluster.local:8008",
    "tts-svc.audio.svc.cluster.local:9009",
    "vllm-audio-cpu.audio.svc.cluster.local:8008",
]
if cfg.get("audio_enabled"):
    http_endpoints.extend(audio_endpoints)

redis_endpoints = [
    # gets populated within prepare_tests fixture
]

# Keycloak no longer ships its own Postgres; it uses the shared CNPG cluster created by
# the core installer's postgresql role (postgresql_cluster_name, namespace postgresql).
postgres_endpoints = [
    "postgresql-rw.postgresql.svc.cluster.local:5432"
]
if cfg.get("edp_enabled"):
    postgres_endpoints.append("edp-postgresql.edp.svc.cluster.local:5432")
postgres_endpoints.append("fingerprint-postgresql.fingerprint.svc.cluster.local:5432")


mongodb_endpoints = []

istio_test_data = {
    ConnectionType.HTTP: http_endpoints,
    ConnectionType.REDIS: redis_endpoints,
    ConnectionType.MONGODB: mongodb_endpoints,
    ConnectionType.POSTGRESQL: postgres_endpoints
}


def get_vector_db_endpoints():
    if not cfg.get("vector_databases_enabled"):
        return []

    # Check for redis-cluster implementation first
    try:
        services = list(kr8s.get("services", "vdb-redis-cluster-headless", namespace="vdb"))
        if len(services) == 1:
            service = services[0]
            logger.info("Found redis-cluster vector DB service: %s", service.name)
            return [f"{service.name}.vdb.svc.cluster.local:6379"]
    except (RuntimeError, ValueError, AttributeError):
        pass

    # Check for redis implementation
    try:
        services = list(kr8s.get("services", "vdb-redis-headless", namespace="vdb"))
        if len(services) == 1:
            service = services[0]
            logger.info("Found redis vector DB service: %s", service.name)
            return [f"{service.name}.vdb.svc.cluster.local:6379"]
    except (RuntimeError, ValueError, AttributeError):
        pass

    raise RuntimeError("No vector database services found with expected names (vdb-redis-cluster or vdb-redis)")


def get_edp_redis_endpoints():
    if cfg.get("edp_enabled"):
        return ["edp-redis.edp.svc.cluster.local:6379"]
    return []


@pytest.fixture(scope="module", autouse=True)
def prepare_tests(istio_helper):
    logger.info("============= Prepare Istio Authorization tests =====================")

    # Dynamically populate redis endpoints
    redis_endpoints.extend(get_edp_redis_endpoints())
    redis_endpoints.extend(get_vector_db_endpoints())

    istio_helper.create_namespace(inmesh=True)
    endpoints = {endpoint: connection_type for connection_type, endpoint_list in istio_test_data.items() for endpoint in endpoint_list}
    sample_endpoints = dict(list(endpoints.items())[:7])
    istio_helper.sample_log_timestamp_offsets()
    istio_helper.query_multiple_endpoints(dict(sample_endpoints))
    log_ts_offset = istio_helper.apply_log_timestamp_offsets()
    if log_ts_offset < 0:
        logger.warning("Detected negative time offset %s sec between kubernetes log and test host", log_ts_offset)
    else:
        logger.info("Detected time offset %s sec between kubernetes log and test host", log_ts_offset)
    istio_helper.delete_namespace()
    yield


@pytest.mark.skip(reason="TestIstioInMesh disabled until evaluation is done")
class TestIstioInMesh:

    @pytest.fixture(autouse=True, scope="class")
    def cleanup(self, istio_helper):
        logger.info("============= TestIstioInMesh setup =====================")
        istio_helper.create_namespace(inmesh=True)
        yield
        istio_helper.delete_namespace()

    @allure.testcase("IEASG-T142")
    def test_authorization_gets_connections_blocked(self, istio_helper):
        endpoints = {endpoint: connection_type for connection_type, endpoint_list in istio_test_data.items() for endpoint in endpoint_list}
        connections_not_blocked = check_if_connections_blocked(istio_helper, endpoints)
        assert connections_not_blocked == []


class TestIstioOutOfMesh:

    @pytest.fixture(autouse=True, scope="class")
    def cleanup(self, istio_helper):
        logger.info("============= TestIstioOutOfMesh setup =====================")
        istio_helper.create_namespace(inmesh=False)
        yield
        istio_helper.delete_namespace()

    @allure.testcase("IEASG-T146")
    def test_authorization_gets_connections_blocked(self, istio_helper):
        endpoints = {endpoint: connection_type for connection_type, endpoint_list in istio_test_data.items() for endpoint in endpoint_list}
        connections_not_blocked = check_if_connections_blocked(istio_helper, endpoints)
        assert connections_not_blocked == []


def check_if_connections_blocked(istio_helper, endpoints: dict[str, ConnectionType]):
    return istio_helper.query_multiple_endpoints(endpoints)
