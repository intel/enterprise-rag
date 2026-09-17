# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
import time

from fastapi import HTTPException

from comps.cores.mega.logger import get_erag_logger
from comps.cores.proto.docarray import GeneratedDoc
from comps.guardrails.llm_guard_output_guardrail.utils.llm_guard_output_scanners import OutputScannersConfig
from comps.guardrails.utils.guardrail_errors import guardrail_errors


logger = get_erag_logger("erag_llm_guard_output_guardrail_microservice")

GUARDRAIL_NAME = "Output"

class EragLLMGuardOutputGuardrail:
    """
    EragLLMGuardOutputGuardrail is responsible for scanning and sanitizing LLM output responses
    using various output scanners provided by LLM Guard.

    This class initializes the output scanners based on the provided configuration and
    scans the output responses to ensure they meet the required guardrail criteria.

    Attributes:
        _scanners (list): A list of enabled scanners.

    Methods:
        __init__(usv_config: list):
            Initializes the EragLLMGuardOutputGuardrail with the provided configuration.

        scan_llm_output(output_doc: object) -> str:
            Scans the output from an LLM output document and returns the sanitized output.
    """

    def __init__(self, usv_config: list):
        """
        Initializes the EragLLMGuardOutputGuardrail with the provided configuration.

        Args:
            usv_config (list): The configuration list for initializing the output scanners.

        Raises:
            Exception: If an unexpected error occurs during the initialization of scanners.
        """
        with guardrail_errors(logger, GUARDRAIL_NAME):
            self._scanners_config = OutputScannersConfig(usv_config)
            self._scanners = self._scanners_config.create_enabled_output_scanners()

    def _scan_output(self, prompt: str, output: str, fail_fast: bool = False) -> tuple[str, dict[str, bool], dict[str, float]]:
        sanitized_output = output
        results_valid = {}
        results_score = {}

        if len(self._scanners) == 0 or output.strip() == "":
            return sanitized_output, results_valid, results_score

        start_time = time.time()
        for scanner in self._scanners:
            start_time_scanner = time.time()
            sanitized_output, is_valid, risk_score = scanner.scan(prompt, sanitized_output)
            elapsed_time_scanner = time.time() - start_time_scanner

            logger.debug(f"Scanner {type(scanner).__name__} completed: is_valid={is_valid}, elapsed={round(elapsed_time_scanner, 6)}s")

            results_valid[type(scanner).__name__] = is_valid
            results_score[type(scanner).__name__] = risk_score
            if fail_fast and not is_valid:
                break

        elapsed_time = time.time() - start_time
        logger.info(f"Scanned output: scores={results_score}, elapsed={round(elapsed_time, 6)}s")

        return sanitized_output, results_valid, results_score

    def scan_llm_output(self, output_doc: GeneratedDoc) -> str:
        """
        Scans the output from an LLM output document.

        Args:
            output_doc (object): The output document containing the response to be scanned.

        Returns:
            str: The sanitized output.

        Raises:
            HTTPException: If the output is not valid based on the scanner results.
            Exception: If an unexpected error occurs during scanning.
        """
        with guardrail_errors(logger, GUARDRAIL_NAME, as_http=True):
            if output_doc.output_guardrail_params is not None:
                self._scanners_config.vault = output_doc.output_guardrail_params.anonymize_vault
                if self._scanners_config.changed(output_doc.output_guardrail_params.dict()):
                    self._scanners = self._scanners_config.create_enabled_output_scanners()
            else:
                logger.warning("Output guardrail params not found in input document.")
            if self._scanners:
                sanitized_output, results_valid, results_score = self._scan_output(
                    output_doc.prompt, output_doc.text
                    )
                if False in results_valid.values():
                    msg = f"LLM Output {output_doc.text} is not valid, scores: {results_score}"
                    logger.error(msg)
                    usr_msg = "I'm sorry, but the model output is not valid according to the policies."
                    redact_or_truncated = [c.get('redact', False) or c.get('truncate', False) for _, c in self._scanners_config._output_scanners_config.items()] # to see if sanitized output available
                    if any(redact_or_truncated):
                        usr_msg = f"We sanitized the answer due to the guardrails policies: {sanitized_output}"
                    raise HTTPException(status_code=466, detail=usr_msg)
                return sanitized_output
            else:
                logger.warning("No output scanners enabled. Skipping scanning.")
                return output_doc.text
