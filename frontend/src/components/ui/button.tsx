"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils/cn";

/**
 * Restrained, Claude-inspired controls: no heavy fills on secondary actions, no
 * strong shadows, and a single warm accent reserved for primary intent.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium transition-colors outline-none disabled:pointer-events-none disabled:opacity-40 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "rounded-lg bg-accent text-accent-contrast hover:bg-accent-hover",
        secondary:
          "rounded-lg border border-border bg-surface-raised text-foreground hover:bg-surface-hover",
        ghost: "rounded-lg text-muted-strong hover:bg-surface-hover hover:text-foreground",
        link: "text-accent underline-offset-4 hover:underline",
        danger:
          "rounded-lg border border-danger/30 bg-danger-soft text-danger hover:bg-danger/10",
      },
      size: {
        default: "h-9 px-3.5",
        sm: "h-8 px-2.5 text-[13px]",
        lg: "h-10 px-5",
        icon: "size-9 rounded-lg",
        "icon-sm": "size-7 rounded-md",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot : "button";

  return (
    <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
}

export { buttonVariants };
