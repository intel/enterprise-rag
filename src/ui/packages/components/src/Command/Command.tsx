// Copyright (C) 2024-2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { SearchIcon } from "@intel-enterprise-rag-ui/icons";
import { cn } from "@intel-enterprise-rag-ui/utils";
import { Command as CommandPrimitive } from "cmdk";
import { ComponentProps } from "react";

export const Command = ({
  className,
  ...props
}: ComponentProps<typeof CommandPrimitive>) => (
  <CommandPrimitive
    className={cn(
      "flex h-full w-full flex-col text-popover-foreground outline-none",
      className,
    )}
    {...props}
  />
);

export const CommandInput = ({
  className,
  ...props
}: ComponentProps<typeof CommandPrimitive.Input>) => (
  <div className="flex items-center gap-2 border-b border-border px-2.5 py-1.5">
    <SearchIcon aria-hidden="true" className="size-3 text-muted-foreground" />
    <CommandPrimitive.Input
      className={cn(
        "w-full text-xs/relaxed outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  </div>
);

export const CommandList = ({
  className,
  ...props
}: ComponentProps<typeof CommandPrimitive.List>) => (
  <CommandPrimitive.List
    className={cn("max-h-64 overflow-x-hidden overflow-y-auto p-1", className)}
    {...props}
  />
);

export const CommandEmpty = (
  props: ComponentProps<typeof CommandPrimitive.Empty>,
) => (
  <CommandPrimitive.Empty
    className="py-4 text-center text-xs/relaxed"
    {...props}
  />
);

export const CommandGroup = ({
  className,
  ...props
}: ComponentProps<typeof CommandPrimitive.Group>) => (
  <CommandPrimitive.Group
    className={cn("overflow-hidden text-foreground", className)}
    {...props}
  />
);

export const CommandItem = ({
  className,
  ...props
}: ComponentProps<typeof CommandPrimitive.Item>) => (
  <CommandPrimitive.Item
    className={cn(
      "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-xs/relaxed outline-none select-none",
      "aria-disabled:pointer-events-none aria-disabled:opacity-50 data-[selected=true]:bg-secondary",
      className,
    )}
    {...props}
  />
);
