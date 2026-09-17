# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import ast
import os
import time
from typing import Union

import requests
from dotenv import load_dotenv
from fastapi import HTTPException

from comps.cores.mega.base_statistics import register_statistics, statistics_dict
from comps.cores.mega.constants import MegaServiceEndpoint, ServiceType
from comps.cores.mega.logger import change_erag_logger_level, get_erag_logger
from comps.cores.mega.micro_service import erag_microservices, register_microservice
from comps.cores.mega.utils import get_access_token
from comps.cores.proto.docarray import EmbedDoc, EmbedDocList, TextDoc, TextDocList
from comps.cores.utils.utils import sanitize_env
from comps.embeddings.utils.erag_embedding import EragEmbedding

# Define the unique service name for the microservice
USVC_NAME='erag_service@embedding'

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "impl/microservice/.env"))

# Initialize the logger for the microservice
logger = get_erag_logger(f"{__file__.split('comps/')[1].split('/', 1)[0]}_microservice")
change_erag_logger_level(logger, log_level=os.getenv("ERAG_LOGGER_LEVEL", "INFO"))

# Check if EMBEDDING_CONNECTOR is defined and issue a deprecation warning
if os.getenv("EMBEDDING_CONNECTOR"):
    logger.warning("EMBEDDING_CONNECTOR environment variable is deprecated and will be ignored.")

# Get the token
access_token = get_access_token(sanitize_env(os.getenv('EMBEDDING_VLLM_TOKEN_URL')), sanitize_env(os.getenv('EMBEDDING_VLLM_CLIENT_ID')), sanitize_env(os.getenv('EMBEDDING_VLLM_CLIENT_SECRET'))) if sanitize_env(os.getenv('EMBEDDING_VLLM_TOKEN_URL')) and sanitize_env(os.getenv('EMBEDDING_VLLM_CLIENT_ID')) and sanitize_env(os.getenv('EMBEDDING_VLLM_CLIENT_SECRET')) else None
# If token is passed directly override it
if os.getenv('EMBEDDING_VLLM_API_KEY'):
    access_token = sanitize_env(os.getenv('EMBEDDING_VLLM_API_KEY'))

headers = {}
if access_token:
    headers = {"Authorization": f"Bearer {access_token}"}

# Initialize an instance of the EragEmbedding class with environment variables.
erag_embedding = EragEmbedding(
    model_name=sanitize_env(os.getenv("EMBEDDING_MODEL_NAME")),
    model_server=sanitize_env(os.getenv("EMBEDDING_MODEL_SERVER")),
    endpoint=sanitize_env(os.getenv("EMBEDDING_MODEL_SERVER_ENDPOINT")),
    headers=headers,
)

# Register the microservice with the specified configuration.
@register_microservice(
    name=USVC_NAME,
    service_type=ServiceType.EMBEDDING,
    endpoint=str(MegaServiceEndpoint.EMBEDDINGS),
    host="0.0.0.0",
    port=int(os.getenv('EMBEDDING_USVC_PORT', default=6000)),
    input_datatype=Union[TextDoc, TextDocList],
    output_datatype=Union[EmbedDoc, EmbedDocList],
    validate_methods=[erag_embedding._connector._validate]
)
@register_statistics(names=[USVC_NAME])
# Define a function to handle processing of input for the microservice.
# Its input and output data types must comply with the registered ones above.
async def process(input: Union[TextDoc, TextDocList]) -> Union[EmbedDoc, EmbedDocList]:
    """
    Process the input document using the EragEmbedding.

    Args:
        input (Union[TextDoc, TextDocList]): The input document to be processed.
    """
    start = time.time()
    logger.debug(f"Received input: {input}")

    try:
        # Pass the input to the 'run' method of the microservice instance
        res = await erag_embedding.run(input)

    except ValueError as e:
        logger.exception(f"ValueError occurred while validating the input: {str(e)}")
        raise HTTPException(status_code=400,
                            detail=f"ValueError occurred while validating the input: {str(e)}"
        )
    except requests.exceptions.HTTPError as e:
        if hasattr(e.response, "status_code") and e.response.status_code == 413:
            raise HTTPException(status_code=413, detail=f"Input text is too long. Provide a valid input text. Error: {ast.literal_eval(e.response.text)['error']}")
        else:
            raise HTTPException(status_code=e.response.status_code, detail=ast.literal_eval(e.response.text)['error'])
    except NotImplementedError as e:
        logger.exception(f"NotImplementedError occured: {str(e)}")
        raise HTTPException(status_code=501,
                            detail=f"NotImplementedError occured: {str(e)}"
        )
    except Exception as e:
         logger.exception(f"An error occurred while processing: {str(e)}")
         raise HTTPException(status_code=500,
                             detail=f"An error occurred while processing: {str(e)}"
    )
    statistics_dict[USVC_NAME].append_latency(time.time() - start, None)
    res.history_id = input.history_id
    return res


if __name__ == "__main__":
    # Start the microservice
    erag_microservices[USVC_NAME].start()
    logger.info(f"Started ERAG Microservice: {USVC_NAME}")
