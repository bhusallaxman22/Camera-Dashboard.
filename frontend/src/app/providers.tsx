"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";
import { LiveEventsProvider } from "@/lib/live";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 10_000,
            refetchOnWindowFocus: true,
            retry: (count, err) => count < 2 && !(err instanceof ApiError && err.status < 500),
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <LiveEventsProvider>{children}</LiveEventsProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
