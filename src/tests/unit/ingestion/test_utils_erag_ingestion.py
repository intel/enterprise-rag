# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comps.cores.proto.docarray import EmbedDoc, EmbedDocList
from comps.ingestion.utils.erag_ingestion import EragIngestion


@pytest.fixture
def mock_vector_store():
    with patch("comps.ingestion.utils.erag_ingestion.EragVectorStore") as mock_cls:
        mock_cls.return_value.add_texts = AsyncMock(return_value=["id1", "id2"])
        mock_cls.return_value.delete_texts = AsyncMock(return_value=3)
        yield mock_cls


@pytest.fixture
def mock_redis_connector():
    with patch("comps.vectorstores.utils.connectors.connector_redis.ConnectorRedis") as mock_cls:
        mock_cls.return_value.add_texts = AsyncMock(return_value=["id1", "id2"])
        mock_cls.return_value.search_and_delete_by_metadata = AsyncMock(return_value=2)
        yield mock_cls.return_value


def test_singleton_initializes_vector_store_once(mock_vector_store):
    first = EragIngestion("redis")
    second = EragIngestion("pgvector")

    assert first is second
    mock_vector_store.assert_called_once_with("redis")
    assert first.vector_store is mock_vector_store.return_value


def test_unsupported_vector_store_raises():
    with pytest.raises(ValueError, match="Unsupported vector store: unknown"):
        EragIngestion("unknown")


@pytest.mark.asyncio
async def test_ingest_passes_all_docs_and_returns_input(mock_vector_store):
    docs = [EmbedDoc(text="doc1", embedding=[0.1, 0.2]), EmbedDoc(text="doc2", embedding=[0.3, 0.4])]
    input_docs = EmbedDocList(docs=docs)

    result = await EragIngestion("redis").ingest(input_docs)

    assert result is input_docs
    passed = mock_vector_store.return_value.add_texts.await_args.kwargs["input"]
    assert [d.text for d in passed] == ["doc1", "doc2"]


@pytest.mark.asyncio
async def test_ingest_wraps_single_doc_in_list(mock_vector_store):
    doc = EmbedDoc(text="doc1", embedding=[0.1, 0.2])
    input_docs = MagicMock(docs=doc)

    result = await EragIngestion("redis").ingest(input_docs)

    assert result is input_docs
    mock_vector_store.return_value.add_texts.assert_awaited_once_with(input=[doc])


@pytest.mark.asyncio
async def test_ingest_propagates_vector_store_error(mock_vector_store):
    mock_vector_store.return_value.add_texts.side_effect = RuntimeError("redis down")
    input_docs = EmbedDocList(docs=[EmbedDoc(text="doc1", embedding=[0.1])])

    with pytest.raises(RuntimeError, match="redis down"):
        await EragIngestion("redis").ingest(input_docs)


@pytest.mark.asyncio
@pytest.mark.parametrize("field_value, expected", [
    ("1b4e28ba-2fa1-11d2-883f-0016d3cca427", "1b4e28ba2fa111d2883f0016d3cca427"),
    ("1b4e28ba2fa111d2883f0016d3cca427", "1b4e28ba2fa111d2883f0016d3cca427"),
])
async def test_delete_strips_hyphens_from_id(mock_vector_store, field_value, expected):
    result = await EragIngestion("redis").delete(field_name="file_id", field_value=field_value)

    assert result == 3
    mock_vector_store.return_value.delete_texts.assert_awaited_once_with(
        search_field_name="file_id", search_field_value=expected
    )


@pytest.mark.asyncio
async def test_delete_propagates_vector_store_error(mock_vector_store):
    mock_vector_store.return_value.delete_texts.side_effect = RuntimeError("redis down")

    with pytest.raises(RuntimeError, match="redis down"):
        await EragIngestion("redis").delete(field_name="link_id", field_value="abc")


@pytest.mark.asyncio
async def test_ingest_reaches_connector_with_texts_embeddings_metadata(mock_redis_connector):
    docs = [
        EmbedDoc(text="doc1", embedding=[0.1, 0.2], metadata={"file_id": "f1"}),
        EmbedDoc(text="doc2", embedding=[0.3, 0.4], metadata={"file_id": "f1"}),
    ]

    await EragIngestion("redis").ingest(EmbedDocList(docs=docs))

    mock_redis_connector.add_texts.assert_awaited_once_with(
        ["doc1", "doc2"], [[0.1, 0.2], [0.3, 0.4]], [{"file_id": "f1"}, {"file_id": "f1"}]
    )


@pytest.mark.asyncio
async def test_delete_reaches_connector(mock_redis_connector):
    result = await EragIngestion("redis").delete(field_name="link_id", field_value="a-b-c")

    assert result == 2
    mock_redis_connector.search_and_delete_by_metadata.assert_awaited_once_with(
        field_name="link_id", field_value="abc"
    )
