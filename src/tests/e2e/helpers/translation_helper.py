#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import time

import requests

from tests.e2e.helpers.api_request_helper import ApiRequestHelper, ApiResponse
from tests.e2e.validation.buildcfg import cfg

logger = logging.getLogger(__name__)


class TranslationHelper(ApiRequestHelper):

    def __init__(self, keycloak_helper):
        super().__init__(keycloak_helper=keycloak_helper)
        self.translation_api_path = f"https://{cfg.get('base_domain_name')}/api/v1/translation"

    def call(self, text, target_language, **parameters):
        payload = {"text": text, "target_language": target_language}
        if parameters:
            payload["parameters"] = parameters
        return self.call_with_payload(payload)

    def call_with_payload(self, payload, headers=None):
        """POST the payload as JSON; a str is sent verbatim, so a test can send malformed JSON."""
        body = payload if isinstance(payload, str) else json.dumps(payload)
        start_time = time.time()
        response = requests.post(
            url=self.translation_api_path,
            headers=self.get_headers() if headers is None else headers,
            data=body,
            timeout=300,
            verify=False
        )
        duration = round(time.time() - start_time, 2)
        logger.info(f"Translation call duration: {duration}")
        return ApiResponse(response, duration)
