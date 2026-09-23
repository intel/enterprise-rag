# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import time

from fastapi import HTTPException

from comps.cores.mega.logger import get_erag_logger
from comps.cores.proto.docarray import TextDocList
from comps.guardrails.llm_guard_dataprep_guardrail.utils.llm_guard_dataprep_scanners import DataprepScannersConfig
from comps.guardrails.utils.guardrail_errors import guardrail_errors


logger = get_erag_logger("erag_llm_guard_dataprep_guardrail_microservice")

GUARDRAIL_NAME = "Dataprep"


class EragLLMGuardDataprepGuardrail:

    def __init__(self, usv_config: dict):

        with guardrail_errors(logger, GUARDRAIL_NAME):
            self._scanners_config = DataprepScannersConfig(usv_config)
            self._scanners = self._scanners_config.create_enabled_dataprep_scanners()

    def _scan_prompt(self, prompt: str, fail_fast: bool = False) -> tuple[str, dict[str, bool], dict[str, float]]:
        sanitized_prompt = prompt
        results_valid = {}
        results_score = {}

        if len(self._scanners) == 0 or prompt.strip() == "":
            return sanitized_prompt, results_valid, results_score

        start_time = time.time()
        for scanner in self._scanners:
            start_time_scanner = time.time()
            sanitized_prompt, is_valid, risk_score = scanner.scan(sanitized_prompt)
            elapsed_time_scanner = time.time() - start_time_scanner

            logger.debug(f"Scanner {type(scanner).__name__} completed: is_valid={is_valid}, elapsed={round(elapsed_time_scanner, 6)}s")

            results_valid[type(scanner).__name__] = is_valid
            results_score[type(scanner).__name__] = risk_score
            if fail_fast and not is_valid:
                break

        elapsed_time = time.time() - start_time
        logger.info(f"Scanned prompt: scores={results_score}, elapsed={round(elapsed_time, 6)}s")

        return sanitized_prompt, results_valid, results_score

    def scan_dataprep_docs(self, dataprep_docs: TextDocList) -> TextDocList:
        with guardrail_errors(logger, GUARDRAIL_NAME, as_http=True):
            if dataprep_docs.dataprep_guardrail_params is not None:
                if self._scanners_config.changed(dataprep_docs.dataprep_guardrail_params.dict()):
                    self._scanners = self._scanners_config.create_enabled_dataprep_scanners()
            else:
                logger.warning("Input guardrail params not found in dataprep request.")
            if self._scanners:
                for doc in dataprep_docs.docs:
                    sanitized_text, results_valid, results_score = self._scan_prompt(doc.text)

                    if False in results_valid.values():
                        msg = f"Ingested doc is not valid, scores: {results_score}"
                        logger.error(f"{msg}")
                        usr_msg = "I'm sorry, I cannot ingest this document, becasue it does not comply with our standards."
                        raise HTTPException(status_code=466, detail=f"{usr_msg}")
                    doc.text = sanitized_text
                return dataprep_docs
            else:
                logger.info("No input scanners enabled. Skipping scanning.")
                return dataprep_docs
