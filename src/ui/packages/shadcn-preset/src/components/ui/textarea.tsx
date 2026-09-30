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
        "field-sizing-content border-input placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/30 aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/20 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 flex w-full resize-none rounded-md border bg-white text-sm outline-none transition-colors focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 data-[size=default]:min-h-16 data-[size=sm]:min-h-12 data-[size=default]:px-2.5 data-[size=default]:py-2 data-[size=sm]:px-2 data-[size=sm]:py-1.5 dark:bg-black",
        className,
      )}
      {...props}
    />
  );
}

export { Textarea };
