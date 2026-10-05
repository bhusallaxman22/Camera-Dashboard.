"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { EVENTS_URL } from "./api";
import type { LiveMessage } from "./types";

type Listener = (msg: LiveMessage) => void;

interface LiveState {
  connected: boolean;
  lastMessage: LiveMessage | null;
  subscribe: (fn: Listener) => () => void;
}

const LiveContext = createContext<LiveState>({
  connected: false,
  lastMessage: null,
  subscribe: () => () => undefined,
});

function photoIds(data: Record<string, unknown>): string[] {
  const ids: string[] = [];
  if (typeof data.photo_id === "string") ids.push(data.photo_id);
  if (Array.isArray(data.photo_ids))
    ids.push(...data.photo_ids.filter((x): x is string => typeof x === "string"));
  return ids;
}

/**
 * One EventSource per tab. Incoming events invalidate the relevant TanStack
 * Query caches so every page updates without polling.
 */
export function LiveEventsProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<LiveMessage | null>(null);
  const listeners = useRef(new Set<Listener>());

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;

    const connect = () => {
      source = new EventSource(EVENTS_URL);
      source.addEventListener("hello", () => setConnected(true));
      source.onopen = () => setConnected(true);
      source.onerror = () => {
        setConnected(false);
        // EventSource reconnects on its own unless the server closed it hard.
        if (source?.readyState === EventSource.CLOSED && !closed) {
          retry = setTimeout(connect, 5000);
        }
      };
      source.onmessage = (ev) => {
        let msg: LiveMessage;
        try {
          msg = JSON.parse(ev.data) as LiveMessage;
        } catch {
          return;
        }
        setLastMessage(msg);
        const ids = photoIds(msg.data ?? {});
        switch (msg.type) {
          case "photo.created":
            qc.invalidateQueries({ queryKey: ["stats"] });
            qc.invalidateQueries({ queryKey: ["photos"] });
            qc.invalidateQueries({ queryKey: ["facets"] });
            break;
          case "photo.updated":
          case "photo.analyzed":
            qc.invalidateQueries({ queryKey: ["stats"] });
            qc.invalidateQueries({ queryKey: ["photos"] });
            for (const id of ids) qc.invalidateQueries({ queryKey: ["photo", id] });
            break;
          case "system.event":
            qc.invalidateQueries({ queryKey: ["events"] });
            break;
          case "job.updated":
            qc.invalidateQueries({ queryKey: ["jobs"] });
            qc.invalidateQueries({ queryKey: ["system"] });
            break;
        }
        for (const fn of listeners.current) fn(msg);
      };
    };

    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      source?.close();
    };
  }, [qc]);

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => {
      listeners.current.delete(fn);
    };
  }, []);

  const value = useMemo(() => ({ connected, lastMessage, subscribe }), [connected, lastMessage, subscribe]);
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive(): LiveState {
  return useContext(LiveContext);
}

export function useLiveListener(fn: Listener): void {
  const { subscribe } = useLive();
  const ref = useRef(fn);
  useEffect(() => {
    ref.current = fn;
  });
  useEffect(() => subscribe((m) => ref.current(m)), [subscribe]);
}
