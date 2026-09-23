#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import concurrent.futures
import json
import logging
import os
import requests
import time

from rouge import Rouge
from sentence_transformers import SentenceTransformer, util

from tests.e2e.validation.buildcfg import cfg
from tests.e2e.validation.constants import TEST_FILES_DIR
from tests.e2e.helpers.api_request_helper import ApiRequestHelper, ApiResponse

logger = logging.getLogger(__name__)


class SummaryEvaluator:
    """A class for evaluating summary quality using sentence transformers similarity and ROUGE scores"""
    def __init__(self):
        self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        self.rouge = Rouge()

    def evaluate(self, original_text, summary):
        """
        Evaluate summary quality using sentence transformers similarity and ROUGE scores.
        Returns a tuple of (similarity_score, max_rouge_score).
        max_rouge_score is the highest score among all ROUGE metrics - this is done due to
        the case when the summary is very short in comparison to the original text.
        """

        # Sentence transformers similarity
        embedding_text = self.model.encode(original_text, convert_to_tensor=True)
        embedding_summary = self.model.encode(summary, convert_to_tensor=True)
        similarity = util.cos_sim(embedding_text, embedding_summary).item()
        logger.debug(f"Sentence transformers score:\t{round(similarity, 2)}")

        # ROUGE scores
        scores = self.rouge.get_scores(summary, original_text)
        max_rouge_score = 0
        for idx, score_dict in enumerate(scores):
            for rouge_key, metrics in score_dict.items():
                for metric_name, value in metrics.items():
                    if value > max_rouge_score:
                        max_rouge_score = value
        logger.debug(f"Highest rouge score: \t{round(max_rouge_score, 2)}")
        logger.debug(f"Similarity scores (rouge):{scores}")
        return similarity, max_rouge_score


class DocSumHelper(ApiRequestHelper):

    def __init__(self, keycloak_helper):
        super().__init__(keycloak_helper=keycloak_helper)
        self.summary_evaluator = SummaryEvaluator()
        self.docsum_api_path = f"https://{cfg.get('base_domain_name')}/api/v1/docsum"

    def call(self, texts=[], links=[], files=[], summary_type="map_reduce", as_user=False, stream=True):
        """Make DocSum API call with the provided texts, links, and files.

        Files are uploaded as multipart/form-data; text- and link-only requests are JSON.
        """
        parameters = {
            "stream": stream,
            "summary_type": summary_type,
            "chunk_size": 2048
        }
        if files:
            return self.call_with_multipart(files=files, texts=texts, links=links,
                                            parameters=parameters, as_user=as_user, stream=stream)
        payload = {
            "links": links,
            "texts": texts,
            "parameters": parameters
        }
        return self.call_with_payload(payload, as_user=as_user, stream=stream)

    def call_in_parallel(self, texts=[], stream=True):
        """Make DocSum API calls in parallel for the provided texts.

        The auth token is fetched once here, before the workers start, and shared by every
        request so the threads do not each trigger their own Keycloak login simultaneously.
        """
        shared_headers = self.get_headers().copy()
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(texts)) as executor:
            futures_to_questions = {}
            for text in texts:
                payload = {
                    "links": [],
                    "texts": [text],
                    "parameters": {
                        "stream": stream,
                        "chunk_size": 2048
                    }
                }
                future = executor.submit(self.call_with_payload, payload, headers=shared_headers)
                futures_to_questions[future] = payload

            for future in concurrent.futures.as_completed(futures_to_questions):
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append(ApiResponse(None, None,
                                               exception=f"Request failed with exception: {e}"))
        return results

    def call_with_payload(self, payload, as_user=False, stream=True, headers=None):
        """Make DocSum API call with the provided payload.

        headers: pre-fetched auth headers to reuse; when None, each call fetches its own via
        get_headers(). call_in_parallel passes a single set so concurrent workers share one token.
        """
        logger.info("Making DocSum API call")
        request_headers = headers if headers is not None else self.get_headers(as_user)
        start_time = time.time()
        response = requests.post(
            url=self.docsum_api_path,
            headers=request_headers,
            json=payload,
            stream=stream,
            verify=False
        )
        api_call_duration = round(time.time() - start_time, 2)
        logger.info(f"DocSum API call duration: {api_call_duration}")
        return ApiResponse(response, api_call_duration)

    def call_with_multipart(self, files, texts=[], links=[], parameters=None, as_user=False, stream=True,
                            headers=None):
        """Make DocSum API call uploading files as multipart/form-data.

        The pipeline parameters travel in a `parameters` form field, since a multipart
        request carries no JSON body for the router to read them from.
        """
        logger.info("Making DocSum API call with a file upload")
        request_headers = dict(headers if headers is not None else self.get_headers(as_user))
        # requests generates Content-Type with the multipart boundary
        request_headers.pop("Content-Type", None)
        form_files = [("files", attachment) for attachment in files]
        form_data = [("texts", text) for text in texts] + [("links", link) for link in links]
        if parameters:
            form_data.append(("parameters", json.dumps(parameters)))
        start_time = time.time()
        response = requests.post(
            url=self.docsum_api_path,
            headers=request_headers,
            files=form_files,
            data=form_data,
            stream=stream,
            verify=False
        )
        api_call_duration = round(time.time() - start_time, 2)
        logger.info(f"DocSum API call duration: {api_call_duration}")
        return ApiResponse(response, api_call_duration)

    def get_summary(self, response):
        """Extract summary from DocSum API response"""
        text = self.get_text(response)
        text = text.replace("Here is a concise summary:", "")
        summary = text.replace("[DONE]", "")
        logger.info(f"Got summary: '{summary}'")
        return summary

    def evaluate_summary(self, response, text, text_title=None, summary_type="map_reduce"):
        """Evaluate the summary in the DocSum API response"""
        summary = self.get_summary(response)
        failures = []
        if "[ERROR]" in summary:
            failures.append(f"DocSum API returned an error in the summary: {summary}")
            return failures
        similarity, max_rouge_score = self.summary_evaluator.evaluate(text, summary)
        if similarity < 0.4:
            failures.append(self.failure_message_sentence_transformers(text_title, similarity, summary_type))
        if max_rouge_score < 0.3:
            failures.append(self.failure_message_rouge(text_title, max_rouge_score, summary_type))
        return failures

    def failure_message_sentence_transformers(self, text_title, similarity, summary_type="map_reduce"):
        """Generate failure message for low sentence transformers similarity"""
        return (f"Summary may not be relevant ("
                f"text title: '{text_title}', "
                f"summary_type: '{summary_type}', "
                f"sentence transformers similarity score: {similarity})")

    def failure_message_rouge(self, text_title, max_rouge_score, summary_type="map_reduce"):
        """Generate failure message for low ROUGE score"""
        return (f"Summary may not be relevant ("
                f"text title: '{text_title}', "
                f"summary_type: '{summary_type}', "
                f"max rouge score: {max_rouge_score})")

    def prepare_file_attachment(self, file_name):
        """Prepare a file attachment (name, bytes) for a DocSum multipart upload"""
        file_path = os.path.join(TEST_FILES_DIR, "docsum", file_name)
        with open(file_path, 'rb') as f:
            content_bytes = f.read()
        return (file_name, content_bytes)
