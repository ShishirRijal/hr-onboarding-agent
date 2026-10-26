"use client";

import { useEffect } from "react";
import { useAppState } from "@/lib/app-state";
import { formatDate } from "@/lib/format";
import { officeLabel } from "@/lib/offices";
import { useSession } from "@/lib/session";
import { Avatar } from "./account";

export function Profile() {
  const { user, signOut } = useSession();
  const { setActiveSessionId } = useAppState();

  useEffect(() => {
    setActiveSessionId(null);
  }, [setActiveSessionId]);

  const details: [string, React.ReactNode][] = [
    ["Email", user.email],
    ["Job title", user.job_title],
    ["Department", user.department],
    ["Office", officeLabel(user)],
    ["Manager", user.manager_name ?? "Not set"],
    ["Start date", formatDate(user.start_date)],
  ];
  if (user.pronouns) details.push(["Pronouns", user.pronouns]);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[46rem] px-4 pt-10 pb-12 sm:px-6">
        <div className="flex items-center gap-4">
          <Avatar name={user.name} size="lg" />
          <div className="min-w-0">
            <h1 className="text-3xl font-bold">{user.name}</h1>
            <p className="text-ink-soft">
              {user.job_title}
              {user.pronouns && <span> · {user.pronouns}</span>}
            </p>
          </div>
        </div>

        <dl className="mt-8 divide-y divide-line rounded-2xl border border-line">
          {details.map(([label, value]) => (
            <div key={label} className="grid gap-0.5 px-4 py-3 sm:grid-cols-[10rem_1fr] sm:gap-4">
              <dt className="text-sm text-ink-soft">{label}</dt>
              <dd className="min-w-0 break-words text-ink">{value}</dd>
            </div>
          ))}
        </dl>

        <p className="mt-4 text-sm leading-relaxed text-ink-soft">
          The assistant uses your office and country to answer with the rules that apply to you. To change any of
          these details, email HR at{" "}
          <a href="mailto:hr@nordtech.test" className="font-semibold text-brand underline underline-offset-2">
            hr@nordtech.test
          </a>
          .
        </p>

        <button
          type="button"
          onClick={() => void signOut()}
          className="mt-8 rounded-full bg-muted px-4 py-2 text-sm font-semibold text-ink transition-colors hover:bg-line"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
