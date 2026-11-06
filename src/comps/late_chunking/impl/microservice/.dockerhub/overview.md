# Intel® Chatbot Toolkit Late Chunking Service

Part of the Intel® Chatbot Toolkit ecosystem.

## Overview

The Intel® Chatbot Toolkit Late Chunking Microservice enhances embedding quality by applying chunking after token-level embeddings are generated. This microservice takes documents as input, obtains token embeddings from an embedding service, then intelligently chunks the text and pools the token embeddings to create high-quality chunk representations. This approach preserves contextual information better than traditional "chunk-then-embed" methods.


## 🔗 Related Components

This service works within the Intel® Chatbot Toolkit ecosystem:
- Embedding service to obtain token-level embeddings with pooling layer
- Enhanced Dataprep service to store chunked embeddings in vector database

## License
Intel® Chatbot Toolkit is licensed under the Apache License, Version 2.0.

Copyright © 2024–2026 Intel Corporation. All rights reserved.