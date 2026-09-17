// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { ChangeArgumentsFunction } from "@/hooks/useServiceCard";
import { ServiceData } from "@/types/index";

export interface ControlPlaneCardProps {
  data: ServiceData;
  changeArguments: ChangeArgumentsFunction;
  isReadOnly?: boolean;
}
