# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from comps.cores.mega.constants import ServiceType
from comps.cores.mega.logger import get_erag_logger
from comps.cores.mega.micro_service import erag_microservices, register_microservice
from comps.cores.utils.utils import sanitize_env
from comps.namespace_status_watcher.utils.erag_namespace_status_watcher import EragNamespaceStatusWatcher


# Define the unique service name for the microservice
USVC_NAME = 'erag_service@namespace_status_watcher'

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "impl/microservice/.env"))

# Initialize the logger for the microservice
logger = get_erag_logger(f"{__file__.split('comps/')[1].split('/', 1)[0]}_microservice")

# Configuration
TARGET_NAMESPACE = sanitize_env(os.getenv("TARGET_NAMESPACE", "audio"))
SERVICE_PORT = int(os.getenv("NAMESPACE_STATUS_WATCHER_PORT", "9010"))

# Initialize the EragNamespaceStatusWatcher instance
try:
    erag_namespace_status_watcher = EragNamespaceStatusWatcher(target_namespace=TARGET_NAMESPACE)
    logger.info(f"Namespace Status Watcher Service initialized for namespace: {TARGET_NAMESPACE}")
except Exception as e:
    logger.error(f"Failed to initialize EragNamespaceStatusWatcher: {e}")
    raise


# Register the status endpoint
@register_microservice(
    name=USVC_NAME,
    service_type=ServiceType.NAMESPACE_STATUS_WATCHER,
    endpoint=f"/v1/{TARGET_NAMESPACE}/status",
    host='0.0.0.0',
    port=SERVICE_PORT,
    http_method="GET",
)
async def get_namespace_status_watcher():
    """
    Get the status of all resources in the namespace.

    Returns GMC-compatible status format.
    """
    try:
        # Query all resources in the namespace
        annotations = erag_namespace_status_watcher.get_namespace_resources()

        status, condition_type, condition_message = erag_namespace_status_watcher.compute_overall_status(annotations)
        logger.info(f"Overall status: {status} - {condition_type} - {condition_message}")

        # Build GMC-compatible response
        response = {
            "status": {
                "annotations": annotations,
            }
        }

        return JSONResponse(content=response)

    except Exception as e:
        logger.error(f"Error getting namespace status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get namespace status: {str(e)}")


if __name__ == "__main__":
    # Start the microservice
    erag_microservices[USVC_NAME].start()
