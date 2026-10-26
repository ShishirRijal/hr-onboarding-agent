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
        <p className="text-lg leading-tight font-semibold tracking-tight">NordTech HR</p>
        <p className="text-sm text-ink-soft">Onboarding and policy questions</p>
      </div>

      <div className="px-3">
        <Link
          href="/"
          onClick={() => {
            resetNewChat();
            onNavigate?.();
          }}
          className="flex items-center gap-2 rounded-lg border border-birch px-3 py-2 text-sm font-medium hover:border-baltic hover:text-baltic"
        >
          <PlusIcon className="size-4" />
          New chat
        </Link>
      </div>

      <nav aria-label="Recent chats" className="mt-6 min-h-0 flex-1 overflow-y-auto px-3">
        <h2 className="px-2 pb-2 text-sm text-ink-soft">Recent chats</h2>
        {sessions.length === 0 ? (
          <p className="px-2 text-sm text-ink-faint">Your chats will appear here.</p>
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
                    className={`block truncate rounded-md px-2 py-1.5 text-sm ${
                      active ? "bg-baltic-wash font-medium text-baltic-deep" : "text-ink hover:bg-ice"
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

      <div className="border-t border-birch px-5 py-4">
        <label htmlFor="office" className="text-sm font-medium">
          Your office
        </label>
        <select
          id="office"
          value={office.id}
          onChange={(event) => setOffice(event.target.value)}
          className="mt-1.5 w-full rounded-md border border-birch bg-paper px-2.5 py-1.5 text-sm"
        >
          {OFFICES.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
        <p className="mt-2 text-xs leading-snug text-ink-soft">
          Answers follow the leave, pay and benefit rules for your office&apos;s country.
        </p>
      </div>
    </div>
  );
}
