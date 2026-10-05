import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "default" | "primary" | "ghost" | "outline" | "danger";
type Size = "sm" | "md" | "icon";

const VARIANTS: Record<Variant, string> = {
  default: "bg-ink-700 text-ink-100 hover:bg-ink-600",
  primary: "bg-accent text-ink-950 hover:brightness-110 font-semibold",
  ghost: "text-ink-300 hover:bg-ink-800 hover:text-ink-100",
  outline: "border border-ink-600 text-ink-200 hover:border-ink-400 hover:text-ink-100",
  danger: "bg-bad/15 text-bad hover:bg-bad/25",
};

const SIZES: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs gap-1.5",
  md: "h-9 px-3.5 text-sm gap-2",
  icon: "h-8 w-8 justify-center",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  active?: boolean;
}

export function buttonClass({
  variant = "default",
  size = "md",
  active,
  className,
}: { variant?: Variant; size?: Size; active?: boolean; className?: string } = {}): string {
  return cn(
    "inline-flex shrink-0 items-center rounded-md font-medium whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-40",
    VARIANTS[variant],
    SIZES[size],
    active && "bg-accent-soft text-accent ring-1 ring-accent/40",
    className,
  );
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, active, type = "button", ...props },
  ref,
) {
  return (
    <button ref={ref} type={type} className={buttonClass({ variant, size, active, className })} {...props} />
  );
});
