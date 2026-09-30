// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./FileSelectedToSummarize.css";

import { Button } from "@intel-enterprise-rag-ui/components";
import { useMemo } from "react";

import { getFileIcon } from "@/features/docsum/utils/render";

interface FileSelectedToSummarizeProps {
  fileName: string;
  isGeneratingSummary: boolean;
  onChangeFile: () => void;
  onDeleteFile: () => void;
}

const FileSelectedToSummarize = ({
  fileName,
  isGeneratingSummary,
  onChangeFile,
  onDeleteFile,
}: FileSelectedToSummarizeProps) => {
  const icon = useMemo(() => getFileIcon(fileName), [fileName]);

  return (
    <div
      className="file-selected-to-summarize"
      data-testid="file-selected-to-summarize"
    >
      <span className="file-selected-to-summarize__icon">{icon}</span>
      <p className="file-selected-to-summarize__filename">{fileName}</p>
      <div className="file-selected-to-summarize__actions">
        <Button
          data-testid="change-file-button"
          size="sm"
          variant="outline"
          isDisabled={isGeneratingSummary}
          onPress={onChangeFile}
        >
          Change
        </Button>
        <Button
          data-testid="delete-file-button"
          variant="destructive"
          size="sm"
          isDisabled={isGeneratingSummary}
          onPress={onDeleteFile}
        >
          Delete
        </Button>
      </div>
    </div>
  );
};

export default FileSelectedToSummarize;
