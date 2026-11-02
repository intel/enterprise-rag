#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Guard tests skip the guards the deployed pipeline variant does not contain.

The fingerprint store seeds every guard group whether or not its step is
deployed, so a guard test on a variant without that guard would write a config
nothing reads and fail. The deployed guards are derived from the repo's own
pipeline and variant files; these tests read the real files, so a variant that
adds or drops a guard step is reflected here without a second list.
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.e2e.helpers.guard_helper import GuardHelper, GuardType, deployed_guard_types


@pytest.mark.parametrize("pipeline_type, pipeline_variant, expected", [
    ("chatqna", "base", (GuardType.INPUT,)),
    ("chatqna", "output_guard", (GuardType.INPUT, GuardType.OUTPUT)),
    ("chatqna", "retrieve-rerank", ()),
    ("chatqna", "upload", ()),
    ("docsum", "base", ()),
])
def test_deployed_guard_types_follow_the_variant(pipeline_type, pipeline_variant, expected):
    assert deployed_guard_types(pipeline_type, pipeline_variant) == expected


def test_setup_skips_a_guard_that_is_not_deployed():
    fingerprint = MagicMock()
    guard_helper = GuardHelper(MagicMock(), fingerprint, deployed_guard_types=(GuardType.INPUT,))

    with pytest.raises(pytest.skip.Exception, match="output_guard is not deployed"):
        guard_helper.setup(GuardType.OUTPUT, "regex", {"enabled": True})
    fingerprint.change_arguments.assert_not_called()


def test_disable_all_guards_touches_only_deployed_guards():
    fingerprint = MagicMock()
    fingerprint.read_config.return_value = MagicMock(
        status_code=200, json=lambda: {"values": {"input_guardrail_params": {}}})
    guard_helper = GuardHelper(MagicMock(), fingerprint, deployed_guard_types=(GuardType.INPUT,))

    with patch("tests.e2e.helpers.guard_helper.time.sleep"):
        guard_helper.disable_all_guards()

    read_keys = [call.args[0] for call in fingerprint.read_config.call_args_list]
    assert read_keys == [GuardType.INPUT.value]
