import { forwardRef, type InputHTMLAttributes, type SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const FIELD =
  "h-9 w-full rounded-md border border-ink-700 bg-ink-850 px-2.5 text-base text-ink-100 placeholder:text-ink-400 focus:border-accent/60 focus:outline-none sm:text-sm pointer-coarse:h-11";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...props },
  ref,
) {
  return <input ref={ref} className={cn(FIELD, className)} {...props} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, ...props },
  ref,
) {
  return <select ref={ref} className={cn(FIELD, "pr-7", className)} {...props} />;
});

export function Label({ children, htmlFor }: { children: React.ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className="text-ink-300 mb-1 block text-xs font-medium">
      {children}
    </label>
  );
}
