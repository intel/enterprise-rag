#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Prove, end to end, that the dataprep guard reads its configuration from the
scope the dataprep worker serves (dataprep._global), not the chatqa scope the
other guard tests write to. The dataprep worker calls the fingerprint per-key
config route under its own pipeline; a guard config written to chatqa's scope
never reaches ingestion. This test writes the dataprep_guard group to the
dataprep scope and asserts the effect is observed at ingestion, so a scope
mismatch on that path fails here.

Distinct from test_in_guard_ban_substrings_when_string_injected_into_file,
which drives the chatqa input guard on the query: that test's redaction is
produced by the chatqa guard, so it cannot detect whether the dataprep guard
is configured at all. Here the observable is the ingestion outcome itself.

Needs a running cluster with the dataprep guard deployed; skipped otherwise.
"""

import allure
import logging
import os
import time

import pytest

from tests.e2e.validation.constants import DATAPREP_UPLOAD_DIR
from tests.e2e.validation.buildcfg import cfg

# Skip when the dataprep guard is not enabled: there is no ingestion-time guard
# to exercise. The guard defaults off, so the flag is usually absent -- treat
# absent as disabled. Fingerprint itself is always deployed, so it is not gated.
if not cfg.get("edp_dp_guard_enabled"):
    pytestmark = pytest.mark.skip(reason="Dataprep guard is not enabled (edp_dp_guard_enabled)")

logger = logging.getLogger(__name__)

_BANNED_SUBSTRING = "Zerquilloo"
_FILE_WITH_BANNED_SUBSTRING = "word_zerquilloo_in_file.txt"

# The dataprep worker sets a file to "blocked" when the guard rejects it (a 466
# from the dpguard service). "blocked" is a terminal state outside the normal
# ingestion flow, so it is polled for directly rather than through the
# flow-ordered status helper.
_BLOCKED_STATUS = "blocked"
_BLOCK_POLL_TIMEOUT_SECONDS = 180
_BLOCK_POLL_INTERVAL_SECONDS = 10

# States that end polling: the expected block, a successful ingest (guard did
# not fire -- the failure this test guards against), or a generic error (the
# dpguard service can also surface a non-466 failure as "error"). Stopping on
# all of them keeps a wrong outcome from waiting out the full timeout.
_TERMINAL_STATUSES = frozenset({_BLOCKED_STATUS, "ingested", "error"})


def _presigned_url(edp_helper, filename, method="PUT"):
    """Returns a presigned URL for filename, asserting the presign call succeeded."""
    response = edp_helper.generate_presigned_url(filename, method=method)
    assert response.status_code == 200, (
        f"Presign ({method}) for '{filename}' failed with {response.status_code}: {response.text[:200]}")
    url = response.json().get("url")
    assert url, f"Presign ({method}) for '{filename}' returned no url: {response.text[:200]}"
    return url


def _file_status(edp_helper, filename):
    """Returns the current EDP status of filename, or None if not listed yet."""
    response = edp_helper.list_files()
    assert response.status_code == 200, (
        f"Listing EDP files failed with {response.status_code}: {response.text[:200]}")
    for file in response.json():
        object_name = file.get("object_name", "")
        if object_name == filename or object_name.endswith("/" + filename):
            return file.get("status")
    return None


def _wait_for_terminal_status(edp_helper, filename):
    """Polls until filename reaches a terminal status, or times out returning the last status."""
    deadline = time.monotonic() + _BLOCK_POLL_TIMEOUT_SECONDS
    status = _file_status(edp_helper, filename)
    while status not in _TERMINAL_STATUSES and time.monotonic() < deadline:
        time.sleep(_BLOCK_POLL_INTERVAL_SECONDS)
        status = _file_status(edp_helper, filename)
    return status


@pytest.fixture(autouse=True)
def restore_dataprep_guard(guard_helper):
    # Disable the dataprep guard after the test so a left-on block does not
    # affect later ingestion. The store is update-only, so it is disabled rather
    # than deleted. A failed restore is a test failure: leaving the guard on
    # would block unrelated ingestion tests later in the run.
    yield
    response = guard_helper.setup_dataprep("ban_substrings", {"enabled": False})
    assert response.status_code == 200, (
        f"Failed to disable the dataprep guard on teardown ({response.status_code}); "
        f"it may stay enabled and block later ingestion. {response.text[:200]}")


@allure.testcase("IEASG-T697")
def test_dataprep_guard_config_reaches_ingestion(guard_helper, edp_helper):
    """
    Enabling ban_substrings on the dataprep guard scope must block ingestion of
    a file that carries the banned substring. A block is an outcome only the
    dataprep guard can produce, so observing it proves the guard read its
    configuration from the dataprep scope.
    """
    # Block (not redact) so the outcome is an unambiguous ingestion failure the
    # chatqna guard cannot produce.
    guard_helper.setup_dataprep(
        "ban_substrings",
        {"enabled": True, "substrings": [_BANNED_SUBSTRING], "case_sensitive": False, "redact": False})

    filename = _FILE_WITH_BANNED_SUBSTRING
    file_path = os.path.join(DATAPREP_UPLOAD_DIR, filename)
    upload = edp_helper.upload_file(file_path, _presigned_url(edp_helper, filename))
    assert upload.status_code == 200, "Upload to the presigned URL failed"

    try:
        status = _wait_for_terminal_status(edp_helper, filename)
        assert status == _BLOCKED_STATUS, (
            f"Dataprep guard did not block '{filename}' (status was '{status}'). "
            f"The guard config is written to the dataprep scope; an 'ingested' status means "
            f"it never reached the dataprep worker (a scope mismatch on the EDP read path).")
        logger.info(f"Ingestion of '{filename}' was blocked by the dataprep guard, as expected")
    finally:
        # Remove the uploaded file so a re-run starts clean. A failed delete is
        # not fatal to this test but is logged so leftover objects that could
        # make a rerun flaky are visible.
        delete = edp_helper.delete_file(_presigned_url(edp_helper, filename, method="DELETE"))
        if delete.status_code != 204:
            logger.warning(
                f"Cleanup delete of '{filename}' returned {delete.status_code}; "
                f"a leftover object may affect a rerun. {delete.text[:200]}")
