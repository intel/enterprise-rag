# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
import numpy as np
import torch
from unittest.mock import MagicMock, patch

from comps.guardrails.utils.llm_guard.output_scanners.relevance import Relevance

RELEVANCE = "comps.guardrails.utils.llm_guard.output_scanners.relevance"


def test_relevance_loads_in_model_dtype_and_encodes_bf16_to_float32():
    transformers = MagicMock()
    loaded_model = transformers.AutoModel.from_pretrained.return_value.to.return_value
    loaded_model.return_value.last_hidden_state = torch.rand(
        1, 4, 8, dtype=torch.bfloat16
    )
    tokenizer = MagicMock(
        return_value={
            "input_ids": torch.ones(1, 4, dtype=torch.long),
            "attention_mask": torch.ones(1, 4, dtype=torch.long),
        }
    )

    with (
        patch(f"{RELEVANCE}.lazy_load_dep", return_value=transformers),
        patch(f"{RELEVANCE}.model_dtype", return_value=torch.bfloat16),
        patch(f"{RELEVANCE}.get_tokenizer", return_value=tokenizer),
    ):
        scanner = Relevance()
        embedding = scanner._encode("What is the capital of France?")

    assert (
        transformers.AutoModel.from_pretrained.call_args.kwargs["dtype"]
        == torch.bfloat16
    )
    assert isinstance(embedding, np.ndarray)
    assert embedding.dtype == np.float32
