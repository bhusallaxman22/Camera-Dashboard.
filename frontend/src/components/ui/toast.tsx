"use client";

import { CheckCircle2, CircleAlert, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type ToastTone = "info" | "ok" | "error";
interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
}

const ToastContext = createContext<(message: string, tone?: ToastTone) => void>(() => undefined);

let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const push = useCallback(
    (message: string, tone: ToastTone = "info") => {
      const id = nextId++;
      setToasts((t) => [...t.slice(-3), { id, tone, message }]);
      setTimeout(() => dismiss(id), tone === "error" ? 7000 : 3500);
    },
    [dismiss],
  );
  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-80 flex-col gap-2"
        aria-live="polite"
      >
        {toasts.map((t) => {
          const Icon = t.tone === "ok" ? CheckCircle2 : t.tone === "error" ? CircleAlert : Info;
          return (
            <div
              key={t.id}
              role="status"
              className={cn(
                "animate-fade-in bg-ink-850/95 pointer-events-auto flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-sm shadow-xl backdrop-blur",
                t.tone === "error" ? "border-bad/40" : t.tone === "ok" ? "border-ok/30" : "border-ink-700",
              )}
            >
              <Icon
                className={cn(
                  "mt-0.5 size-4 shrink-0",
                  t.tone === "error" ? "text-bad" : t.tone === "ok" ? "text-ok" : "text-info",
                )}
              />
              <span className="text-ink-200 flex-1">{t.message}</span>
              <button
                onClick={() => dismiss(t.id)}
                className="text-ink-500 hover:text-ink-200"
                aria-label="Dismiss"
              >
                <X className="size-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
