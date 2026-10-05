import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function StatTile({
  label,
  value,
  hint,
  icon,
  className,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("border-ink-800 bg-ink-900/80 rounded-xl border px-4 py-3", className)}>
      <div className="text-ink-500 flex items-center justify-between text-[10px] font-semibold tracking-[0.14em] uppercase">
        {label}
        {icon}
      </div>
      <div className="text-ink-100 tabular mt-1 text-2xl font-semibold">{value}</div>
      {hint && <div className="text-ink-400 text-[11px]">{hint}</div>}
    </div>
  );
}
