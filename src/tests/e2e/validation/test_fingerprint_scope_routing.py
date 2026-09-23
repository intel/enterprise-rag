#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Prove, end to end, that a fingerprint write reaches the chatqna router only when
it names the scope the router reads. A write to chatqna's scope must change what
chatqna does; a write to a different scope must not. max_new_tokens is used only
as a cheap, observable vehicle -- the assertion is about which scope the router
picks up, not about the knob.

Needs a running cluster; skipped like the other fingerprint e2e tests when the
service is not deployed.
"""

import allure
import logging
import time

import pytest


from tests.e2e.helpers.guard_helper import CHATQNA_PIPELINE, GLOBAL_TENANT
from tests.e2e.validation.buildcfg import cfg

# The observable here is a chatqna answer, so this only runs where a chatqna
# endpoint exists. On another pipeline type the write would still succeed and the
# call would return 405, failing for a reason that has nothing to do with scope
# routing.
if cfg.get("pipeline_type") not in ("chatqna", "audioqna"):
    pytestmark = pytest.mark.skip(
        reason=f"Needs a chatqna endpoint; pipeline_type is {cfg.get('pipeline_type')!r}")

logger = logging.getLogger(__name__)

# A tenant other than the one the chatqna router reads. Shaped like a Keycloak
# sub so the row is a valid per-user scope, just not the one chatqna serves.
_OTHER_TENANT = "550e8400-e29b-41d4-a716-446655440000"

# The canonical llm default the router falls back to, restored for any scope the
# test had to create (the store is insert/update-only, so a new row cannot be
# deleted).
_DEFAULT_MAX_NEW_TOKENS = 1024

# A small cap makes the effect observable: the answer is cut to a handful of
# words when the router honours the write. The uncapped side asserts only that
# the answer is not in that capped range, so it does not depend on an absolute
# answer length that can drift with the model or provider.
_CAPPED_MAX_NEW_TOKENS = 5
_CAPPED_WORD_CEILING = 15

# Config propagation to the router is not instantaneous, so lifting chatqna's cap
# is confirmed by polling the answer length rather than asserting on the first
# call, which could still reflect the previous capped value.
_UNCAP_POLL_TIMEOUT_SECONDS = 30
_UNCAP_POLL_INTERVAL_SECONDS = 2

_QUESTION = "List all the planets in the solar system with a brief description of each."


def _scoped_max_new_tokens(fingerprint_api_helper, pipeline, tenant):
    """Returns the stored max_new_tokens for a scope, or None if it has no row."""
    response = fingerprint_api_helper.read_config("llm", pipeline=pipeline, tenant=tenant)
    if response.status_code != 200:
        return None
    return response.json()["values"]["max_new_tokens"]


def _set_scoped_max_new_tokens(fingerprint_api_helper, pipeline, tenant, value):
    """Writes max_new_tokens for one scope and requires the write to succeed."""
    write = fingerprint_api_helper.set_component_parameters(
        "llm", max_new_tokens=value, pipeline=pipeline, tenant=tenant)
    assert write.status_code == 200, f"Write to {pipeline}/{tenant} failed"


def _restore_scoped_max_new_tokens(fingerprint_api_helper, pipeline, tenant, value):
    """Best-effort restore of a scope's max_new_tokens; logs instead of raising."""
    try:
        response = fingerprint_api_helper.set_component_parameters(
            "llm", max_new_tokens=value, pipeline=pipeline, tenant=tenant)
        if response.status_code != 200:
            logger.warning(
                f"Restore of {pipeline}/{tenant} to {value} returned {response.status_code}; "
                f"the scope may still hold the test value")
    except Exception as e:
        logger.warning(f"Failed to restore {pipeline}/{tenant} to {value}: {e}")


def _answer_word_count(chatqa_api_helper):
    """Asks the sample question and returns the chatqna answer's word count."""
    response = chatqa_api_helper.call_chatqa(_QUESTION)
    assert response.status_code == 200, "Unexpected status code from chatqna"
    return len(chatqa_api_helper.get_text(response).split())


