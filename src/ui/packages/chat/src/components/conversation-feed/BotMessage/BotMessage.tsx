// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./BotMessage.css";

import {
  Alert,
  AlertDescription,
  CopyButton,
} from "@intel-enterprise-rag-ui/components";
import { ErrorIcon } from "@intel-enterprise-rag-ui/icons";
import { Markdown } from "@intel-enterprise-rag-ui/markdown";
import { sanitizeString } from "@intel-enterprise-rag-ui/utils";
import classNames from "classnames";
import { memo } from "react";

import { AnimatedAiIcon } from "@/components/conversation-feed/AnimatedAiIcon/AnimatedAiIcon";
import {
  PlaySpeechButton,
  PlaySpeechButtonState,
} from "@/components/conversation-feed/PlaySpeechButton/PlaySpeechButton";
import { SourcesGrid } from "@/components/sources/SourcesGrid/SourcesGrid";
import { ChatTurn } from "@/types";

type BotMessageProps = Pick<
  ChatTurn,
  "id" | "answer" | "error" | "isPending" | "sources"
> & {
  playingState?: PlaySpeechButtonState;
  onFileDownload: (
    fileName: string,
    bucketName: string | null,
    siteName: string | null,
  ) => void;
  onPlayMessage?: (turnId: string) => Promise<void>;
};

const BotMessage = ({
  id,
  answer,
  error,
  isPending,
  sources,
  playingState = "idle",
  onFileDownload,
  onPlayMessage,
}: BotMessageProps) => {
  const isWaitingForAnswer = isPending && (answer === "" || error !== null);
  const sanitizedAnswer = sanitizeString(answer);
  const showActions = !isPending && (sanitizedAnswer !== "" || error !== null);
  const showSources = showActions && Array.isArray(sources);

  const botResponse =
    error !== null ? (
      <Alert variant="error" className="mt-1" data-testid="bot-message__error">
        <ErrorIcon />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    ) : (
      <div className="bot-message__text" data-testid="bot-message__text">
        <Markdown text={sanitizedAnswer} />
        {showActions && (
          <footer className="bot-message__footer">
            <CopyButton textToCopy={sanitizedAnswer} />
            {onPlayMessage && (
              <PlaySpeechButton
                turnId={id}
                playingState={playingState}
                onPlayMessage={onPlayMessage}
              />
            )}
          </footer>
        )}
        {showSources && (
          <SourcesGrid sources={sources} onFileDownload={onFileDownload} />
        )}
      </div>
    );

  const className = classNames("bot-message", {
    "bot-message--waiting": isWaitingForAnswer,
    "bot-message--completed": !isWaitingForAnswer,
  });

  return (
    <div className={className} data-testid={`bot-message-${id}`}>
      {isWaitingForAnswer ? (
        <div className="bot-message__waiting">
          <AnimatedAiIcon />
        </div>
      ) : (
        botResponse
      )}
    </div>
  );
};

export const MemoizedBotMessage = memo(BotMessage);
