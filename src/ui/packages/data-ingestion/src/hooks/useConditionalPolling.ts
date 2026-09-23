// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef } from "react";
import { useSelector } from "react-redux";

import { POLLING_END_STATUSES, POLLING_INTERVAL } from "@/config/api";
import { DataIngestionSettingsState } from "@/store/dataIngestionSettings.slice";
import { FileDataItem, LinkDataItem } from "@/types";

const isDataIngestionInProgress = (
  data: FileDataItem[] | LinkDataItem[] | undefined,
) =>
  data?.some(({ status }) => !POLLING_END_STATUSES.includes(status)) ?? false;

const useConditionalPolling = (
  data: FileDataItem[] | LinkDataItem[] | undefined,
  refetch: () => void,
  selectIsAutorefreshEnabled: (state: {
    dataIngestionSettings: DataIngestionSettingsState;
  }) => boolean,
) => {
  const isAutorefreshEnabled = useSelector(selectIsAutorefreshEnabled);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearPollingInterval = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  useEffect(() => {
    if (isAutorefreshEnabled && isDataIngestionInProgress(data)) {
      if (!intervalRef.current) {
        intervalRef.current = setInterval(() => {
          refetch();
        }, POLLING_INTERVAL);
      }
    } else {
      if (intervalRef.current) {
        clearPollingInterval();
      }
    }

    return () => {
      clearPollingInterval();
    };
  }, [data, refetch, isAutorefreshEnabled]);
};

export default useConditionalPolling;
