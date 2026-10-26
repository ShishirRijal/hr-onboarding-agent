"use client";

import Link from "next/link";
import { useAppState } from "@/lib/app-state";
import { OFFICES } from "@/lib/offices";
import { PlusIcon } from "./icons";

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { sessions, activeSessionId, office, setOffice, resetNewChat } = useAppState();

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
          <p className="px-3 text-sm text-ink-soft">Your chats will appear here.</p>
        ) : (
          <ul className="space-y-0.5">
            {sessions.map((session) => {
              const active = session.id === activeSessionId;
              return (
                <li key={session.id}>
                  <Link
                    href={`/c/${session.id}`}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={`block truncate rounded-xl px-3 py-2 text-sm text-ink ${
                      active ? "bg-surface font-semibold shadow-[0_1px_3px_rgb(6_26_55/0.08)]" : "hover:bg-ink/5"
                    }`}
                  >
                    {session.title}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </nav>

      <div className="px-5 py-4">
        <label htmlFor="office" className="text-sm font-semibold">
          Your office
        </label>
        <select
          id="office"
          value={office.id}
          onChange={(event) => setOffice(event.target.value)}
          className="mt-1.5 w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm"
        >
          {OFFICES.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
        
      </div>
    </div>
  );
}
