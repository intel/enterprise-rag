// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  FileDocIcon,
  FileDocxIcon,
  FileMdIcon,
  FilePdfIcon,
  FileTextIcon,
  PlainTextIcon,
} from "@intel-enterprise-rag-ui/icons";

import { HistoryItemData } from "@/features/docsum/types/history";

export const getFileIcon = (fileName: string) => {
  const fileExtension = fileName.split(".").pop()?.toLowerCase();
  if (fileExtension === "pdf") {
    return <FilePdfIcon />;
  } else if (fileExtension === "docx") {
    return <FileDocxIcon />;
  } else if (fileExtension === "doc") {
    return <FileDocIcon />;
  } else if (fileExtension === "md") {
    return <FileMdIcon />;
  } else {
    return <FileTextIcon />;
  }
};

export const getItemIcon = (itemData: HistoryItemData) => {
  if (itemData.sourceType === "file") {
    return getFileIcon(itemData.title);
  } else if (itemData.sourceType === "plainText") {
    return <PlainTextIcon />;
  } else {
    return null;
  }
};
