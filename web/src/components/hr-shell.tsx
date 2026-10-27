"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fetchHrOverview } from "@/lib/api";
import { useSession } from "@/lib/session";
import type { HrOverview } from "@/lib/types";
import { AccountFooter } from "./account";
import { AppShell } from "./app-shell";

// New questions can come in at any time, so the overview is checked again on focus and every minute.
const REFRESH_MS = 60_000;

type HrState = {
  overview: HrOverview | null;
  overviewError: boolean;
  refreshOverview: () => void;
};

const HrStateContext = createContext<HrState | null>(null);

export function useHrState(): HrState {
  const state = useContext(HrStateContext);
  if (!state) throw new Error("useHrState must be used inside HrShell.");
  return state;
}

export function HrShell({ children }: { children: React.ReactNode }) {
  const [overview, setOverview] = useState<HrOverview | null>(null);
  const [overviewError, setOverviewError] = useState(false);

  const refreshOverview = useCallback(() => {
    fetchHrOverview()
      .then((next) => {
        setOverview(next);
        setOverviewError(false);
      })
      .catch(() => setOverviewError(true));
  }, []);

  useEffect(() => {
    refreshOverview();
    const timer = setInterval(refreshOverview, REFRESH_MS);
    window.addEventListener("focus", refreshOverview);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refreshOverview);
    };
  }, [refreshOverview]);

  const value = useMemo(() => ({ overview, overviewError, refreshOverview }), [overview, overviewError, refreshOverview]);

  return (
    <HrStateContext value={value}>
      <AppShell menuLabel="Open menu" sidebar={(onNavigate) => <HrSidebar onNavigate={onNavigate} />}>
        {children}
      </AppShell>
    </HrStateContext>
  );
}

function HrSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useSession();
  const { overview } = useHrState();
  const pathname = usePathname();
  const open = overview?.open_questions ?? 0;
  const links = [
    { href: "/hr", label: "Inbox", current: pathname === "/hr" || pathname.startsWith("/hr/q/"), count: open, unit: "open" },
    { href: "/hr/answered", label: "Answered", current: pathname === "/hr/answered", count: 0, unit: "" },
    {
      href: "/hr/review",
      label: "Answer review",
      current: pathname.startsWith("/hr/review"),
      count: overview?.unhelpful_to_review ?? 0,
      unit: "marked unhelpful",
    },
    { href: "/hr/usage", label: "Usage", current: pathname === "/hr/usage", count: 0, unit: "" },
  ];

  return (
    <div className="flex min-h-0 w-full flex-col">
      <div className="px-5 pt-5 pb-4">
        <p className="text-xl leading-tight font-bold tracking-tight">NordTech HR</p>
        <p className="text-sm text-ink-soft">HR platform</p>
      </div>

      <nav aria-label="HR platform" className="min-h-0 flex-1 overflow-y-auto px-3">
        <ul className="space-y-0.5">
          {links.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                onClick={onNavigate}
                aria-current={link.current ? "page" : undefined}
                className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-ink ${
                  link.current ? "bg-surface font-semibold shadow-[0_1px_3px_rgb(6_26_55/0.08)]" : "hover:bg-ink/5"
                }`}
              >
                <span className="flex-1">{link.label}</span>
                {link.count > 0 && (
                  <span className="rounded-full bg-lamp-wash px-2 py-0.5 text-xs font-semibold text-lamp tabular-nums">
                    {link.count}
                    <span className="sr-only"> {link.unit}</span>
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <AccountFooter detail={user.job_title}>
        <Link
          href="/"
          onClick={onNavigate}
          className="block rounded-xl px-3 py-2 text-sm font-semibold text-brand hover:bg-ink/5"
        >
          Try the assistant
        </Link>
      </AccountFooter>
    </div>
  );
}
