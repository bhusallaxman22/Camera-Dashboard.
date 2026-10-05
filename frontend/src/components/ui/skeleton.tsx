import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("bg-ink-800 animate-pulse rounded-md", className)} />;
}
