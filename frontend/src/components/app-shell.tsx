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

export function LiveDot() {
  const { connected } = useLive();
  return (
    <span
      className="text-ink-400 flex items-center gap-1.5 text-[11px]"
      title={connected ? "Live updates connected" : "Live updates disconnected — retrying"}
    >
      <span className={cn("size-2 rounded-full", connected ? "bg-ok" : "bg-bad")} />
      {connected ? "Live" : "Offline"}
    </span>
  );
}

function CameraPill() {
  const { data } = useStats();
  const state = data?.camera.state ?? "never";
  return (
    <div className="text-ink-400 flex items-center gap-2 text-[11px]">
      <span
        className={cn(
          "size-2 rounded-full",
          state === "receiving" ? "pulse-ring bg-ok" : state === "idle" ? "bg-ink-500" : "bg-ink-700",
        )}
      />
      <span className="truncate">
        {data?.camera.camera ?? "Camera"} ·{" "}
        {state === "receiving" ? "receiving" : state === "idle" ? "idle" : "no uploads"}
      </span>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-screen">
      <aside className="border-ink-800 bg-ink-900/60 sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r md:flex">
        <Link href="/" className="flex items-center gap-2.5 px-5 pt-5 pb-6">
          <span className="bg-accent text-ink-950 grid size-8 place-items-center rounded-lg">
            <Aperture className="size-5" strokeWidth={2.25} />
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-semibold tracking-tight">Z6III AI Studio</span>
            <span className="text-ink-400 block text-[10px]">Nikon photography workflow</span>
          </span>
        </Link>
        <nav className="flex flex-col gap-0.5 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/"
                ? pathname === "/"
                : pathname.startsWith(href) || (href === "/library" && pathname.startsWith("/photos"));
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
                  active ? "bg-ink-800 text-ink-100" : "text-ink-400 hover:bg-ink-850 hover:text-ink-200",
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
        <header className="border-ink-800 bg-ink-950/90 sticky top-0 z-30 flex items-center justify-between border-b px-4 py-2.5 backdrop-blur md:hidden">
          <Link href="/" className="flex items-center gap-2 text-sm font-semibold">
            <Aperture className="text-accent size-5" /> Z6III AI Studio
          </Link>
          <nav className="flex items-center gap-1">
            {NAV.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                aria-label={label}
                className={cn("rounded-md p-2", pathname === href ? "text-accent" : "text-ink-400")}
              >
                <Icon className="size-4" />
              </Link>
            ))}
            <LiveDot />
          </nav>
        </header>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
