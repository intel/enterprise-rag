# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import sys

import pytest

from comps.ingestion.utils.erag_ingestion import EragIngestion
from comps.vectorstores.utils.erag_vectorstore import EragVectorStore

# The microservice does `from utils import erag_ingestion`, which only resolves
# when comps/ingestion is on sys.path (as it is when run from that directory).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "comps", "ingestion"))


@pytest.fixture(autouse=True)
def reset_singletons():
    EragIngestion._instance = None
    EragVectorStore._instance = None
    yield
    EragIngestion._instance = None
    EragVectorStore._instance = None