def _wait_for_uncapped_answer(chatqa_api_helper):
    """Polls chatqna until the answer leaves the capped range, or times out."""
    deadline = time.monotonic() + _UNCAP_POLL_TIMEOUT_SECONDS
    words = _answer_word_count(chatqa_api_helper)
    while words <= _CAPPED_WORD_CEILING and time.monotonic() < deadline:
        time.sleep(_UNCAP_POLL_INTERVAL_SECONDS)
        words = _answer_word_count(chatqa_api_helper)
    return words


@allure.testcase("IEASG-T696")
def test_fingerprint_write_scope_reaches_only_matching_router(fingerprint_api_helper, chatqa_api_helper):
    """
    A write to chatqna's scope changes chatqna's answer; a write to a different
    scope leaves it unchanged, so the router serves the scope it is meant to and
    a misrouted write cannot silently take effect.
    """
    chatqna_before = _scoped_max_new_tokens(fingerprint_api_helper, CHATQNA_PIPELINE, GLOBAL_TENANT)
    other_before = _scoped_max_new_tokens(fingerprint_api_helper, CHATQNA_PIPELINE, _OTHER_TENANT)

    try:
        # A cap on chatqna's own scope must reach the router and shorten the answer.
        _set_scoped_max_new_tokens(
            fingerprint_api_helper, CHATQNA_PIPELINE, GLOBAL_TENANT, _CAPPED_MAX_NEW_TOKENS)
        capped_words = _answer_word_count(chatqa_api_helper)
        logger.info(f"chatqna-scoped cap produced a {capped_words}-word answer")
        assert capped_words <= _CAPPED_WORD_CEILING, (
            f"A cap written to {CHATQNA_PIPELINE}/{GLOBAL_TENANT} did not reach the router "
            f"(answer was {capped_words} words, expected <= {_CAPPED_WORD_CEILING})")

        # Lift chatqna's own scope back up and wait until the router is observed
        # serving the uncapped answer, so the isolation check below starts from a
        # known-uncapped baseline rather than a stale capped value.
        _set_scoped_max_new_tokens(
            fingerprint_api_helper, CHATQNA_PIPELINE, GLOBAL_TENANT, _DEFAULT_MAX_NEW_TOKENS)
        baseline_words = _wait_for_uncapped_answer(chatqa_api_helper)
        assert baseline_words > _CAPPED_WORD_CEILING, (
            f"chatqna did not return to an uncapped answer after restoring its scope "
            f"within {_UNCAP_POLL_TIMEOUT_SECONDS}s (answer was {baseline_words} words)")

        # Cap a different scope. The router reads chatqna/_global, so the
        # other-scope cap must not leak in and shorten the answer.
        _set_scoped_max_new_tokens(
            fingerprint_api_helper, CHATQNA_PIPELINE, _OTHER_TENANT, _CAPPED_MAX_NEW_TOKENS)
        uncapped_words = _answer_word_count(chatqa_api_helper)
        logger.info(f"other-scope cap left a {uncapped_words}-word answer")
        assert uncapped_words > _CAPPED_WORD_CEILING, (
            f"A cap written to a different scope leaked into {CHATQNA_PIPELINE}/{GLOBAL_TENANT} "
            f"(answer was cut to {uncapped_words} words, still within the capped range)")
    finally:
        restore_chatqna = chatqna_before if chatqna_before is not None else _DEFAULT_MAX_NEW_TOKENS
        restore_other = other_before if other_before is not None else _DEFAULT_MAX_NEW_TOKENS
        logger.info(f"Restoring chatqna/_global to {restore_chatqna} and the other scope to {restore_other}")
        _restore_scoped_max_new_tokens(
            fingerprint_api_helper, CHATQNA_PIPELINE, GLOBAL_TENANT, restore_chatqna)
        _restore_scoped_max_new_tokens(
            fingerprint_api_helper, CHATQNA_PIPELINE, _OTHER_TENANT, restore_other)
