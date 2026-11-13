# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
import pytest
import torch
from unittest.mock import MagicMock, patch

from comps.guardrails.utils.llm_guard import transformers_helpers
from comps.guardrails.utils.llm_guard.model import Model

HELPERS = "comps.guardrails.utils.llm_guard.transformers_helpers"


@pytest.fixture
def transformers_stub():
    transformers = MagicMock()
    with (
        patch(f"{HELPERS}.lazy_load_dep", return_value=transformers),
        patch(f"{HELPERS}.model_dtype", return_value=torch.bfloat16),
    ):
        yield transformers


@pytest.mark.parametrize(
    "loader, auto_class",
    [
        (
            transformers_helpers.get_tokenizer_and_model_for_classification,
            "AutoModelForSequenceClassification",
        ),
        (
            transformers_helpers.get_tokenizer_and_model_for_ner,
            "AutoModelForTokenClassification",
        ),
    ],
)
def test_loaders_pass_model_dtype(transformers_stub, loader, auto_class):
    model = Model(path="org/model", revision="abc123")

    tokenizer, tf_model = loader(model)

    from_pretrained = getattr(transformers_stub, auto_class).from_pretrained
    from_pretrained.assert_called_once_with(
        "org/model", subfolder="", revision="abc123", dtype=torch.bfloat16
    )
    assert tf_model is from_pretrained.return_value
    assert tokenizer is transformers_stub.AutoTokenizer.from_pretrained.return_value
