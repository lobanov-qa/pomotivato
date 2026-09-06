import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef } from "react";
import { cn } from "../../lib/utils";

/**
 * Button primitive (shadcn-shaped, hand-rolled: a full shadcn init would
 * add radix deps we do not use yet — kanban needs buttons, not dialogs).
 * Visual bar: modern minimal — rounded-lg, subtle shadow on secondary,
 * ring focus, disabled fade. The dial PR reuses these variants.
 */

const button = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg text-sm font-medium transition-all outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 active:scale-[0.98]",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow hover:bg-primary/90",
        secondary: "bg-muted text-foreground shadow-xs hover:bg-muted/70",
        ghost: "hover:bg-muted text-foreground",
        danger: "bg-transparent text-danger border border-danger/30 hover:bg-danger/10",
        outline: "border border-input bg-card shadow-xs hover:bg-muted",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof button> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, type = "button", ...props }, ref) => (
    <button ref={ref} type={type} className={cn(button({ variant, size }), className)} {...props} />
  ),
);
Button.displayName = "Button";
