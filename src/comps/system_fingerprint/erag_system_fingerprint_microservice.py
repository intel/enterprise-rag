# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Dict, List, Optional

from fastapi import HTTPException

from comps.cores.mega.constants import MegaServiceEndpoint
from comps.cores.mega.logger import change_erag_logger_level, get_erag_logger
from comps.cores.mega.micro_service import erag_microservices, register_microservice
from comps.cores.proto.docarray import ComponentArgument
from comps.cores.utils.utils import sanitize_env
from comps.system_fingerprint.utils.erag_system_fingerprint import (
    EragSystemFingerprintController,
    params_kind_catalog,
)


USVC_NAME = "erag_service@system_fingerprint"

logger = get_erag_logger(f"{__file__.split('comps/')[1].split('/', 1)[0]}_microservice")
change_erag_logger_level(logger, os.getenv("ERAG_LOGGER_LEVEL", "INFO"))

fingerprint_controller = EragSystemFingerprintController(
    host=sanitize_env(os.getenv("SYSTEM_FINGERPRINT_POSTGRES_HOST", "127.0.0.1")),
    port=int(os.getenv("SYSTEM_FINGERPRINT_POSTGRES_PORT", default=5432)),
    db_name=sanitize_env(os.getenv("SYSTEM_FINGERPRINT_DATABASE_NAME", "system_fingerprint")),
    user=sanitize_env(os.getenv("SYSTEM_FINGERPRINT_POSTGRES_USER", "postgres")),
    password=sanitize_env(os.getenv("SYSTEM_FINGERPRINT_POSTGRES_PASSWORD", "postgres")),
    pipeline=sanitize_env(os.getenv("SYSTEM_FINGERPRINT_PIPELINE", "default")),
    tenant=sanitize_env(os.getenv("SYSTEM_FINGERPRINT_TENANT", "_global")),
    template_language=sanitize_env(os.getenv("SYSTEM_FINGERPRINT_TEMPLATE_LANGUAGE", "en")))


@register_microservice(
    name=USVC_NAME,
    endpoint=f"{MegaServiceEndpoint.SYSTEM_FINGERPRINT}/change_arguments",
    host="0.0.0.0",
    port=int(os.getenv('SYSTEM_FINGERPRINT_USVC_PORT', default=6012)),
    input_datatype=List[ComponentArgument],
    output_datatype=None,
    startup_methods=[fingerprint_controller.init_async],
    close_methods=[fingerprint_controller.close],
    validate_methods=[fingerprint_controller._validate]
)
async def change_arguments(inputs: List[ComponentArgument],
                           pipeline: Optional[str] = None,
                           tenant: Optional[str] = None) -> None:
    if not inputs:
        raise HTTPException(status_code=400, detail="Input is empty.")
    try:
        await fingerprint_controller.store_arguments(inputs, pipeline=pipeline, tenant=tenant)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while storing arguments.") from e


@register_microservice(
    name=USVC_NAME,
    endpoint=f"{MegaServiceEndpoint.SYSTEM_FINGERPRINT}/config",
    host="0.0.0.0",
    port=int(os.getenv('SYSTEM_FINGERPRINT_USVC_PORT', default=6012)),
    http_method="GET",
    input_datatype=Dict,
    output_datatype=None,
    startup_methods=[fingerprint_controller.init_async],
    close_methods=[fingerprint_controller.close],
    validate_methods=[fingerprint_controller._validate]
)
async def read_config(params_key: str, pipeline: Optional[str] = None,
                      tenant: Optional[str] = None) -> Dict:
    if not params_key:
        raise HTTPException(status_code=400, detail="params_key is required.")
    try:
        group = await fingerprint_controller.read_group(params_key, pipeline=pipeline, tenant=tenant)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while reading the config.") from e

    if group is None:
        raise HTTPException(status_code=404, detail=f"No config for params_key '{params_key}'.")
    return group


@register_microservice(
    name=USVC_NAME,
    endpoint=f"{MegaServiceEndpoint.SYSTEM_FINGERPRINT}/kinds",
    host="0.0.0.0",
    port=int(os.getenv('SYSTEM_FINGERPRINT_USVC_PORT', default=6012)),
    http_method="GET",
    input_datatype=None,
    output_datatype=None,
    startup_methods=[fingerprint_controller.init_async],
    close_methods=[fingerprint_controller.close],
    validate_methods=[fingerprint_controller._validate]
)
async def read_kinds() -> Dict:
    return params_kind_catalog()


@register_microservice(
    name=USVC_NAME,
    endpoint=f"{MegaServiceEndpoint.SYSTEM_FINGERPRINT}/ensure_keys",
    host="0.0.0.0",
    port=int(os.getenv('SYSTEM_FINGERPRINT_USVC_PORT', default=6012)),
    input_datatype=Dict,
    output_datatype=None,
    startup_methods=[fingerprint_controller.init_async],
    close_methods=[fingerprint_controller.close],
    validate_methods=[fingerprint_controller._validate]
)
async def ensure_keys(input: Dict) -> Dict:
    if not input:
        raise HTTPException(status_code=400, detail="Input is empty.")
    if "keys" not in input:
        raise HTTPException(status_code=400, detail="At least one key is required.")
    keys = input.get("keys")
    if isinstance(keys, list) and not keys:
        raise HTTPException(status_code=400, detail="At least one key is required.")
    pipeline = input.get("pipeline")
    tenant = input.get("tenant")
    try:
        await fingerprint_controller.ensure_keys(keys, pipeline=pipeline, tenant=tenant)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception(f"An error occurred: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while ensuring keys.") from e

    return {"status": "ok"}


if __name__ == "__main__":
    erag_microservices[USVC_NAME].start()
    logger.info(f"Started ERAG System Fingerprint microservice: {USVC_NAME}")
