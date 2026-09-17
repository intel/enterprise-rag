# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True, scope="module")
def mock_microservice_class():
    """Mock MicroService to prevent event loop creation during module import."""
    mock_microservice = MagicMock()
    mock_microservice.app = MagicMock()
    mock_microservice.start = MagicMock()

    with patch('comps.cores.mega.micro_service.MicroService', return_value=mock_microservice):
        yield mock_microservice


@pytest.fixture(autouse=True, scope="module")
def mock_register_microservice():
    with patch('comps.cores.mega.micro_service.register_microservice') as mock_register, \
         patch('comps.cores.mega.micro_service.erag_microservices', {}):
        mock_register.return_value = lambda func: func  # decorator passthrough
        yield mock_register
