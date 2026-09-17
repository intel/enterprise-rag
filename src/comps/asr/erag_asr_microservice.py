# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import time

from dotenv import load_dotenv
from fastapi import File, Form, HTTPException, UploadFile
from openai import BadRequestError
from requests.exceptions import ConnectionError, ReadTimeout, RequestException

from comps.asr.utils.erag_asr import EragAsr
from comps.cores.mega.base_statistics import register_statistics, statistics_dict
from comps.cores.mega.constants import MegaServiceEndpoint, ServiceType
from comps.cores.mega.logger import change_erag_logger_level, get_erag_logger
from comps.cores.mega.micro_service import erag_microservices, register_microservice
from comps.cores.proto.api_protocol import AudioTranscriptionResponse
from comps.cores.proto.docarray import Audio2TextDoc
from comps.cores.utils.utils import sanitize_env


# Define the unique service name for the microservice
USVC_NAME = 'erag_service@asr'

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "impl/microservice/.env"))

# Initialize the logger for the microservice
logger = get_erag_logger(f"{__file__.split('comps/')[1].split('/', 1)[0]}_microservice")
change_erag_logger_level(logger, log_level=os.getenv("ERAG_LOGGER_LEVEL", "INFO"))

# Initialize an instance of the ERAG ASR class with environment variables.
erag_asr = EragAsr(
    model_name=sanitize_env(os.getenv('ASR_MODEL_NAME')),
    model_server=sanitize_env(os.getenv('ASR_MODEL_SERVER')),
    model_server_endpoint=sanitize_env(os.getenv('ASR_MODEL_SERVER_ENDPOINT'))
)

# Register the microservice with the specified configuration.
@register_microservice(
    name=USVC_NAME,
    service_type=ServiceType.ASR,
    endpoint=str(MegaServiceEndpoint.ASR),
    host='0.0.0.0',
    port=int(os.getenv('ASR_USVC_PORT', default=9009)),
    input_datatype=Audio2TextDoc,
    output_datatype=AudioTranscriptionResponse,
    validate_methods=[erag_asr._validate_model_server],
)
@register_statistics(names=[USVC_NAME])
async def process(
    file: UploadFile = File(...),
    model: str = Form(None),
    language: str = Form("auto"),
    response_format: str = Form("json"),
) -> AudioTranscriptionResponse:
    """
    Processes audio transcription using the ERAG ASR microservice.

    Args:
        file: Audio file to transcribe
        model: Model name (optional)
        language: Language code (default: "auto")
        response_format: Response format (default: "json")

    Returns:
        AudioTranscriptionResponse: The transcription response.
    """
    start = time.time()
    try:
        file_content = await file.read()

        file_extension = os.path.splitext(file.filename)[1]
        logger.info(f"Processing file: {file.filename}")
        SUPPORTED_EXTENSIONS = [".mp3", ".wav"]
        if file_extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported audio file extension '{file_extension}'. Supported extensions are: {', '.join(SUPPORTED_EXTENSIONS)}")


        input_audio = Audio2TextDoc(
            file=file_content,
            model=model,
            language=language,
            response_format=response_format
        )

        res = await erag_asr.run(input_audio)

    except ValueError as e:
        error_message = f"A ValueError occurred while processing: {str(e)}"
        logger.exception(error_message)
        raise HTTPException(status_code=400, detail=error_message)
    except BadRequestError as e:
        error_message = f"A BadRequestError occurred while processing: {str(e)}"
        logger.exception(error_message)
        raise HTTPException(status_code=400, detail=error_message)
    except ReadTimeout as e:
        error_message = f"A Timeout error occurred while processing: {str(e)}"
        logger.exception(error_message)
        raise HTTPException(status_code=408, detail=error_message)
    except ConnectionError as e:
        error_message = f"A Connection error occurred while processing: {str(e)}"
        logger.exception(error_message)
        raise HTTPException(status_code=503, detail=error_message)
    except RequestException as e:
        error_message = f"A Request error occurred while processing: {str(e)}"
        logger.exception(error_message)
        raise HTTPException(status_code=500, detail=error_message)
    except Exception as e:
        error_message = f"An unexpected error occurred while processing: {str(e)}"
        logger.exception(error_message)
        raise HTTPException(status_code=500, detail=error_message)

    statistics_dict[USVC_NAME].append_latency(time.time() - start, None)
    return res


if __name__ == "__main__":
    # Start the microservice
    erag_microservices[USVC_NAME].start()
    logger.info(f"Started ERAG Microservice: {USVC_NAME}")
