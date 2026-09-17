// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { createS3Api } from "@intel-enterprise-rag-ui/data-ingestion";

import { getChatQnAAppEnv } from "@/utils";

export const { s3Api, usePostFileMutation, useDeleteFileMutation } =
  createS3Api(() => getChatQnAAppEnv("S3_SEND_BEARER_TOKEN"));
