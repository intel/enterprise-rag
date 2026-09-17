#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Runs before `es_auto_installer.sh backup --env <env>`.

Creates the data the round trip is judged on, and first checks the two engine
preconditions whose absence would otherwise be diagnosed as data loss: no
storage location to write to, and no snapshot class — which produces a Backup
that reaches Completed holding object metadata and no volume contents.
"""

import allure
import logging
import os
import pytest

from tests.e2e.lifecycle.backup_data import (
    PRE_BACKUP_ANSWER,
    PRE_BACKUP_FILE,
    PRE_BACKUP_QUESTION,
    PRE_BACKUP_USER,
)
from tests.e2e.validation.constants import DATAPREP_UPLOAD_DIR, VELERO_NAMESPACE


@pytest.fixture(autouse=True)
def edp_cleanup_after_test():
    """No-op override: files must persist for post-restore verification."""
    yield


@pytest.fixture(scope="session", autouse=True)
def edp_cleanup_after_session():
    """No-op override: files must persist for post-restore verification."""
    yield

logger = logging.getLogger(__name__)


# No test-case id yet: assign one when this check is registered.
def test_pre_backup_engine_is_ready(k8s_helper):
    """
    The backup engine can produce a usable restore point:
    1. The velero namespace exists and no pod in it is failing.
    2. At least one BackupStorageLocation is Available.
    3. The cluster has a VolumeSnapshotClass, without which volume contents are
       not captured at all.
    """
    assert k8s_helper.get_namespace(VELERO_NAMESPACE) is not None, (
        f"Namespace '{VELERO_NAMESPACE}' does not exist — install the velero component first."
    )

    pods = k8s_helper.list_pods(namespace=VELERO_NAMESPACE)
    assert pods, f"No pods in namespace '{VELERO_NAMESPACE}'."
    for pod in pods:
        logger.debug(f"Pod {pod.name}: {pod.status.phase}")
        assert pod.status.phase not in ["Error", "CrashLoopBackOff", "Failed"], (
            f"Pod {pod.name} is in {pod.status.phase} status."
        )

    locations = k8s_helper.get_backup_storage_locations(namespace=VELERO_NAMESPACE)
    assert locations, f"No BackupStorageLocation in '{VELERO_NAMESPACE}'."
    phases = {loc.name: loc.raw.get("status", {}).get("phase") for loc in locations}
    logger.info(f"Backup storage locations: {phases}")
    assert "Available" in phases.values(), (
        f"No BackupStorageLocation is Available: {phases}. A backup would fail to upload."
    )

    classes = k8s_helper.get_volume_snapshot_classes()
    logger.info(f"Volume snapshot classes: {[c.name for c in classes]}")
    assert classes, (
        "No VolumeSnapshotClass in the cluster. The backup would complete with object "
        "metadata and no volume contents, and the restore would come back empty."
    )


@allure.testcase("IEASG-T312")
def test_pre_backup(keycloak_helper, edp_helper, chat_history_helper):
    """
    Prepare data for backup:
    1. Upload a file to the system via EDP.
    2. Create a chat history via Chat History API.
    3. Create a new user in Keycloak.
    """
    # Populate db
    edp_helper.upload_file_and_wait_for_ingestion(os.path.join(DATAPREP_UPLOAD_DIR, PRE_BACKUP_FILE))

    # Populate chat history
    chat_history_helper.save_history([
        {
            "question": PRE_BACKUP_QUESTION,
            "answer": PRE_BACKUP_ANSWER,
            "metadata": {}
        }
    ])

    # Add new user if it does not exist. It has to exist before the backup: the
    # account lives in the realm, the realm lives in the shared database, and the
    # backup captures that database as the volume it sits on.
    if not keycloak_helper.user_exists(PRE_BACKUP_USER):
        keycloak_helper.add_user(
            PRE_BACKUP_USER, "PreBackupPass123!", "BackupUser", "BackupSurname", "backup@example.com"
        )
