# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time
from typing import Union

from dotenv import load_dotenv
from fastapi import HTTPException

from comps.cores.mega.base_statistics import register_statistics, statistics_dict
from comps.cores.mega.constants import MegaServiceEndpoint, ServiceType
from comps.cores.mega.logger import change_erag_logger_level, get_erag_logger
from comps.cores.mega.micro_service import erag_microservices, register_microservice
from comps.cores.proto.docarray import GeneratedDoc, PromptTemplateInput, TranslationInput
from comps.cores.utils.utils import sanitize_env
from comps.language_detection.utils.erag_language_detection import EragLanguageDetector


# Define the unique service name for the microservice
USVC_NAME='erag_service@language_detection'

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "impl/microservice/.env"))

# Initialize the logger for the microservice
logger = get_erag_logger(f"{__file__.split('comps/')[1].split('/', 1)[0]}_microservice")
change_erag_logger_level(logger, log_level=os.getenv("ERAG_LOGGER_LEVEL", "INFO"))

# Initialize an instance of the language detector class with environment variables.
erag_language_detector = EragLanguageDetector(is_standalone=(sanitize_env(os.getenv('LANG_DETECT_STANDALONE')) == "True"))

# Register the microservice with the specified configuration.
@register_microservice(
    name=USVC_NAME,
    service_type=ServiceType.LANGUAGE_DETECTION,
    endpoint=str(MegaServiceEndpoint.LANGUAGE_DETECTION),
    host='0.0.0.0',
    port=int(os.getenv('LANGUAGE_DETECTION_USVC_PORT', default=8001)),
    input_datatype=Union[GeneratedDoc, TranslationInput],
    output_datatype=PromptTemplateInput,
)
@register_statistics(names=[USVC_NAME])
# Define a function to handle processing of input for the microservice.
# Its input and output data types must comply with the registered ones above.
def process(input: Union[GeneratedDoc, TranslationInput]) -> PromptTemplateInput:
    """
    Process the input document using the EragLanguageDetector.

    Args:
        input (Union[GeneratedDoc, TranslationInput]): The input document to be processed.

    Returns:
        PromptTemplateInput: The prompt template and placeholders for translation.
    """
    start = time.time()
    try:
        # Pass the input to the 'run' method of the microservice instance
        res = erag_language_detector.run(input)
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
