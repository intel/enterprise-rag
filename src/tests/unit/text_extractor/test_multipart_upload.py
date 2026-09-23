# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the multipart upload endpoint on text_extractor microservice.

The @register_microservice decorator calls run_until_complete() at import time,
which conflicts with pytest-asyncio's event loop. We therefore import the module
at the top level (outside async context) and use patch.object on it.
"""

import io
import os
import sys
import pytest
from unittest.mock import patch, AsyncMock

from comps.cores.proto.docarray import TextDoc, TextExtractorInput, TextSplitterInput

# The microservice uses `from utils.erag_text_extractor import ...` which requires
# comps/text_extractor/ on sys.path.
_te_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "comps", "text_extractor")
_te_dir = os.path.normpath(_te_dir)
if _te_dir not in sys.path:
    sys.path.insert(0, _te_dir)

# Import at module level (synchronous context) so @register_microservice succeeds.
import comps.text_extractor.erag_text_extractor_microservice as te_mod  # noqa: E402


@pytest.fixture
def sample_pdf_bytes():
    """Minimal valid-ish PDF bytes for testing (not a real PDF, but enough for decoding tests)."""
    return b"%PDF-1.4 fake content for testing purposes " + b"\x00" * 100


@pytest.fixture
def sample_txt_bytes():
    return b"This is a plain text document for testing."


class TestMultipartEndpoint:
    """Verify the multipart endpoint reads file bytes and delegates to shared processing logic."""

    @pytest.mark.asyncio
    async def test_multipart_endpoint_reads_and_calls_shared_logic(self, sample_txt_bytes):
        """The multipart endpoint should read file bytes and call _process_files."""
        from fastapi import UploadFile

        with patch.object(te_mod, "_process_files", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = TextSplitterInput(loaded_docs=[TextDoc(text="extracted")])

            upload = UploadFile(filename="test.txt", file=io.BytesIO(sample_txt_bytes))
            await te_mod.process_multipart(files=[upload], links=[], texts=[])

            mock_process.assert_called_once()
            call_args = mock_process.call_args
            decoded_files = call_args[0][0]
            assert len(decoded_files) == 1
            assert decoded_files[0][0] == "test.txt"
            assert decoded_files[0][1] == sample_txt_bytes

    @pytest.mark.asyncio
    async def test_multipart_rejects_empty_file(self):
        """Multipart endpoint should reject files with no content."""
        from fastapi import UploadFile, HTTPException

        with patch.object(te_mod, "_process_files", new_callable=AsyncMock):
            upload = UploadFile(filename="empty.txt", file=io.BytesIO(b""))

            with pytest.raises(HTTPException) as exc_info:
                await te_mod.process_multipart(files=[upload], links=[], texts=[])
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_multipart_rejects_invalid_filename(self, sample_txt_bytes):
        """Multipart endpoint should reject files with invalid filenames."""
        from fastapi import UploadFile, HTTPException

        with patch.object(te_mod, "_process_files", new_callable=AsyncMock):
            upload = UploadFile(filename="../../../etc/passwd", file=io.BytesIO(sample_txt_bytes))

            with pytest.raises(HTTPException) as exc_info:
                await te_mod.process_multipart(files=[upload], links=[], texts=[])
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_multipart_rejects_empty_request(self):
        """Multipart endpoint should reject a request with no files, links or texts."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await te_mod.process_multipart(files=[], links=[], texts=[])
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_multipart_combines_files_and_texts(self, sample_txt_bytes):
        """A DocSum upload may carry texts alongside the files; both are extracted."""
        from fastapi import UploadFile

        with patch.object(te_mod, "_process_files", new_callable=AsyncMock) as mock_files, \
                patch.object(te_mod, "_process_links_and_texts", new_callable=AsyncMock) as mock_links:
            mock_files.return_value = TextSplitterInput(loaded_docs=[TextDoc(text="from file")])
            mock_links.return_value = TextSplitterInput(loaded_docs=[TextDoc(text="from text")])

            upload = UploadFile(filename="test.txt", file=io.BytesIO(sample_txt_bytes))
            result = await te_mod.process_multipart(files=[upload], links=[], texts=["pasted"])

            mock_links.assert_called_once_with(link_list=[], texts=["pasted"])
            assert [doc.text for doc in result.loaded_docs] == ["from file", "from text"]


class TestProcessLinksEndpoint:
    """Verify the JSON process() endpoint delegates link/text requests correctly."""

    @pytest.mark.asyncio
    async def test_process_delegates_links(self):
        """process() should pass links to _process_links_and_texts."""
        with patch.object(te_mod, "_process_links_and_texts", new_callable=AsyncMock) as mock:
            mock.return_value = TextSplitterInput(loaded_docs=[TextDoc(text="x")])
            await te_mod.process(TextExtractorInput(links=["http://example.com"]))
            mock.assert_called_once_with(link_list=["http://example.com"], texts=[])

    @pytest.mark.asyncio
    async def test_process_rejects_empty_input(self):
        """process() should reject requests with no links and no texts."""
        from fastapi import HTTPException

        with patch.object(te_mod, "_process_links_and_texts", new_callable=AsyncMock):
            with pytest.raises(HTTPException) as exc_info:
                await te_mod.process(TextExtractorInput(links=[], texts=[]))
            assert exc_info.value.status_code == 400
