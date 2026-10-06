"use client";

import { Activity, Aperture, Images, LayoutDashboard } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useStats } from "@/lib/hooks";
import { useLive } from "@/lib/live";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/library", label: "Library", icon: Images },
  { href: "/system", label: "System", icon: Activity },
];

function isActive(href: string, pathname: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href) || (href === "/library" && pathname.startsWith("/photos"));
}

export function LiveDot() {
  const { connected } = useLive();
  return (
    <span
      className="text-ink-300 flex items-center gap-1.5 text-xs"
      title={connected ? "Live updates connected" : "Live updates disconnected — retrying"}
    >
      <span className={cn("size-2 rounded-full", connected ? "bg-ok" : "bg-bad")} />
      {connected ? "Live" : "Offline"}
    </span>
  );
}

function CameraPill({ session = false }: { session?: boolean }) {
  const { data } = useStats();
  const state = data?.camera.state ?? "never";
  const count = data?.camera.session_photos ?? 0;
  return (
    <div className="text-ink-300 flex min-w-0 items-center gap-2 text-xs">
      <span
        className={cn(
          "size-2 shrink-0 rounded-full",
          state === "receiving" ? "pulse-ring bg-ok" : state === "idle" ? "bg-ink-400" : "bg-ink-600",
        )}
      />
      <span className="truncate">
        <span className="text-ink-100">{data?.camera.camera ?? "Camera"}</span> ·{" "}
        <span className={cn(state === "receiving" && "text-ok")}>
          {state === "receiving" ? "receiving" : state === "idle" ? "idle" : "no uploads"}
        </span>
        {session && count > 0 && <span className="tabular"> · {count.toLocaleString()} this session</span>}
      </span>
    </div>
  );
}

function TabBar({ pathname }: { pathname: string }) {
  return (
    <nav
      aria-label="Primary"
      className="border-ink-800 bg-ink-950/95 pb-safe fixed inset-x-0 bottom-0 z-30 border-t backdrop-blur md:hidden"
    >
      <ul className="mx-auto grid max-w-md grid-cols-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = isActive(href, pathname);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-14 flex-col items-center justify-center gap-1 text-xs font-medium transition-colors",
                  active ? "text-accent" : "text-ink-300 active:text-ink-100",
                )}
              >
                <Icon className="size-5" strokeWidth={active ? 2.25 : 1.75} />
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  // The photo viewer brings its own back button and culling bar on phones.
  const immersive = pathname.startsWith("/photos/");
  return (
    <div className="flex min-h-svh">
      <aside className="border-ink-800 bg-ink-900/60 sticky top-0 hidden h-svh w-56 shrink-0 flex-col border-r md:flex">
        <Link href="/" className="flex items-center gap-2.5 px-5 pt-5 pb-6">
          <span className="bg-accent text-ink-950 grid size-8 place-items-center rounded-lg">
            <Aperture className="size-5" strokeWidth={2.25} />
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-semibold tracking-tight">Z6III AI Studio</span>
            <span className="text-ink-300 block text-xs">Nikon photography workflow</span>
          </span>
        </Link>
        <nav aria-label="Primary" className="flex flex-col gap-0.5 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = isActive(href, pathname);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
                  active ? "bg-ink-800 text-ink-100" : "text-ink-300 hover:bg-ink-850 hover:text-ink-100",
                )}
              >
                <Icon className={cn("size-4", active && "text-accent")} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="border-ink-800 mt-auto space-y-2 border-t px-5 py-4">
          <CameraPill />
          <LiveDot />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {!immersive && (
          <header className="border-ink-800 bg-ink-950/90 pt-safe sticky top-0 z-30 border-b backdrop-blur md:hidden">
            <div className="flex h-12 items-center justify-between gap-3 px-4">
              <Link href="/" className="-m-2 flex min-w-0 items-center gap-2.5 p-2">
                <Aperture className="text-accent size-5 shrink-0" aria-hidden />
                <span className="sr-only">Z6III AI Studio dashboard, camera status:</span>
                <CameraPill session />
              </Link>
              <LiveDot />
            </div>
          </header>
        )}
        <main
          className={cn(
            "min-w-0 flex-1",
            !immersive && "pb-[calc(3.5rem+env(safe-area-inset-bottom))] md:pb-0",
          )}
        >
          {children}
        </main>
      </div>

      {!immersive && <TabBar pathname={pathname} />}
    </div>
  );
}
