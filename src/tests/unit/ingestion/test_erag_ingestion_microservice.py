# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from comps.cores.mega.micro_service import erag_microservices
from comps.cores.proto.docarray import EmbedDoc, EmbedDocList
from comps.ingestion import erag_ingestion_microservice as svc


@pytest.fixture
def mock_ingestion():
    mock = MagicMock()
    mock.ingest = AsyncMock()
    mock.delete = AsyncMock(return_value=5)
    with patch.object(svc, "ingestion", mock):
        yield mock


@pytest.fixture
def mock_latency():
    with patch.object(svc.statistics_dict[svc.USVC_NAME], "append_latency") as mock:
        yield mock


def test_endpoints_registered():
    paths = {route.path for route in erag_microservices[svc.USVC_NAME].app.routes}

    assert {"/v1/ingestion", "/v1/ingestion/delete"} <= paths


@pytest.mark.asyncio
async def test_ingest_returns_ingested_docs(mock_ingestion, mock_latency):
    input_docs = EmbedDocList(docs=[EmbedDoc(text="doc1", embedding=[0.1, 0.2])])
    mock_ingestion.ingest.return_value = input_docs

    result = await svc.ingest(input_docs)

    assert result is input_docs
    mock_ingestion.ingest.assert_awaited_once_with(input_docs)
    mock_latency.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_error_returns_500(mock_ingestion, mock_latency):
    mock_ingestion.ingest.side_effect = RuntimeError("redis down")
    input_docs = EmbedDocList(docs=[EmbedDoc(text="doc1", embedding=[0.1, 0.2])])

    with pytest.raises(HTTPException) as exc:
        await svc.ingest(input_docs)

    assert exc.value.status_code == 500
    assert "redis down" in exc.value.detail
    mock_latency.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload, field_name, field_value", [
    ({"file_id": "f-1"}, "file_id", "f-1"),
    ({"link_id": "l-1"}, "link_id", "l-1"),
    ({"file_id": "f-1", "link_id": "l-1"}, "file_id", "f-1"),
])
async def test_delete_by_field(mock_ingestion, mock_latency, payload, field_name, field_value):
    result = await svc.delete(payload)

    assert result == {"deleted_embeddings": 5}
    mock_ingestion.delete.assert_awaited_once_with(field_name=field_name, field_value=field_value)
    mock_latency.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"bucket_name": "b"}])
async def test_delete_without_id_returns_400(mock_ingestion, payload):
    with pytest.raises(HTTPException) as exc:
        await svc.delete(payload)

    assert exc.value.status_code == 400
    assert "link_id or file_id" in exc.value.detail
    mock_ingestion.delete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"file_id": ""}, {"file_id": None}, {"link_id": ""}])
async def test_delete_with_empty_id_returns_400(mock_ingestion, payload):
    with pytest.raises(HTTPException) as exc:
        await svc.delete(payload)

    assert exc.value.status_code == 400
    assert "cannot be empty" in exc.value.detail
    mock_ingestion.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_error_returns_500(mock_ingestion, mock_latency):
    mock_ingestion.delete.side_effect = RuntimeError("redis down")

    with pytest.raises(HTTPException) as exc:
        await svc.delete({"file_id": "f-1"})

    assert exc.value.status_code == 500
    assert "redis down" in exc.value.detail
    mock_latency.assert_not_called()
