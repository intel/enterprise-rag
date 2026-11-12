# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import re

import pytest

_KANA = re.compile(r"[぀-ヿ]")
_HAN = re.compile(r"[一-鿿]")


def fake_detect(text, low_memory=True):
    """Deterministic stand-in for ftlangdetect.detect.

    The real function downloads the fastText model (lid.176.ftz) from
    dl.fbaipublicfiles.com on first use, which makes the unit tests depend on
    that host being reachable and serving a valid certificate. The tests only
    need to tell apart the scripts used in their inputs: Japanese (kana),
    Chinese (Han without kana) and English (everything else).
    """
    if _KANA.search(text):
        lang = "ja"
    elif _HAN.search(text):
        lang = "zh"
    else:
        lang = "en"
    return {"lang": lang, "score": 1.0}


@pytest.fixture(autouse=True)
def offline_language_detection(monkeypatch):
    """Keep the language detection unit tests from downloading the fastText model."""
    monkeypatch.setattr("comps.language_detection.utils.detector.detect", fake_detect)
