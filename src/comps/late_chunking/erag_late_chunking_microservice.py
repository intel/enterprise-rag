# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time

from dotenv import load_dotenv
from fastapi import HTTPException

from comps.cores.mega.base_statistics import register_statistics, statistics_dict
from comps.cores.mega.constants import MegaServiceEndpoint, ServiceType
from comps.cores.mega.logger import change_erag_logger_level, get_erag_logger
from comps.cores.mega.micro_service import erag_microservices, register_microservice
from comps.cores.proto.docarray import EmbedDocList, LateChunkingInput
from comps.cores.utils.utils import sanitize_env
from comps.late_chunking.utils.erag_late_chunking import EragLateChunking


# Define the unique service name for the microservice
USVC_NAME='erag_service@late_chunking'

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "impl/microservice/.env"))

# Initialize the logger for the microservice
logger = get_erag_logger(f"{__file__.split('comps/')[1].split('/', 1)[0]}_microservice")
change_erag_logger_level(logger, log_level=os.getenv("ERAG_LOGGER_LEVEL", "INFO"))

# Initialize an instance of the EragLateChunking class with environment variables.

erag_late_chunking = EragLateChunking(
    embedding_endpoint=sanitize_env(os.getenv("EMBEDDING_ENDPOINT", "http://embedding-svc.chatqa.svc:6000/v1/embeddings")),
    model_name=sanitize_env(os.getenv("EMBEDDING_MODEL_NAME")),
    chunk_size=int(os.getenv("CHUNK_SIZE", "256")),
    chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "0")),
    strategy=sanitize_env(os.getenv("LATE_CHUNKING_STRATEGY", "fixed"))
    )

# Register the microservice with the specified configuration.
@register_microservice(
    name=USVC_NAME,
    service_type=ServiceType.LATE_CHUNKING,
    endpoint=str(MegaServiceEndpoint.LATE_CHUNKING),
    host='0.0.0.0',
    port=int(os.getenv('LATE_CHUNKING_USVC_PORT', default=8003)),
    input_datatype=LateChunkingInput,
    output_datatype=EmbedDocList
)

@register_statistics(names=[USVC_NAME])
# Define a function to handle processing of input for the microservice.
# Its input and output data types must comply with the registered ones above.
def process(input: LateChunkingInput) -> EmbedDocList:
    start = time.time()
    try:
        # Pass the input to the 'run' method of the microservice instance
        res = erag_late_chunking.run(input)
    except ValueError as e:
        logger.exception(f"An internal error occurred while processing: {str(e)}")
        raise HTTPException(status_code=400,
                            detail=f"An internal error occurred while processing: {str(e)}"
        )
    except Exception as e:
         logger.exception(f"An error occurred while processing: {str(e)}")
         raise HTTPException(status_code=500,
                             detail=f"An error occurred while processing: {str(e)}"
    
    )
    statistics_dict[USVC_NAME].append_latency(time.time() - start, None)

    return res


if __name__ == "__main__":
    # Start the microservice
    erag_microservices[USVC_NAME].start()
    logger.info(f"Started ERAG Microservice: {USVC_NAME}")
