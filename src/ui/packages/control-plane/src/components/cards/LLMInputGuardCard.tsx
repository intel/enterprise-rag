// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { GenericScannerInputs } from "@/components/GenericScannerInputs/GenericScannerInputs";
import { ScannersArgumentsTitle } from "@/components/ScannersArgumentsTitle/ScannersArgumentsTitle";
import { SelectedServiceCard } from "@/components/SelectedServiceCard/SelectedServiceCard";
import {
  LLMInputGuardArgs,
  llmInputGuardFormConfig,
} from "@/configs/guards/llmInputGuard";
import { useGuardServiceCard } from "@/hooks/useGuardServiceCard";
import { ControlPlaneCardProps } from "@/types/cards";

export const LLMInputGuardCard = ({
  data: { id, status, displayName, inputGuardArgs, details },
  changeArguments,
  isReadOnly = false,
}: ControlPlaneCardProps) => {
  const config = llmInputGuardFormConfig;

  const { argumentsForm, handlers, footerProps } =
    useGuardServiceCard<LLMInputGuardArgs>(id, inputGuardArgs, {
      changeArguments,
    });

  return (
    <SelectedServiceCard
      serviceStatus={status}
      serviceName={displayName}
      serviceDetails={details}
      footerProps={footerProps}
      isReadOnly={isReadOnly}
    >
      <ScannersArgumentsTitle>Scanners Arguments</ScannersArgumentsTitle>
      <GenericScannerInputs
        scannerId="prompt_injection"
        config={config.prompt_injection}
        previousArgumentsValues={argumentsForm.prompt_injection}
        handlers={handlers}
        isReadOnly={isReadOnly}
      />
      <GenericScannerInputs
        scannerId="ban_substrings"
        config={config.ban_substrings}
        previousArgumentsValues={argumentsForm.ban_substrings}
        handlers={handlers}
        isReadOnly={isReadOnly}
      />
      <GenericScannerInputs
        scannerId="code"
        config={config.code}
        previousArgumentsValues={argumentsForm.code}
        handlers={handlers}
        isReadOnly={isReadOnly}
      />
      <GenericScannerInputs
        scannerId="invisible_text"
        config={config.invisible_text}
        previousArgumentsValues={argumentsForm.invisible_text}
        handlers={handlers}
        isReadOnly={isReadOnly}
      />
      <GenericScannerInputs
        scannerId="regex"
        config={config.regex}
        previousArgumentsValues={argumentsForm.regex}
        handlers={handlers}
        isReadOnly={isReadOnly}
      />
      <GenericScannerInputs
        scannerId="ban_topics"
        config={config.ban_topics}
        previousArgumentsValues={argumentsForm.ban_topics}
        handlers={handlers}
        isReadOnly={isReadOnly}
      />
      <GenericScannerInputs
        scannerId="secrets"
        config={config.secrets}
        previousArgumentsValues={argumentsForm.secrets}
        handlers={handlers}
        isReadOnly={isReadOnly}
      />
      <GenericScannerInputs
        scannerId="sentiment"
        config={config.sentiment}
        previousArgumentsValues={argumentsForm.sentiment}
        handlers={handlers}
        isReadOnly={isReadOnly}
      />
      <GenericScannerInputs
        scannerId="token_limit"
        config={config.token_limit}
        previousArgumentsValues={argumentsForm.token_limit}
        handlers={handlers}
        isReadOnly={isReadOnly}
      />
      <GenericScannerInputs
        scannerId="toxicity"
        config={config.toxicity}
        previousArgumentsValues={argumentsForm.toxicity}
        handlers={handlers}
        isReadOnly={isReadOnly}
      />
    </SelectedServiceCard>
  );
};
