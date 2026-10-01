// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import "./AnchorCard.css";

import {
  ExternalLinkIcon,
  IconName,
  icons,
} from "@intel-enterprise-rag-ui/icons";
import { cn, isSafeHref, sanitizeHref } from "@intel-enterprise-rag-ui/utils";
import { AnchorHTMLAttributes, MouseEvent } from "react";

interface AnchorCardProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  /** Text to display in the anchor card */
  text: string;
  /** Name of the icon to display */
  icon?: IconName;
  /** If true, additional icon for indicating external links is displayed */
  isExternal?: boolean;
  /** Callback fired when the anchor card is pressed */
  onPress?: (event: MouseEvent<HTMLAnchorElement>) => void;
}

/**
 * Anchor component for rendering a styled link in the form of the card with optional icon and external indication.
 */
export const AnchorCard = ({
  text,
  icon,
  isExternal,
  href,
  target = "_blank",
  className,
  onPress,
  ...rest
}: AnchorCardProps) => {
  const isSafe = isSafeHref(href);
  const safeHref = isSafe ? sanitizeHref(href) : undefined;
  const rel = target === "_blank" ? "noopener noreferrer" : undefined;

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (onPress && isSafe) {
      onPress(event);
    }
  };

  const IconComponent = icon ? icons[icon] : null;

  return (
    <a
      {...rest}
      href={safeHref}
      target={target}
      rel={rel}
      className={cn("anchor-card", !isSafe && "invalid", className)}
      aria-disabled={!isSafe}
      onClick={handleClick}
    >
      <span className="anchor-card__content">
        {IconComponent ? <IconComponent /> : null}
        <p className="anchor-card__text">
          {!isSafe && "Caution: Malicious link - "}
          {text}
        </p>
        {isExternal && <ExternalLinkIcon fontSize={12} />}
      </span>
    </a>
  );
};
