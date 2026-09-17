// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  createEdge,
  createNode,
  docsumArgumentsDefault,
  GraphNodeId,
  llmArgumentsDefault,
} from "@intel-enterprise-rag-ui/control-plane";
import { Position } from "@xyflow/react";

const graphNodes = [
  createNode(GraphNodeId.TextExtractor, {
    displayName: "Text Extractor",
    position: { x: 0, y: 0 },
    sourcePosition: Position.Right,
  }),
  createNode(GraphNodeId.TextCompression, {
    displayName: "Text Compression",
    position: { x: 200, y: 0 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }),
  createNode(GraphNodeId.TextSplitter, {
    displayName: "Text Splitter",
    position: { x: 400, y: 0 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }),
  createNode(GraphNodeId.Docsum, {
    displayName: "DocSum",
    position: { x: 600, y: 0 },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Left,
    configurable: true,
    docsumArgs: docsumArgumentsDefault,
  }),
  createNode(GraphNodeId.Llm, {
    displayName: "LLM",
    position: { x: 600, y: 144 },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    configurable: true,
    llmArgs: llmArgumentsDefault,
  }),
  createNode(GraphNodeId.LlmModelServer, {
    displayName: "LLM Model Server",
    position: { x: 600, y: 288 },
    targetPosition: Position.Top,
  }),
];

const graphEdges = [
  createEdge(GraphNodeId.TextExtractor, GraphNodeId.TextCompression),
  createEdge(GraphNodeId.TextCompression, GraphNodeId.TextSplitter),
  createEdge(GraphNodeId.TextSplitter, GraphNodeId.Docsum),
  createEdge(GraphNodeId.Docsum, GraphNodeId.Llm),
  createEdge(GraphNodeId.Llm, GraphNodeId.LlmModelServer),
];

export { graphEdges, graphNodes };
