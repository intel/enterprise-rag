# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
import pytest
import torch
from unittest.mock import mock_open, patch

from comps.guardrails.utils.llm_guard import util


@pytest.fixture(autouse=True)
def clear_model_dtype_cache():
    util.model_dtype.cache_clear()
    yield
    util.model_dtype.cache_clear()


@pytest.mark.parametrize(
    "flags, expected_dtype",
    [
        ("fpu avx512f avx512_bf16 amx_bf16 amx_tile amx_int8", torch.bfloat16),
        ("fpu avx512f avx512_bf16", torch.float32),
        ("fpu avx2 amx_bf16_extra", torch.float32),
    ],
)
def test_model_dtype_follows_amx_bf16_flag(flags, expected_dtype):
    cpuinfo = f"processor\t: 0\nflags\t\t: {flags}\n"
    with patch("builtins.open", mock_open(read_data=cpuinfo)):
        assert util.model_dtype() == expected_dtype


def test_model_dtype_falls_back_to_float32_without_cpuinfo():
    with patch("builtins.open", side_effect=FileNotFoundError):
        assert util.model_dtype() == torch.float32


def test_model_dtype_is_detected_once_per_process():
    with patch(
        "builtins.open", mock_open(read_data="flags\t\t: amx_bf16\n")
    ) as cpuinfo_open:
        util.model_dtype()
        util.model_dtype()
    cpuinfo_open.assert_called_once()
