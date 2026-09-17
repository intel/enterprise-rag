# ruff: noqa: E712
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# test_erag_embedding.py

from unittest import mock

import pytest

from comps.embeddings.utils.erag_embedding import EragEmbedding
from comps.embeddings.utils.connectors.ovms_connector import OVMSConnector
from comps.embeddings.utils.connectors.vllm_connector import VLLMConnector


@pytest.fixture
def teardown():
    yield
    EragEmbedding._instance = None
    VLLMConnector._instance = None
    OVMSConnector._instance = None


def test_singleton_behavior(teardown):
    with mock.patch.object(VLLMConnector, '__new__', return_value=mock.MagicMock()):
        instance1 = EragEmbedding("model1", "vllm", "http://test-endpoint")
        instance2 = EragEmbedding("model1", "vllm", "http://test-endpoint")

        assert instance1 is instance2


def test_singleton_reuse_on_different_params(teardown):
    with mock.patch.object(VLLMConnector, '__new__', return_value=mock.MagicMock()):
        instance1 = EragEmbedding("model1", "vllm", "http://test-endpoint")
        # Second call with different params reuses existing instance with a warning
        instance2 = EragEmbedding("model2", "ovms", "http://test-endpoint")

        assert instance1 is instance2


def test_initialization(teardown):
    with mock.patch.object(VLLMConnector, '__new__', return_value=mock.MagicMock()):
        model_name = "test_model"
        model_server = "vllm"
        endpoint = "http://test-endpoint"
        embedding = EragEmbedding(model_name, model_server, endpoint)

        assert embedding._model_name == model_name
        assert embedding._model_server == model_server
        assert embedding._endpoint == endpoint
        assert embedding._connector is not None


def test_unsupported_model_server(teardown):
    with pytest.raises(ValueError) as exc_info:
        EragEmbedding("test_model", "unsupported_server", "http://test-endpoint")
    assert "Invalid model server" in exc_info.value.args[0]


@pytest.mark.asyncio
async def test_return_pooling_is_rejected_by_the_connector(teardown):
    """The surviving model servers cannot return per-token embeddings, so pooling must raise."""
    from comps.cores.proto.docarray import TextDoc, TextDocList

    with mock.patch.object(VLLMConnector, '__new__', return_value=mock.MagicMock()):
        embedding = EragEmbedding("test_model", "vllm", "http://test-endpoint")

    embedding._connector.embed_documents = mock.AsyncMock(
        side_effect=ValueError("return_pooling is not supported by the vllm model server.")
    )

    docs = [TextDoc(text=f"test document {i}") for i in range(5)]
    input_with_pooling = TextDocList(docs=docs, return_pooling=True)

    with pytest.raises(ValueError) as exc_info:
        await embedding.run(input_with_pooling)

    assert "return_pooling is not supported" in str(exc_info.value)


@pytest.mark.asyncio
async def test_return_pooling_false_uses_regular_batch_size(teardown):
    """Test that return_pooling=False uses REQUEST_BATCH_SIZE."""
    from comps.cores.proto.docarray import TextDoc, TextDocList

    with mock.patch.object(VLLMConnector, '__new__', return_value=mock.MagicMock()):
        embedding = EragEmbedding("test_model", "vllm", "http://test-endpoint")

    def mock_embed_side_effect(texts, **kwargs):
        return [[0.1, 0.2, 0.3] for _ in texts]

    mock_embed_docs = mock.AsyncMock(side_effect=mock_embed_side_effect)
    embedding._connector.embed_documents = mock_embed_docs

    docs = [TextDoc(text=f"test document {i}") for i in range(5)]
    input_without_pooling = TextDocList(docs=docs, return_pooling=False)

    result = await embedding.run(input_without_pooling)

    assert mock_embed_docs.call_count > 0
    for call in mock_embed_docs.call_args_list:
        kwargs = call.kwargs
        assert 'return_pooling' in kwargs
        assert kwargs['return_pooling'] == False
        texts = call.args[0] if call.args else kwargs.get('texts', [])
        assert len(texts) <= embedding.REQUEST_BATCH_SIZE

    assert len(result.docs) == 5
    for doc in result.docs:
        assert doc.embedding is not None
