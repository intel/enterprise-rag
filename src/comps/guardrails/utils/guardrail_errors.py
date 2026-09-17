# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Shared error handling for the LLM Guard guardrail classes."""

from contextlib import contextmanager

from fastapi import HTTPException


@contextmanager
def guardrail_errors(logger, guardrail_name, *, as_http=False):
    """
    Unified error handler for scanner initialisation and scanning.

    When *as_http* is False (init phase), exceptions are logged and re-raised unchanged.
    When *as_http* is True (scan phase), exceptions are wrapped in HTTPException (400/500),
    except HTTPException itself which passes through.

    Args:
        logger: The guardrail's logger.
        guardrail_name (str): The guardrail name for the message, e.g. "Input".
        as_http (bool): If True, wrap errors as HTTPException responses.
    """
    try:
        yield
    except HTTPException:
        raise
    except ValueError as e:
        if as_http:
            error_msg = f"Validation Error occurred while scanning with LLM Guard {guardrail_name} Guardrail: {e}"
            logger.exception(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
        else:
            logger.exception(f"Value Error occurred while initializing LLM Guard {guardrail_name} Guardrail scanners: {e}")
            raise
    except Exception as e:
        if as_http:
            error_msg = f"An unexpected error occurred during scanning prompt with LLM Guard {guardrail_name} Guardrail: {e}"
            logger.exception(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
        else:
            logger.exception(f"An unexpected error occurred during initializing LLM Guard {guardrail_name} Guardrail scanners: {e}")
            raise
