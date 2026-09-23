// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Edge, Node, Position, XYPosition } from "@xyflow/react";

import { GraphNodeId } from "@/configs/graphs/graphNodeId";
import { ServiceData } from "@/types/index";

type GraphNodeArgs = Partial<
  Pick<
    ServiceData,
    | "llmArgs"
    | "retrieverArgs"
    | "rerankerArgs"
    | "promptTemplateArgs"
    | "inputGuardArgs"
    | "outputGuardArgs"
    | "docsumArgs"
  >
>;

export interface CreateNodeOptions extends GraphNodeArgs {
  displayName: string;
  position: XYPosition;
  sourcePosition?: Position;
  targetPosition?: Position;
  additionalSourcePosition?: Position;
  additionalSourceId?: string;
  additionalTargetPosition?: Position;
  additionalTargetId?: string;
  configurable?: boolean;
  focusable?: boolean;
  selectable?: boolean;
}

export const createNode = (
  id: GraphNodeId,
  options: CreateNodeOptions,
): Node<ServiceData> => {
  const {
    displayName,
    position,
    sourcePosition,
    targetPosition,
    additionalSourcePosition,
    additionalSourceId,
    additionalTargetPosition,
    additionalTargetId,
    configurable = false,
    focusable = configurable,
    selectable = configurable,
    ...args
  } = options;

  return {
    id,
    position,
    data: {
      id,
      displayName,
      selected: false,
      configurable,
      sourcePosition,
      targetPosition,
      additionalSourcePosition,
      additionalSourceId,
      additionalTargetPosition,
      additionalTargetId,
      ...args,
    },
    type: "serviceNode",
    focusable,
    selectable,
  };
};

export interface CreateEdgeOptions {
  sourceHandle?: string;
  targetHandle?: string;
  selectable?: boolean;
}

export const createEdge = (
  source: GraphNodeId,
  target: GraphNodeId,
  options: CreateEdgeOptions = {},
): Edge => ({
  id: `${source}-${target}`,
  source,
  target,
  selectable: false,
  ...options,
});
