// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  createEdge,
  createNode,
  GraphNodeId,
  llmArgumentsDefault,
  llmInputGuardArgumentsDefault,
  llmOutputGuardArgumentsDefault,
  promptTemplateArgumentsDefault,
  rerankerArgumentsDefault,
  retrieverArgumentsDefault,
} from "@intel-enterprise-rag-ui/control-plane";
import { Position } from "@xyflow/react";

export const llmNodePositionNoGuards = { x: 840, y: 144 };
export const llmModelServerNodePositionNoGuards = { x: 840, y: 288 };

const graphNodes = [
  createNode(GraphNodeId.EmbeddingModelServer, {
    displayName: "Embedding Model Server",
    position: { x: 40, y: 288 },
    targetPosition: Position.Top,
  }),
  createNode(GraphNodeId.Embedding, {
    displayName: "Embedding",
    position: { x: 40, y: 144 },
    sourcePosition: Position.Right,
    additionalSourcePosition: Position.Bottom,
    additionalSourceId: "embedding-embedding_model_server-source",
  }),
  createNode(GraphNodeId.Retriever, {
    displayName: "Retriever",
    position: { x: 240, y: 144 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    additionalTargetPosition: Position.Top,
    additionalTargetId: "retriever-vectordb-target",
    configurable: true,
    retrieverArgs: retrieverArgumentsDefault,
  }),
  createNode(GraphNodeId.VectorDB, {
    displayName: "VectorDB",
    position: { x: 240, y: 0 },
    sourcePosition: Position.Bottom,
  }),
  createNode(GraphNodeId.Reranker, {
    displayName: "Reranker",
    position: { x: 440, y: 144 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    additionalSourcePosition: Position.Bottom,
    additionalSourceId: "reranker-reranker_model_server-source",
    configurable: true,
    rerankerArgs: rerankerArgumentsDefault,
  }),
  createNode(GraphNodeId.RerankerModelServer, {
    displayName: "Reranker Model Server",
    position: { x: 440, y: 288 },
    targetPosition: Position.Top,
  }),
  createNode(GraphNodeId.PromptTemplate, {
    displayName: "Prompt Template",
    position: { x: 640, y: 144 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    configurable: true,
    promptTemplateArgs: promptTemplateArgumentsDefault,
  }),
  createNode(GraphNodeId.InputGuard, {
    displayName: "LLM Input Guard",
    position: { x: 840, y: 144 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    configurable: true,
    inputGuardArgs: llmInputGuardArgumentsDefault,
  }),
  createNode(GraphNodeId.Llm, {
    displayName: "LLM",
    position: { x: 1040, y: 144 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    additionalSourcePosition: Position.Bottom,
    additionalSourceId: "llm-llm_model_server-source",
    configurable: true,
    llmArgs: llmArgumentsDefault,
  }),
  createNode(GraphNodeId.LlmModelServer, {
    displayName: "LLM Model Server",
    position: { x: 1040, y: 288 },
    targetPosition: Position.Top,
  }),
  createNode(GraphNodeId.OutputGuard, {
    displayName: "LLM Output Guard",
    position: { x: 1240, y: 144 },
    targetPosition: Position.Left,
    configurable: true,
    outputGuardArgs: llmOutputGuardArgumentsDefault,
  }),
];

const graphEdges = [
  createEdge(GraphNodeId.Embedding, GraphNodeId.EmbeddingModelServer, {
    sourceHandle: "embedding-embedding_model_server-source",
  }),
  createEdge(GraphNodeId.Embedding, GraphNodeId.Retriever),
  createEdge(GraphNodeId.VectorDB, GraphNodeId.Retriever, {
    targetHandle: "retriever-vectordb-target",
  }),
  createEdge(GraphNodeId.Retriever, GraphNodeId.Reranker),
  createEdge(GraphNodeId.Reranker, GraphNodeId.RerankerModelServer, {
    sourceHandle: "reranker-reranker_model_server-source",
  }),
  createEdge(GraphNodeId.Reranker, GraphNodeId.PromptTemplate),
  createEdge(GraphNodeId.PromptTemplate, GraphNodeId.InputGuard),
  createEdge(GraphNodeId.PromptTemplate, GraphNodeId.Llm),
  createEdge(GraphNodeId.InputGuard, GraphNodeId.Llm),
  createEdge(GraphNodeId.Llm, GraphNodeId.LlmModelServer, {
    sourceHandle: "llm-llm_model_server-source",
  }),
  createEdge(GraphNodeId.Llm, GraphNodeId.OutputGuard),
];

export { graphEdges, graphNodes };
