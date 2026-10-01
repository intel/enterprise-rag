// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./ChunksProgress.css";

import { Progress } from "@intel-enterprise-rag-ui/components";
import { memo } from "react";

interface ChunksProgressProps {
  processedChunks: number;
  totalChunks: number;
}

const ChunksProgress = memo(
  ({ processedChunks, totalChunks }: ChunksProgressProps) => {
    const percentValue =
      totalChunks > 0 ? Math.round((processedChunks / totalChunks) * 100) : 0;

    return (
      <div className="chunks-progress-bar">
        <Progress
          data-testid="chunks-progress-bar"
          value={processedChunks}
          maxValue={totalChunks}
          aria-label="Processed Chunks"
        />
        <p className="chunks-progress-bar__count">
          {processedChunks}&nbsp;/&nbsp;{totalChunks}&nbsp;({percentValue}%)
        </p>
      </div>
    );
  },
);

ChunksProgress.displayName = "ChunksProgress";

export default ChunksProgress;
