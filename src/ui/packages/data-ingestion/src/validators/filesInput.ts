// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import {
  getFilenameInvalidCharactersMsg,
  getUnsupportedFileExtensionMsg,
  getUnsupportedFileMIMETypeMsg,
  isFileExtensionSupported,
  isMIMETypeSupported,
  noInvalidCharactersInFileName,
} from "@intel-enterprise-rag-ui/input-validation";
import { z } from "zod";

import {
  SUPPORTED_FILE_EXTENSIONS_BASE,
  SUPPORTED_FILES_MIME_TYPES_BASE,
} from "@/utils/constants";

const validationSchema = z.array(
  z
    .instanceof(File)
    .refine(
      isFileExtensionSupported(SUPPORTED_FILE_EXTENSIONS_BASE),
      (file) => ({
        message: getUnsupportedFileExtensionMsg({ value: file }),
      }),
    )
    .refine(isMIMETypeSupported(SUPPORTED_FILES_MIME_TYPES_BASE), (file) => ({
      message: getUnsupportedFileMIMETypeMsg({ value: file }),
    }))
    .refine(noInvalidCharactersInFileName, (file) => ({
      message: getFilenameInvalidCharactersMsg({ value: file }),
    })),
);

export const validateFileInput = async (files: File[] | FileList) => {
  await validationSchema.parseAsync(Array.from(files));
};
