// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export enum GraphNodeId {
  EmbeddingModelServer = "embedding_model_server",
  Embedding = "embedding",
  Retriever = "retriever",
  VectorDB = "vectordb",
  Reranker = "reranker",
  RerankerModelServer = "reranker_model_server",
  PromptTemplate = "prompt_template",
  InputGuard = "input_guard",
  Llm = "llm",
  LlmModelServer = "llm_model_server",
  OutputGuard = "output_guard",
  Asr = "asr",
  VllmAudioCpu = "vllm-audio-cpu",
  Tts = "tts",
  TtsModelServer = "tts-model-server",
  TextExtractor = "text_extractor",
  TextCompression = "text_compression",
  TextSplitter = "text_splitter",
  Docsum = "docsum",
}
