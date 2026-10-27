import { cn } from "cn";
import * as React from "react";

function Textarea({
  className,
  size = "default",
  ...props
}: React.ComponentProps<"textarea"> & { size?: "sm" | "default" }) {
  return (
    <textarea
      data-slot="textarea"
      data-size={size}
      className={cn(
        "flex field-sizing-content w-full resize-none rounded-md border border-input bg-white text-sm transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/20 data-[size=default]:min-h-16 data-[size=default]:px-2.5 data-[size=default]:py-2 data-[size=sm]:min-h-12 data-[size=sm]:px-2 data-[size=sm]:py-1.5 dark:bg-black dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
