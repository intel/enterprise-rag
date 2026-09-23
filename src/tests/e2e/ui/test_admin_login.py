#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import allure
import logging
import pytest

from tests.e2e.validation.buildcfg import cfg

logger = logging.getLogger(__name__)


def _get_valid_redirect_paths() -> list:
    """
    Get valid redirect paths based on deployed pipelines.
    
    Returns list of valid paths user can be redirected to after login.
    """
    pipeline_type = cfg.get("pipeline_type")
    if pipeline_type == "chatqna":
        return ["/chat"]
    elif pipeline_type == "docsum":
        return ["/docsum", "/docsum/paste-text"]
    elif pipeline_type == "translation":
        return ["/translation"]
    return ["/chat", "/docsum", "/translation"]


@allure.testcase("IEASG-T266")
@pytest.mark.ui
@pytest.mark.ui_smoke
@pytest.mark.asyncio
async def test_admin_login(page, admin_credentials):
    """Test admin login with KeycloakHelper credentials.
    
    Success criteria: User is redirected to a valid pipeline page after login.
    Valid redirects depend on deployed pipelines (chatqna -> /chat, docsum -> /docsum).
    """
    USERNAME = admin_credentials['username']
    PASSWORD = admin_credentials['password']
    erag_domain = f"https://{cfg.get('base_domain_name')}"
    
    logger.info(f"Testing admin login with username: {USERNAME}")
    
    # Navigate to login page
    await page.goto(erag_domain)
    
    # Fill credentials
    await page.fill("#username", USERNAME)
    await page.fill("#password", PASSWORD)
    
    # Click login button
    await page.click("#kc-login")
    
    # Wait for navigation after login
    await page.wait_for_load_state("networkidle")
    
    # Verify success: should redirect to a valid pipeline path
    current_url = page.url
    valid_paths = _get_valid_redirect_paths()
    
    # Check if current URL ends with any valid path
    is_valid_redirect = any(current_url.startswith(f"{erag_domain}{path}") for path in valid_paths)
    
    assert is_valid_redirect, \
        f"Login failed: expected redirect to one of {valid_paths}, but got {current_url}"
    
    logger.info(f"Admin login successful: redirected to {current_url}")