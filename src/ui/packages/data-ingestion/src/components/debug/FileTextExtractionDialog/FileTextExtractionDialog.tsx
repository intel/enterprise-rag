// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { usePostFileToExtractTextMutation } from "@/api/edpApi";
import TextExtractionDialog from "@/components/debug/TextExtractionDialog/TextExtractionDialog";
import { ERROR_MESSAGES } from "@/config/api";
import useTextExtraction from "@/hooks/debug/useTextExtraction";

interface FileTextExtractionDialogProps {
  uuid: string;
  fileName: string;
}

const FileTextExtractionDialog = ({
  uuid,
  fileName,
}: FileTextExtractionDialogProps) => {
  const {
    extractedText,
    isLoading,
    errorMessage,
    onTriggerPress,
    onFormSubmit,
  } = useTextExtraction(
    usePostFileToExtractTextMutation,
    ERROR_MESSAGES.POST_FILE_TO_EXTRACT_TEXT,
    uuid,
  );

  return (
    <TextExtractionDialog
      objectName={fileName}
      extractedText={extractedText}
      isLoading={isLoading}
      errorMessage={errorMessage}
      onFormSubmit={onFormSubmit}
      onTriggerPress={onTriggerPress}
    />
  );
};

export default FileTextExtractionDialog;
