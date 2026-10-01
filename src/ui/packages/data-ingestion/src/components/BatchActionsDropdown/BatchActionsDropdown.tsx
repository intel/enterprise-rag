// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./BatchActionsDropdown.css";

import {
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@intel-enterprise-rag-ui/components";
import { DeleteIcon, RefreshIcon } from "@intel-enterprise-rag-ui/icons";

interface BatchActionsDropdownProps {
  /** Total number of selected items */
  selectedCount: number;
  /** Number of items in error state that can be retried */
  retryableCount: number;
  /** Number of items that need re-ingestion due to embedding model change */
  reingestableCount?: number;
  /** Callback when retry action is clicked */
  onRetry: () => void;
  /** Callback when delete action is clicked */
  onDelete: () => void;
  /** Callback when reingest action is clicked */
  onReingest?: () => void;
  /** Whether the dropdown is disabled */
  isDisabled?: boolean;
}

const BatchActionsDropdown = ({
  selectedCount,
  retryableCount,
  reingestableCount = 0,
  onRetry,
  onDelete,
  onReingest,
  isDisabled = false,
}: BatchActionsDropdownProps) => {
  const isActionsDisabled = isDisabled || selectedCount === 0;
  const isRetryDisabled = retryableCount === 0;
  const isReingestDisabled = reingestableCount === 0;

  return (
    <DropdownMenuTrigger
      trigger={
        <Button
          data-testid="batch-actions-button"
          isDisabled={isActionsDisabled}
        >
          Actions{selectedCount > 0 ? ` (${selectedCount})` : ""}
        </Button>
      }
      ariaLabel="Batch Actions Menu"
      placement="bottom end"
    >
      <DropdownMenu
        className="batch-actions-menu"
        onAction={(key) => {
          if (key === "retry") onRetry();
          if (key === "reingest" && onReingest) onReingest();
          if (key === "delete") onDelete();
        }}
      >
        <DropdownMenuItem
          id="retry"
          className={`batch-actions-menu__item ${isRetryDisabled ? "batch-actions-menu__item--disabled" : ""}`}
          isDisabled={isRetryDisabled}
        >
          <RefreshIcon className="batch-actions-menu__icon" />
          <span>Retry{retryableCount > 0 ? ` (${retryableCount})` : ""}</span>
        </DropdownMenuItem>
        {reingestableCount > 0 && onReingest && (
          <DropdownMenuItem
            id="reingest"
            className={`batch-actions-menu__item ${isReingestDisabled ? "batch-actions-menu__item--disabled" : ""}`}
            isDisabled={isReingestDisabled}
          >
            <RefreshIcon className="batch-actions-menu__icon" />
            <span>Reingest ({reingestableCount})</span>
          </DropdownMenuItem>
        )}
        <DropdownMenuItem
          id="delete"
          className="batch-actions-menu__item batch-actions-menu__item--delete"
        >
          <DeleteIcon className="batch-actions-menu__icon" />
          <span>Delete ({selectedCount})</span>
        </DropdownMenuItem>
      </DropdownMenu>
    </DropdownMenuTrigger>
  );
};

export default BatchActionsDropdown;
