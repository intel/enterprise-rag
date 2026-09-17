# TEI Embedding Model Server

This README provides instructions on how to run a model server using [TEI](https://github.com/huggingface/text-embeddings-inference).

> [!IMPORTANT]
> TEI is kept **only** as the embedding service for the RAG evaluation benchmarks in
> [src/tests/e2e/evals](../../../../../tests/e2e/evals), where RAGAS metrics need a standalone
> embedding endpoint. It is **not** a supported model server for the Embedding Microservice
> or for an Intel AI for Enterprise RAG deployment - the `EMBEDDING_MODEL_SERVER=tei`
> connector no longer exists. For local microservice testing use
> [vLLM](../vllm/) or [OVMS](../ovms/) instead.

## Table of Contents

1. [TEI Embedding Model Server](#tei-embedding-model-server)
2. [Getting Started](#getting-started)
   - 2.1. [🚀 Start the TEI Service via script](#-start-the-tei-service-via-script)
   - 2.2. [Service Cleanup](#service-cleanup)
   - 2.3. [Verify the Service](#verify-the-service)

## Getting Started

### 🚀 Start the TEI Service via script

```bash
chmod +x run_tei.sh
./run_tei.sh
```

The script initiates a Docker container with the text embeddings inference service running on port `TEI_PORT` (default: **8090**). Configuration settings are specified in the environment configuration file [docker/.env](./docker/.env). You can adjust these settings either by modifying the dotenv file or by exporting environment variables.

### Service Cleanup

```bash
cd docker

docker compose down
```

### Verify the Service

- Test the `embedding-tei-model-server` using the following command:
    ```bash
    curl http://localhost:8090/embed \
        -X POST \
        -d '{"inputs":"What is Deep Learning?"}' \
        -H 'Content-Type: application/json'
    ```
