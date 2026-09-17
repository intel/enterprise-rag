// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  AsyncThunk,
  CaseReducer,
  createAsyncThunk,
  createSlice,
  PayloadAction,
  Slice,
} from "@reduxjs/toolkit";
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Connection,
  Edge,
  EdgeChange,
  Node,
  NodeChange,
  XYPosition,
} from "@xyflow/react";

import {
  FetchedServiceDetails,
  FetchedServicesData,
} from "@/types/api/services";
import { ServiceData } from "@/types/index";
import { updateNodes } from "@/utils/graph";

export interface PipelineGraphState {
  nodes: Node<ServiceData>[];
  edges: Edge[];
  isLoading: boolean;
  selectedServiceNode: Node<ServiceData> | null;
  isRenderable: boolean;
  isAutorefreshEnabled: boolean;
}

interface PipelineGraphSliceReducers
  // Matches RTK's own SliceCaseReducers constraint, which uses `any` here because
  // reducer payloads below are contravariant params with mismatched concrete types
  // (boolean, Node<ServiceData>[], void, ...) — neither `unknown` nor `never` typechecks.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  extends Record<string, CaseReducer<PipelineGraphState, PayloadAction<any>>> {
  onNodesChange: CaseReducer<
    PipelineGraphState,
    PayloadAction<NodeChange<Node<ServiceData>>[]>
  >;
  onEdgesChange: CaseReducer<
    PipelineGraphState,
    PayloadAction<EdgeChange<Edge>[]>
  >;
  onConnect: CaseReducer<PipelineGraphState, PayloadAction<Edge | Connection>>;
  setEdges: CaseReducer<
    PipelineGraphState,
    PayloadAction<FetchedServiceDetails>
  >;
  setNodes: CaseReducer<PipelineGraphState, PayloadAction<FetchedServicesData>>;
  setSelectedServiceNode: CaseReducer<
    PipelineGraphState,
    PayloadAction<Node<ServiceData>[]>
  >;
  setIsLoading: CaseReducer<PipelineGraphState, PayloadAction<boolean>>;
  setIsRenderable: CaseReducer<PipelineGraphState, PayloadAction<boolean>>;
  setIsAutorefreshEnabled: CaseReducer<
    PipelineGraphState,
    PayloadAction<boolean>
  >;
  resetSlice: CaseReducer<PipelineGraphState, PayloadAction<void>>;
}

export interface CreatePipelineGraphSliceResult {
  slice: Slice<PipelineGraphState, PipelineGraphSliceReducers, string>;
  reset: AsyncThunk<void, void, object>;
  setup: AsyncThunk<void, FetchedServicesData, object>;
}

const defaultFilterEdges = (
  edges: Edge[],
  details: FetchedServiceDetails,
): Edge[] => {
  const hasInputGuard = details.input_guard?.status !== undefined;
  return hasInputGuard
    ? edges.filter((edge) => edge.id !== "prompt_template-llm")
    : edges;
};

export interface CreatePipelineGraphSliceOptions {
  llmNodePositionNoGuards?: XYPosition;
  llmModelServerNodePositionNoGuards?: XYPosition;
  filterEdges?: (edges: Edge[], details: FetchedServiceDetails) => Edge[];
}

export function createPipelineGraphSlice(
  name: string,
  graphNodes: Node<ServiceData>[],
  graphEdges: Edge[],
  options: CreatePipelineGraphSliceOptions = {},
): CreatePipelineGraphSliceResult {
  const {
    llmNodePositionNoGuards,
    llmModelServerNodePositionNoGuards,
    filterEdges = defaultFilterEdges,
  } = options;

  const initialState: PipelineGraphState = {
    nodes: graphNodes,
    edges: [],
    isLoading: false,
    selectedServiceNode: null,
    isRenderable: false,
    isAutorefreshEnabled: false,
  };

  const slice = createSlice({
    name,
    initialState,
    reducers: {
      onNodesChange: (
        state,
        action: PayloadAction<NodeChange<Node<ServiceData>>[]>,
      ) => {
        const changes = action.payload;
        state.nodes = applyNodeChanges(changes, [
          ...state.nodes,
        ]) as typeof state.nodes;
      },
      onEdgesChange: (state, action: PayloadAction<EdgeChange<Edge>[]>) => {
        const changes = action.payload;
        state.edges = applyEdgeChanges(changes, state.edges as Edge[]);
      },
      onConnect: (state, action: PayloadAction<Edge | Connection>) => {
        const edgeParams = action.payload;
        state.edges = addEdge(edgeParams, state.edges);
      },
      setEdges: (state, action: PayloadAction<FetchedServiceDetails>) => {
        const details = action.payload;
        state.edges = filterEdges(graphEdges, details);
      },
      setNodes: (state, action: PayloadAction<FetchedServicesData>) => {
        const fetchedServicesData = action.payload;
        const newNodes = updateNodes(
          graphNodes,
          fetchedServicesData,
          llmNodePositionNoGuards,
          llmModelServerNodePositionNoGuards,
        ) as typeof state.nodes;

        if (state.selectedServiceNode) {
          const selectedId = state.selectedServiceNode.id;
          state.nodes = newNodes.map((node) =>
            node.id === selectedId
              ? {
                  ...node,
                  selected: true,
                  data: { ...node.data, selected: true },
                }
              : node,
          ) as typeof state.nodes;
        } else {
          state.nodes = newNodes;
        }
      },
      setSelectedServiceNode: (
        state,
        action: PayloadAction<Node<ServiceData>[]>,
      ) => {
        const nodes = action.payload;
        if (nodes.length) {
          const incomingNode = nodes[0] as typeof state.selectedServiceNode;
          if (incomingNode?.id !== state.selectedServiceNode?.id) {
            state.selectedServiceNode = incomingNode;
          }
          // same id: keep existing selectedServiceNode to preserve unsaved form state
        } else {
          state.selectedServiceNode = null;
        }
        const selectedId = state.selectedServiceNode?.id ?? null;
        state.nodes = [...state.nodes].map((node) => ({
          ...node,
          selected: selectedId ? node.id === selectedId : false,
          data: {
            ...node.data,
            selected: selectedId ? node.id === selectedId : false,
          },
        }));
      },
      setIsLoading: (state, action: PayloadAction<boolean>) => {
        state.isLoading = action.payload;
      },
      setIsRenderable: (state, action: PayloadAction<boolean>) => {
        state.isRenderable = action.payload;
      },
      setIsAutorefreshEnabled: (state, action: PayloadAction<boolean>) => {
        state.isAutorefreshEnabled = action.payload;
      },
      resetSlice: () => initialState,
    },
  });

  const reset = createAsyncThunk(`${name}/reset`, (_: void, { dispatch }) => {
    dispatch(slice.actions.setSelectedServiceNode([]));
    dispatch(slice.actions.setIsLoading(true));
  });

  const setup = createAsyncThunk(
    `${name}/setup`,
    ({ parameters, details }: FetchedServicesData, { dispatch }) => {
      dispatch(slice.actions.setNodes({ parameters, details }));
      dispatch(slice.actions.setEdges(details));
      dispatch(slice.actions.setIsRenderable(true));
    },
  );

  return { slice, reset, setup };
}
