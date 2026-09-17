# Intel® AI for Enterprise RAG LLMs Microservice

Part of the Intel® AI for Enterprise RAG ecosystem.

## 🔍 Overview

The Intel® AI for Enterprise RAG LLMs microservice interfaces with various LLMs to process queries and reranked documents by constructing prompts and performing inference.

### Support Matrix

| Model server name |  Status   |
| ------------------| --------- |
| VLLM              | &#x2713;   |

### Features

- Supports streaming and non-streaming LLM inference

## 🔗 Related Components

This service integrates with other Intel® AI for Enterprise RAG components:
- Intel AI for Enterprise RAG Prompt Template and Retriever & Reranker microservices are components that build the final prompt for the LLM
- It triggers inference requests with vLLM Model Server running on Intel® Xeon® Processors
- Its input is scanned by Intel AI for Enterprise RAG Input Guardrails (if enabled)
- Its output is scanned by Intel AI for Enterprise RAG Output Guardrails (if enabled)

## License

Intel AI for Enterprise RAG is licensed under the Apache License, Version 2.0.

Copyright © 2024–2026 Intel Corporation. All rights reserved.