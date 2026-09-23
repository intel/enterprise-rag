#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Runs after `es_auto_installer.sh restore --env <env> --force`.

Three claims, in the order they can fail:
  the restore itself completed;
  the data created before the backup is back and readable through the APIs;
  the data created after the backup is gone.

Accounts are part of that comparison. The realm lives in a database whose volume
the backup captures, so an account created before the backup is there afterwards
and one created after it is not.
"""

import allure
import logging
import pytest

from tests.e2e.lifecycle.backup_data import (
    POST_BACKUP_FILE,
    POST_BACKUP_HISTORY_MARKER,
    POST_BACKUP_USER,
    POST_RESTORE_ANSWER_KEYWORD,
    POST_RESTORE_QUESTION,
    PRE_BACKUP_FILE,
    PRE_BACKUP_HISTORY_MARKER,
    PRE_BACKUP_USER,
)
from tests.e2e.validation.constants import (
    BACKED_UP_DATA_NAMESPACES,
    BACKUP_PROFILE_LABEL,
    BACKUP_PROFILE_NAME,
    VELERO_NAMESPACE,
)

logger = logging.getLogger(__name__)

# Velero stamps every object it recreates with the Restore that recreated it.
RESTORE_NAME_LABEL = "velero.io/restore-name"


def latest_profile_restore(k8s_helper):
    """The newest Restore the engine created for this solution's profile."""
    restores = k8s_helper.get_restores(
        namespace=VELERO_NAMESPACE,
        label_selector={BACKUP_PROFILE_LABEL: BACKUP_PROFILE_NAME},
    )
    assert restores, (
        f"No Restore labelled {BACKUP_PROFILE_LABEL}={BACKUP_PROFILE_NAME} in '{VELERO_NAMESPACE}'. "
        f"Run: ./es_auto_installer.sh restore --env <env> --force"
    )
    return sorted(restores, key=lambda r: r.metadata["creationTimestamp"])[-1]


# No test-case id yet: assign one when this check is registered.
def test_post_restore_restore_completed(k8s_helper):
    """
    1. The newest Restore for this profile completed.
    2. It replayed a backup taken for this profile, not an unrelated one.
    3. Every workload the restore recreated is running: a restored volume whose
       ownership was lost is invisible until the database on it refuses to start.
    """
    restore = latest_profile_restore(k8s_helper)
    status = restore.raw.get("status", {})
    logger.info(f"Restore {restore.name}: {status}")

    assert status.get("phase") == "Completed", (
        f"Restore {restore.name} is {status.get('phase')}, not Completed. "
        f"Warnings do not prevent Completed; errors do."
    )
    assert status.get("progress", {}).get("itemsRestored", 0) > 0, (
        f"Restore {restore.name} replayed no items."
    )

    backup_name = restore.raw.get("spec", {}).get("backupName", "")
    assert backup_name, f"Restore {restore.name} names no backup."
    profile_backups = [
        b.name for b in k8s_helper.get_backups(
            namespace=VELERO_NAMESPACE,
            label_selector={BACKUP_PROFILE_LABEL: BACKUP_PROFILE_NAME},
        )
    ]
    assert backup_name in profile_backups, (
        f"Restore {restore.name} replayed '{backup_name}', which is not one of this profile's "
        f"backups ({profile_backups})."
    )

    for namespace in BACKED_UP_DATA_NAMESPACES:
        if k8s_helper.get_namespace(namespace) is None:
            pytest.fail(f"Namespace '{namespace}' does not exist after the restore.")
        for pvc in k8s_helper.list_pvcs(namespace=namespace):
            phase = pvc.raw.get("status", {}).get("phase")
            assert phase == "Bound", f"PVC {namespace}/{pvc.name} is {phase}, not Bound."
        for pod in k8s_helper.list_pods(namespace=namespace):
            phase = pod.status.phase
            # Job and CronJob pods are transient by design: a scheduled pod is Pending for a
            # few seconds every time it fires, so asserting on it makes this test fail on
            # timing rather than on the restore. rag-utils-watcher runs every two minutes.
            owners = {o.get("kind") for o in (pod.raw.get("metadata", {}).get("ownerReferences") or [])}
            if owners & {"Job", "CronJob"}:
                logger.debug(f"Pod {namespace}/{pod.name}: {phase} (owned by {sorted(owners)}, skipped)")
                continue
            logger.debug(f"Pod {namespace}/{pod.name}: {phase}")
            assert phase in ["Running", "Succeeded"], (
                f"Pod {namespace}/{pod.name} is {phase} after the restore. A store that will not "
                f"start on its restored volume is the usual cause."
            )


@allure.testcase("IEASG-T315")
def test_post_restore_data_exists(keycloak_helper, edp_helper, chat_history_helper, chatqa_api_helper):
    """
    1. Verify that the previously uploaded file is present in the system.
    2. Verify that the chat history is present.
    3. Ask a question about the pre-backup document, which can only be answered
       from the restored embeddings.
    4. Verify the account created before the backup is back in the realm.
    """
    # Verify uploaded file exists
    files = edp_helper.list_files()
    for item in files.json():
        if PRE_BACKUP_FILE in item['object_name']:
            logger.debug(f"File found: {item['object_name']}")
            break
    else:
        pytest.fail(f"File {PRE_BACKUP_FILE} not found after restore.")

    # Verify chat history exists
    response = chat_history_helper.get_all_histories()
    all_history_names = [history["history_name"] for history in response.json()]
    logger.debug(f"All histories: {all_history_names}")
    for history in all_history_names:
        if PRE_BACKUP_HISTORY_MARKER in history:
            logger.debug(f"Chat history found: {history}")
            break
    else:
        pytest.fail("Chat history not found after restore.")

    response = chatqa_api_helper.call_chatqa(POST_RESTORE_QUESTION)
    assert response.status_code == 200, "Unexpected status code returned"
    response_text = chatqa_api_helper.get_text(response)
    logger.info(f"ChatQA response: {response_text}")
    assert POST_RESTORE_ANSWER_KEYWORD in response_text.lower(), (
        "Unexpected answer from ChatQA after restore"
    )

    assert keycloak_helper.user_exists(PRE_BACKUP_USER), (
        f"User '{PRE_BACKUP_USER}' is not in the realm after the restore. The realm is in the "
        f"database whose volume the backup captured, so it should have come back with the rest."
    )


@allure.testcase("IEASG-T316")
def test_post_restore_data_does_not_exists(keycloak_helper, edp_helper, chat_history_helper):
    """
    Check that data ingested after the backup does not exist after the restore.
    Accounts included: the realm is rolled back with the volume it lives on.
    """
    # Verify uploaded file does not exist
    files = edp_helper.list_files()
    for item in files.json():
        if POST_BACKUP_FILE in item['object_name']:
            pytest.fail(f"File {POST_BACKUP_FILE} found after restore, but it should not be present.")

    # Verify chat history does not exist
    response = chat_history_helper.get_all_histories()
    all_history_names = [history["history_name"] for history in response.json()]
    logger.debug(f"All histories: {all_history_names}")
    for history in all_history_names:
        if POST_BACKUP_HISTORY_MARKER in history:
            pytest.fail("Chat history found after restore, but it should not be present.")

    assert not keycloak_helper.user_exists(POST_BACKUP_USER), (
        f"User '{POST_BACKUP_USER}' is still in the realm after the restore. It was created after "
        f"the backup, so replaying the volume the realm lives on should have removed it."
    )
