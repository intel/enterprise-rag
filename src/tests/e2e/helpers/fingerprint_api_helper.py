#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import logging
import time

import requests

from tests.e2e.helpers.api_request_helper import ApiRequestHelper, ApiResponse
from tests.e2e.validation.buildcfg import cfg

logger = logging.getLogger(__name__)


class FingerprintApiHelper(ApiRequestHelper):

    def __init__(self, keycloak_helper):
        super().__init__(keycloak_helper=keycloak_helper)
        self.change_args_api_path = f"https://{cfg.get('base_domain_name')}/v1/system_fingerprint/change_arguments"
        self.config_api_path = f"https://{cfg.get('base_domain_name')}/v1/system_fingerprint/config"

    def change_arguments(self, json_data, as_user=False, pipeline=None, tenant=None):
        """
        /v1/system_fingerprint/change_arguments API call

        An optional pipeline/tenant selects the scope the write targets; both
        fall back to the microservice's configured scope when omitted.
        """
        params = {}
        if pipeline is not None:
            params["pipeline"] = pipeline
        if tenant is not None:
            params["tenant"] = tenant
        start_time = time.time()
        response = requests.post(
            self.change_args_api_path,
            headers=self.get_headers(as_user=as_user),
            json=json_data,
            params=params,
            verify=False,
            timeout=10
        )
        duration = round(time.time() - start_time, 2)
        logger.info(f"Fingerprint (/v1/system_fingerprint/change_arguments) call duration: {duration}")
        return ApiResponse(response, duration)

    def read_config(self, params_key, as_user=False, pipeline=None, tenant=None):
        """
        /v1/system_fingerprint/config API call for a single params_key

        An optional pipeline/tenant selects the scope to read; both fall back to
        the microservice's configured scope when omitted.
        """
        params = {"params_key": params_key}
        if pipeline is not None:
            params["pipeline"] = pipeline
        if tenant is not None:
            params["tenant"] = tenant
        start_time = time.time()
        response = requests.get(
            self.config_api_path,
            headers=self.get_headers(as_user=as_user),
            params=params,
            verify=False,
            timeout=10
        )
        duration = round(time.time() - start_time, 2)
        logger.info(f"Fingerprint (/v1/system_fingerprint/config) call duration: {duration}")
        return ApiResponse(response, duration)

    def set_component_parameters(self, component, params_kind=None, pipeline=None, tenant=None, **parameters):
        """Change component parameters, optionally under a custom params_key/kind

        An optional pipeline/tenant selects the scope the write targets; both fall
        back to the microservice's configured scope when omitted. A test that
        asserts a pipeline behaviour change must name the pipeline it serves so
        the write reaches the scope the router reads.
        """
        item = {
            "name": component,
            "data": {
                **parameters
            }
        }
        if params_kind is not None:
            item["params_kind"] = params_kind
        return self.change_arguments([item], pipeline=pipeline, tenant=tenant)

    def set_chatqa_component_parameters(self, component, params_kind=None, **parameters):
        """Change component parameters on the scope the chatqa router reads.

        Wraps set_component_parameters with the chatqa pipeline and the shared
        _global tenant, so the chatqa pipeline tests need not repeat the scope.
        The scope is fixed here, so passing pipeline/tenant in parameters is
        rejected rather than sent as component data fields.
        """
        conflicting = {"pipeline", "tenant"} & parameters.keys()
        if conflicting:
            raise TypeError(
                f"{sorted(conflicting)} select the scope and cannot be passed as component "
                "parameters; the chatqa scope is fixed by set_chatqa_component_parameters")
        return self.set_component_parameters(
            component, params_kind=params_kind, pipeline="chatqna", tenant="_global", **parameters)
