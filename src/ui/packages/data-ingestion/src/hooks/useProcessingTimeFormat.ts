// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Duration } from "luxon";
import { useDispatch, useSelector } from "react-redux";

import {
  ProcessingTimeFormat,
  selectProcessingTimeFormat,
  setProcessingTimeFormat,
} from "@/store/dataIngestionSettings.slice";

const formatStandard = (ms: number) => {
  const duration = Duration.fromMillis(ms);
  return duration.toFormat("hh:mm:ss.SSS");
};

const formatCompact = (ms: number) => {
  const duration = Duration.fromMillis(ms).rescale().toObject();
  const parts = [];

  if (duration.hours && duration.hours > 0) parts.push(`${duration.hours}h`);
  if (duration.minutes && duration.minutes > 0)
    parts.push(`${duration.minutes}m`);
  parts.push(`${duration.seconds ?? 0}s`);

  return parts.join(" ");
};

const useProcessingTimeFormat = () => {
  const processingTimeFormat = useSelector(selectProcessingTimeFormat);
  const dispatch = useDispatch();

  const formatFn =
    processingTimeFormat === "standard" ? formatStandard : formatCompact;

  const setFormat = (format: ProcessingTimeFormat) => {
    dispatch(setProcessingTimeFormat(format));
  };

  return {
    processingTimeFormat,
    formatProcessingTime: formatFn,
    setFormat,
  };
};

export default useProcessingTimeFormat;
