#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import concurrent
import logging
import time
import requests

from tests.e2e.helpers.api_request_helper import ApiRequestHelper, ApiResponse
from tests.e2e.validation.buildcfg import cfg

logger = logging.getLogger(__name__)


class ChatQaApiHelper(ApiRequestHelper):

    def __init__(self, keycloak_helper):
        super().__init__(keycloak_helper=keycloak_helper)
        self.chatqa_api_path = f"https://{cfg.get('base_domain_name')}/api/v1/chatqna"

    def call_chatqa(self, question, as_user=False, **custom_params):
        """
        Make /v1/chatqna API call with the provided question. Streaming disabled.
        """
        json_data = {
            "text": question
        }
        json_data.update(custom_params)
        return self._call_chatqa(json_data, as_user=as_user)

    def call_chatqa_with_streaming_enabled(self, question, **custom_params):
        """
        Make /v1/chatqna API call with the provided question and enable streaming response.
        """
        json_data = {
            "text": question
        }
        json_data.update(custom_params)
        return self._call_chatqa(json_data, stream=True)

    def call_chatqa_in_parallel(self, questions, num_tokens=5):
        """Ask questions in parallel across a small pool of pre-fetched auth tokens.

        Two constraints shape this:
        - The chatqna APISIX route rate-limits to 30 requests / 60 s per token (keyed by the
          Authorization header), so a single shared token would get most of a large burst 429'd.
        - Fetching one token per request would log in to Keycloak from every worker at once,
          stampeding the token endpoint (hard-coded 10 s timeout, no retry).

        So we pre-fetch a small pool of distinct tokens - one Keycloak login each, done calmly
        before the workers start - and round-robin the requests across them. With the default
        pool of 5 and 100 questions each token carries 20 requests, comfortably under the 30/60s
        limit, while all 100 still hit the pipeline concurrently.
        """

        request_bodies = []
        for question in questions:
            json_data = {"text": question, "parameters": {"streaming": False}}
            request_bodies.append(json_data)

        # Each get_headers() triggers a fresh login, so every pool entry carries a different
        # Authorization value and thus counts as a separate APISIX rate-limit key.
        pool_size = max(1, min(num_tokens, len(request_bodies)))
        token_pool = [self.get_headers().copy() for _ in range(pool_size)]

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(questions)) as executor:
            futures_to_questions = {}
            for i, payload in enumerate(request_bodies):
                future = executor.submit(self._call_chatqa, payload, headers=token_pool[i % pool_size])
                futures_to_questions[future] = payload

            for future in concurrent.futures.as_completed(futures_to_questions):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append(ApiResponse(None, None,
                                               exception=f"Request failed with exception: {e}"))
        return results

    def _call_chatqa(self, payload, stream=False, as_user=False, headers=None):
        """
        Make /api/v1/chatqna API call through APISIX using provided token.

        headers: pre-fetched auth headers to reuse across calls. When None, each call fetches
        its own headers (and token) via get_headers(). call_chatqa_in_parallel passes a
        single set of headers so concurrent workers share one token instead of each logging
        in on its own.
        """
        logger.info(f"Asking the following question: {payload['text']}")
        request_headers = headers if headers is not None else self.get_headers(as_user)
        start_time = time.time()
        response = requests.post(
            url=self.chatqa_api_path,
            headers=request_headers,
            json=payload,
            stream=stream,
            verify=False
        )
        api_call_duration = round(time.time() - start_time, 2)
        logger.info(f"ChatQA API call duration: {api_call_duration}")
        return ApiResponse(response, api_call_duration)

    def get_reranked_docs(self, response):
        """Extract the reranked_docs from the response"""
        _, reranked_docs = self.format_response(response)
        return reranked_docs

    def words_in_response(self, substrings, response):
        """Returns true if any of the substrings appear in the response strings"""
        response = response.lower()
        return any(substring.lower() in response for substring in substrings)

    def all_words_in_response(self, substrings, response):
        """Returns true if all of the substrings appear in the response strings"""
        response = response.lower()
        return all(substring.lower() in response for substring in substrings)

