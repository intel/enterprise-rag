// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

export interface ServiceArgumentFieldConfig {
  name: string;
  tooltipText?: string;
}

export interface ServiceArgumentNumberFieldConfig extends ServiceArgumentFieldConfig {
  range: { min: number; max: number };
}

// Boolean-valued fields (e.g. checkboxes) carry no range; every other
// supported value type renders as a number input and requires one.
export type ServiceFormFieldConfig<TValue> = TValue extends boolean
  ? ServiceArgumentFieldConfig
  : ServiceArgumentNumberFieldConfig;

export type ServiceFormConfig<TArgs> = {
  [K in keyof TArgs]: ServiceFormFieldConfig<TArgs[K]>;
};
