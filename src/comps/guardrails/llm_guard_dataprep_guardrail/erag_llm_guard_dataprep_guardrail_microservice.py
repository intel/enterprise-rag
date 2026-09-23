
# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os

from dotenv import dotenv_values

from comps.cores.mega.base_statistics import register_statistics
from comps.cores.mega.constants import MegaServiceEndpoint, ServiceType
from comps.cores.mega.logger import change_erag_logger_level, get_erag_logger
from comps.cores.mega.micro_service import erag_microservices, register_microservice
from comps.cores.proto.docarray import TextDocList
from comps.guardrails.llm_guard_dataprep_guardrail.utils.llm_guard_dataprep_guardrail import (
    EragLLMGuardDataprepGuardrail
)


USVC_NAME = "erag_service@llm_guard_dataprep_scanner"
logger = get_erag_logger("erag_llm_guard_dataprep_guardrail_microservice")

usvc_config = {
    **dotenv_values("impl/microservice/.env"),
    **os.environ # override loaded values with environment variables - priority
}

dataprep_guardrail = EragLLMGuardDataprepGuardrail(usvc_config)

@register_microservice(
    name=USVC_NAME,
    service_type=ServiceType.LLM_GUARD_DATAPREP_SCANNER,
    endpoint=str(MegaServiceEndpoint.LLM_GUARD_DATAPREP_SCANNER),
    host="0.0.0.0",
    port=int(usvc_config.get('LLM_GUARD_DATAPREP_SCANNER_USVC_PORT', 8070)),
    input_datatype=TextDocList,
    output_datatype=TextDocList,
)

@register_statistics(names=[USVC_NAME])
def process(dataprep_docs: TextDocList) -> TextDocList:
    """
    Process the documents uploaded to dataprep using the EragLLMGuardDataprepGuardrail.
    This function processes the input document by scanning it using the LLM Guard Dataprep Scanner.

    Args:
        dataprep_docs (TextDocList): The input document to be processed.

    Returns:
        TextDocList: The scanned dataprep documents.
    """
    return dataprep_guardrail.scan_dataprep_docs(dataprep_docs)


if __name__ == "__main__":
    log_level = usvc_config.get("ERAG_LOGGER_LEVEL", "INFO")
    change_erag_logger_level(logger, log_level)

    erag_microservices[USVC_NAME].start()