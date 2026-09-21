import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-peri-300 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 min-h-10",
  {
    variants: {
      variant: {
        default: "bg-sage-700 text-white hover:bg-sage-900",
        outline: "border border-sage-700 text-sage-700 hover:bg-sage-100",
        ghost: "text-slate-700 underline-offset-4 hover:underline hover:text-ink",
        secondary: "bg-sage-100 text-sage-900 hover:bg-sage-200",
        destructive: "bg-error text-white hover:opacity-90",
      },
      size: {
        default: "px-5 py-2.5",
        sm: "px-3.5 py-1.5 text-xs",
        lg: "px-6 py-3 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = "Button";
