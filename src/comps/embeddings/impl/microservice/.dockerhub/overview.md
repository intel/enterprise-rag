# Intel® AI for Enterprise RAG Embedding Microservice

Part of the Intel® AI for Enterprise RAG ecosystem.

## 🔍 Overview

The Intel® AI for Enterprise RAG Embedding Microservice is designed to efficiently convert textual strings into vectorized embeddings, facilitating seamless integration into various machine learning and data processing workflows. This microservice provides a unified API for generating embeddings from text or documents, simplifying embedding integration across the platform. It interacts with an embedding model endpoint to perform the actual embedding computation. These embeddings are then used by downstream components such as retrievers and rerankers to improve search relevance and contextual understanding. 

### Support Matrix

| Model server  | Status    |
| ------------- | --------- |
| vLLM          | &#x2713;  |
| OVMS          | &#x2713;  |

## 🔗 Related Components

This service integrates with other Intel® AI for Enterprise RAG components:
- Dataprep Service supplies cleaned and preprocessed input data for embedding generation
- Embedding model server, deployed by Intel® AI for Enterprise Solutions through Enterprise Inference, performs the actual embedding computation
- Vector Database stores embeddings for fast similarity search and retrieval
- Retriever Microservice uses embeddings to find relevant documents based on query similarity

## License

Intel® AI for Enterprise RAG is licensed under the Apache License, Version 2.0.

Copyright © 2024–2026 Intel Corporation. All rights reserved.
