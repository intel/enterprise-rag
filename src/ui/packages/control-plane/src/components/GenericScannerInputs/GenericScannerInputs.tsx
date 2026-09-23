// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { ScannerInputsTitle } from "@/components/ScannerInputsTitle/ScannerInputsTitle";
import { ServiceArgumentCheckbox } from "@/components/ServiceArgumentCheckbox/ServiceArgumentCheckbox";
import { ServiceArgumentNumberInput } from "@/components/ServiceArgumentNumberInput/ServiceArgumentNumberInput";
import { ServiceArgumentSelectInput } from "@/components/ServiceArgumentSelectInput/ServiceArgumentSelectInput";
import { ServiceArgumentTextInput } from "@/components/ServiceArgumentTextInput/ServiceArgumentTextInput";
import {
  ScannerInputsProps,
  useGuardScannerInputs,
} from "@/hooks/useGuardScannerInputs";
import {
  OnArgumentValidityChangeHandler,
  OnArgumentValueChangeHandler,
  ServiceArgumentInputValue,
  ServiceArgumentNumberInputValue,
  ServiceArgumentTextInputValue,
} from "@/types/index";

interface ScannerArgumentFieldConfig {
  name: string;
  tooltipText?: string;
  isNullable?: boolean;
  range?: { min: number; max: number };
  options?: string[];
  isCommaSeparated?: boolean;
  supportedValues?: string[];
}

interface GenericScannerInputsProps<
  TArgs extends Record<string, ServiceArgumentInputValue>,
  TConfig extends Record<string, ScannerArgumentFieldConfig>,
> extends ScannerInputsProps<TArgs, TConfig> {
  scannerId: string;
}

const renderArgumentInput = (
  fieldName: string,
  fieldConfig: ScannerArgumentFieldConfig,
  value: ServiceArgumentInputValue,
  onArgumentValueChange: OnArgumentValueChangeHandler,
  onArgumentValidityChange: OnArgumentValidityChangeHandler,
  isReadOnly: boolean,
) => {
  if (fieldConfig.range) {
    return (
      <ServiceArgumentNumberInput
        key={fieldName}
        {...fieldConfig}
        range={fieldConfig.range}
        value={value as ServiceArgumentNumberInputValue}
        onArgumentValueChange={onArgumentValueChange}
        onArgumentValidityChange={onArgumentValidityChange}
        isDisabled={isReadOnly}
      />
    );
  }

  if (fieldConfig.options) {
    return (
      <ServiceArgumentSelectInput
        key={fieldName}
        {...fieldConfig}
        options={fieldConfig.options}
        value={value as string}
        onArgumentValueChange={onArgumentValueChange}
        isDisabled={isReadOnly}
      />
    );
  }

  if (fieldConfig.isCommaSeparated) {
    return (
      <ServiceArgumentTextInput
        key={fieldName}
        {...fieldConfig}
        value={value as ServiceArgumentTextInputValue}
        onArgumentValueChange={onArgumentValueChange}
        onArgumentValidityChange={onArgumentValidityChange}
        isDisabled={isReadOnly}
      />
    );
  }

  return (
    <ServiceArgumentCheckbox
      key={fieldName}
      {...fieldConfig}
      value={value as boolean}
      onArgumentValueChange={onArgumentValueChange}
      isDisabled={isReadOnly}
    />
  );
};

// Every scanner's inputs follow the same shape: a title, then one input per
// field declared in its config, dispatched by field shape (range -> number,
// options -> select, isCommaSeparated -> text, otherwise -> checkbox). The
// config in configs/guards/scanners.ts already encodes all field metadata per
// scanner, so a single generic renderer replaces all per-scanner components.
export const GenericScannerInputs = <
  TArgs extends Record<string, ServiceArgumentInputValue>,
  TConfig extends Record<string, ScannerArgumentFieldConfig>,
>({
  scannerId,
  previousArgumentsValues,
  config,
  handlers,
  isReadOnly = false,
}: GenericScannerInputsProps<TArgs, TConfig>) => {
  const {
    titleCasedName,
    handleArgumentValueChange,
    handleArgumentValidityChange,
  } = useGuardScannerInputs(scannerId, handlers);

  return (
    <>
      <ScannerInputsTitle>{titleCasedName}</ScannerInputsTitle>
      {Object.entries(config).map(([fieldName, fieldConfig]) =>
        renderArgumentInput(
          fieldName,
          fieldConfig,
          previousArgumentsValues[fieldName],
          handleArgumentValueChange,
          handleArgumentValidityChange,
          isReadOnly,
        ),
      )}
    </>
  );
};
