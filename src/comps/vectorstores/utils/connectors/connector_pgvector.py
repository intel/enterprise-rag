# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Iterable, List, Optional, Union # noqa: F401

from comps.cores.mega.logger import change_erag_logger_level, get_erag_logger
from comps.cores.proto.docarray import SearchedDoc, TextDoc # noqa: F401
from comps.cores.utils.utils import get_boolean_env_var, sanitize_env # noqa: F401
from comps.vectorstores.utils.connectors.connector import VectorStoreConnector


logger = get_erag_logger(f"{__file__.split('comps/')[1].split('/', 1)[0]}")
change_erag_logger_level(logger, log_level=os.getenv("ERAG_LOGGER_LEVEL", "INFO"))

class ConnectorPgVector(VectorStoreConnector):
    def __init__(self, batch_size: int = 32):
        self.batch_size = batch_size
        self.index_dict = {}
        self.client = None
