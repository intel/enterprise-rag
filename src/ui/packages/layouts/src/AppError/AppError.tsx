// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./AppError.css";

import {
  Anchor,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@intel-enterprise-rag-ui/components";
import { ErrorIcon, WarningIcon } from "@intel-enterprise-rag-ui/icons";

export interface AppErrorProps {
  /** HTTP-style status code, when known (e.g. 404). Omit for a non-route-response error. */
  status?: number;
  /** Server-provided status text / error detail, shown for non-404 errors. */
  statusText?: string;
  /** Path the "Return to the app" link navigates to, e.g. `paths.chat` or `paths.docsum`. */
  homePath: string;
  /** Label for the return link. */
  homeLabel?: string;
}

/**
 * Shared application-error surface for route-level errors (404s and runtime errors), used by every
 * app's `errorElement`/`ErrorRoute` instead of each app duplicating its own plain-text markup.
 */
export const AppError = ({
  status,
  statusText,
  homePath,
  homeLabel = "Return to the app",
}: AppErrorProps) => {
  const isNotFound = status === 404;

  return (
    <div className="app-error" data-testid="app-error">
      <Card className="app-error__card">
        <CardHeader>
          {isNotFound ? (
            <WarningIcon className="app-error__icon" />
          ) : (
            <ErrorIcon className="app-error__icon app-error__icon--destructive" />
          )}
          <CardTitle>
            {isNotFound ? "Page not found" : "Something went wrong"}
          </CardTitle>
          <CardDescription>
            {isNotFound
              ? "The page you're looking for doesn't exist or may have been moved."
              : "An unexpected error occurred while loading this page."}
          </CardDescription>
        </CardHeader>
        {!isNotFound && status !== undefined && (
          <CardContent>
            <p className="app-error__detail">
              Error code: {status}
              {statusText && <> — {statusText}</>}
            </p>
          </CardContent>
        )}
        <CardFooter>
          <Anchor href={homePath} target="_self">
            {homeLabel}
          </Anchor>
        </CardFooter>
      </Card>
    </div>
  );
};
