# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
import pytest
from unittest.mock import MagicMock, patch

from comps.guardrails.utils.llm_guard.output_scanners.malicious_urls import (
    MaliciousURLs,
)

MALICIOUS_URLS = "comps.guardrails.utils.llm_guard.output_scanners.malicious_urls"


def _classify(urls):
    return [
        [
            {"label": "MALWARE", "score": 0.99 if "malware" in url else 0.01},
            {"label": "BENIGN", "score": 0.01 if "malware" in url else 0.99},
        ]
        for url in urls
    ]


@pytest.fixture
def scanner():
    with (
        patch(
            f"{MALICIOUS_URLS}.get_tokenizer_and_model_for_classification",
            return_value=(MagicMock(), MagicMock()),
        ),
        patch(
            f"{MALICIOUS_URLS}.pipeline", return_value=MagicMock(side_effect=_classify)
        ),
    ):
        yield MaliciousURLs()


def test_malicious_url_is_blocked(scanner):
    _, is_valid, risk_score = scanner.scan(
        "prompt", "Visit http://malware-login.example/steal now"
    )
    assert is_valid is False
    assert risk_score > 0


def test_benign_url_is_allowed(scanner):
    _, is_valid, risk_score = scanner.scan(
        "prompt", "See https://www.intel.com for details"
    )
    assert is_valid is True
    assert risk_score < 0


def test_output_without_urls_is_allowed(scanner):
    assert scanner.scan("prompt", "No links here.") == ("No links here.", True, -1.0)
