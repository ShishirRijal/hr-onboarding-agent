"use client";

import Link from "next/link";
import { useAppState } from "@/lib/app-state";
import { officeLabel } from "@/lib/offices";
import { useSession } from "@/lib/session";
import { AccountFooter } from "./account";
import { PlusIcon } from "./icons";

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { sessions, sessionsLoaded, activeSessionId, resetNewChat } = useAppState();
  const { user } = useSession();

  return (
    <div className="flex min-h-0 w-full flex-col">
      <div className="px-5 pt-5 pb-4">
        <p className="text-xl leading-tight font-bold tracking-tight">NordTech HR</p>
        <p className="text-sm text-ink-soft">Onboarding and policy questions</p>
      </div>

      <div className="px-3">
        <Link
          href="/"
          onClick={() => {
            resetNewChat();
            onNavigate?.();
          }}
          className="flex items-center justify-center gap-2 rounded-full bg-brand px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-deep"
        >
          <PlusIcon className="size-4" />
          New chat
        </Link>
      </div>

      <nav aria-label="Recent chats" className="mt-6 min-h-0 flex-1 overflow-y-auto px-3">
        <h2 className="px-3 pb-2 text-sm font-semibold text-ink">Recent chats</h2>
        {sessions.length === 0 ? (
          <p className="px-3 text-sm text-ink-soft">{sessionsLoaded ? "Your chats will appear here." : "Loading…"}</p>
        ) : (
          <ul className="space-y-0.5">
            {sessions.map((session) => {
              const active = session.id === activeSessionId;
              const unread = session.unread > 0;
              return (
                <li key={session.id}>
                  <Link
                    href={`/c/${session.id}`}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-ink ${
                      active ? "bg-surface font-semibold shadow-[0_1px_3px_rgb(6_26_55/0.08)]" : "hover:bg-ink/5"
                    } ${unread ? "font-semibold" : ""}`}
                  >
                    <span className="min-w-0 flex-1 truncate">{session.title}</span>
                    {unread && (
                      <>
                        <span className="size-2 shrink-0 rounded-full bg-brand" aria-hidden="true" />
                        <span className="sr-only">(new reply from HR)</span>
                      </>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </nav>

      <AccountFooter detail={officeLabel(user)} profileHref="/profile" onNavigate={onNavigate}>
        {user.role === "hr" && (
          <Link
            href="/hr"
            className="block rounded-xl px-3 py-2 text-sm font-semibold text-brand hover:bg-ink/5"
          >
            Open the HR inbox
          </Link>
        )}
      </AccountFooter>
    </div>
  );
}
