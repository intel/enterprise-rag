#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Runs after `es_auto_installer.sh backup --env <env>`.

Proves the backup recorded the data created before it, then creates more data
that the restore has to roll back.

The backup under test is the newest one the installer's engine labelled with
this solution's profile — not "every Backup in the namespace", which would also
judge restore points taken for something else, including ones a negative test
made fail on purpose.
"""

import allure
import logging
import os
import pytest

from tests.e2e.lifecycle.backup_data import (
    POST_BACKUP_ANSWER,
    POST_BACKUP_FILE,
    POST_BACKUP_QUESTION,
    POST_BACKUP_USER,
)
from tests.e2e.validation.constants import (
    BACKED_UP_DATA_NAMESPACES,
    BACKUP_PROFILE_LABEL,
    BACKUP_PROFILE_NAME,
    BACKUP_VERSION_LABEL,
    DATAPREP_UPLOAD_DIR,
    IDENTITY_DATABASE_NAMESPACE,
    VELERO_NAMESPACE,
)


@pytest.fixture(autouse=True)
def edp_cleanup_after_test():
    """No-op override: files must persist for post-restore verification."""
    yield


@pytest.fixture(scope="session", autouse=True)
def edp_cleanup_after_session():
    """No-op override: files must persist for post-restore verification."""
    yield

logger = logging.getLogger(__name__)


def latest_profile_backup(k8s_helper):
    """The newest Backup the engine created for this solution's profile."""
    backups = k8s_helper.get_backups(
        namespace=VELERO_NAMESPACE,
        label_selector={BACKUP_PROFILE_LABEL: BACKUP_PROFILE_NAME},
    )
    assert backups, (
        f"No Backup labelled {BACKUP_PROFILE_LABEL}={BACKUP_PROFILE_NAME} in '{VELERO_NAMESPACE}'. "
        f"Take one with: ./es_auto_installer.sh backup --env <env>"
    )
    # RFC 3339 timestamps sort lexicographically.
    return sorted(backups, key=lambda b: b.metadata["creationTimestamp"])[-1]


@allure.testcase("IEASG-T313")
def test_post_backup_backup_created(k8s_helper):
    """
    Check the backup is a usable restore point.
    1. The newest Backup for this profile completed.
    2. It records the solution version, which the upgrade gate matches on.
    3. It covers the namespaces holding the data created before it.
    4. It captured volume contents, not only object metadata.
    5. No pod in the velero namespace is failing.
    """
    backup = latest_profile_backup(k8s_helper)
    status = backup.raw.get("status", {})
    logger.info(f"Backup {backup.name}: {status}")

    assert status.get("phase") == "Completed", (
        f"Backup {backup.name} is {status.get('phase')}, not Completed."
    )

    version = backup.metadata.get("labels", {}).get(BACKUP_VERSION_LABEL, "")
    assert version and version != "unknown", (
        f"Backup {backup.name} carries no {BACKUP_VERSION_LABEL} label ('{version}'). "
        f"The pre-upgrade gate looks restore points up by it, and would match any version's."
    )

    included = backup.raw.get("spec", {}).get("includedNamespaces", [])
    missing = [ns for ns in BACKED_UP_DATA_NAMESPACES if ns not in included]
    assert not missing, (
        f"Backup {backup.name} does not cover {missing} (covers {included}). Data in those "
        f"namespaces cannot be restored — check namespace_order in deployment/backup_profile.yaml."
    )

    # A Backup reaches Completed whether or not a single volume was snapshotted, so
    # the counts are the only evidence the contents were captured. Velero deletes
    # the transient VolumeSnapshot objects at finalization; these survive on it.
    attempted = status.get("csiVolumeSnapshotsAttempted", 0)
    completed = status.get("csiVolumeSnapshotsCompleted", 0)
    assert attempted > 0, (
        f"Backup {backup.name} attempted no CSI volume snapshots: it holds object metadata only. "
        f"Check that the storage backend is CSI-snapshot-capable and a VolumeSnapshotClass exists."
    )
    assert completed == attempted, (
        f"Backup {backup.name} completed {completed} of {attempted} CSI volume snapshots."
    )

    assert status.get("progress", {}).get("itemsBackedUp", 0) > 0, (
        f"Backup {backup.name} recorded no items."
    )

    for pod in k8s_helper.list_pods(namespace=VELERO_NAMESPACE):
        logger.debug(f"Pod Name: {pod.name}, Status: {pod.status.phase}")
        assert pod.status.phase not in ["Error", "CrashLoopBackOff"], (
            f"Pod {pod.name} is in {pod.status.phase} status."
        )


# No test-case id yet: assign one when this check is registered.
def test_post_backup_identity_database_volume_captured(k8s_helper):
    """
    The identity realm is captured as the volume it lives on, like every other
    store in the profile: it is a database in the platform's shared PostgreSQL
    cluster, and that cluster's namespace is in the profile's namespace list.

    A Backup reaches Completed whether or not any particular volume was
    snapshotted, so what is asserted is that the database has a volume and that
    the backup attempted at least as many snapshots as there are volumes in the
    namespaces the test data lives in. One volume silently left out is the way
    this fails.
    """
    backup = latest_profile_backup(k8s_helper)

    db_pvcs = [pvc.name for pvc in k8s_helper.list_pvcs(namespace=IDENTITY_DATABASE_NAMESPACE)]
    assert db_pvcs, (
        f"Namespace '{IDENTITY_DATABASE_NAMESPACE}' has no PersistentVolumeClaim, so the realm is "
        f"not on a volume this backup could have captured."
    )
    logger.info(f"Identity database volumes: {db_pvcs}")

    expected = [
        f"{namespace}/{pvc.name}"
        for namespace in BACKED_UP_DATA_NAMESPACES
        for pvc in k8s_helper.list_pvcs(namespace=namespace)
    ]
    attempted = backup.raw.get("status", {}).get("csiVolumeSnapshotsAttempted", 0)
    assert attempted >= len(expected), (
        f"Backup {backup.name} attempted {attempted} volume snapshots for {len(expected)} volumes "
        f"holding test data ({expected}). At least one was skipped — check that every namespace in "
        f"namespace_order uses a snapshot-capable StorageClass."
    )


@allure.testcase("IEASG-T314")
def test_post_backup_data_ingested_after_backup(keycloak_helper, edp_helper, chat_history_helper):
    """
    Ingest some data which should not be present in the backup since backup was already created.
    1. Upload a file to the system via EDP.
    2. Create a chat history via Chat History API.
    3. Create a new user in Keycloak.
    """
    # Upload a file
    edp_helper.upload_file_and_wait_for_ingestion(os.path.join(DATAPREP_UPLOAD_DIR, POST_BACKUP_FILE))

    # Create chat history
    chat_history_helper.save_history([
        {
            "question": POST_BACKUP_QUESTION,
            "answer": POST_BACKUP_ANSWER,
            "metadata": {}
        }
    ])

    # Create a new user
    if not keycloak_helper.user_exists(POST_BACKUP_USER):
        keycloak_helper.add_user(
            POST_BACKUP_USER, "PostBackupPass123!", "PostBackupUser", "PostBackupSurname",
            "postbackup@example.com"
        )
