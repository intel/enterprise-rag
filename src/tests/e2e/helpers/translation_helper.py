#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import time

import requests

from tests.e2e.helpers.api_request_helper import ApiRequestHelper, ApiResponse, CustomPortForward

logger = logging.getLogger(__name__)


class TranslationHelper(ApiRequestHelper):
    """Calls the translation router directly, as translation has no external route."""

    NAMESPACE = "translation"
    ROUTER_SELECTOR = "app=router-service"
    ROUTER_PORT = 8080

    def call(self, text, target_language):
        return self.call_with_payload({"text": text, "target_language": target_language})

    def call_with_payload(self, payload):
        with CustomPortForward(self.ROUTER_PORT, self.NAMESPACE, self.ROUTER_SELECTOR) as pf:
            start_time = time.time()
            response = requests.post(
                url=f"http://127.0.0.1:{pf.local_port}/",
                headers=self.default_headers,
                json=payload,
                timeout=300
            )
            duration = round(time.time() - start_time, 2)
        logger.info(f"Translation call duration: {duration}")
        return ApiResponse(response, duration)
