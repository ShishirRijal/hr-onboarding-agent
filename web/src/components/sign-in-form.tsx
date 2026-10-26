"use client";

import { useEffect, useState } from "react";
import { ApiError, fetchMe, signIn } from "@/lib/api";
import type { User } from "@/lib/types";
import { AssistantMark } from "./assistant-mark";

const FIELD =
  "mt-1.5 w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 text-ink transition-[border-color,box-shadow] placeholder:text-ink-faint focus-visible:border-brand-bright focus-visible:ring-4 focus-visible:ring-brand-bright/15 focus-visible:outline-none";

// Where to go once signed in: the HR team lands in the HR inbox, employees in the chat, or
// back to the page that sent them here.
function destination(user: User): string {
  const next = new URLSearchParams(window.location.search).get("next") ?? "";
  const safe = next.startsWith("/") && !next.startsWith("//") ? next : "";
  if (user.role === "hr") return safe.startsWith("/hr") ? safe : "/hr";
  return safe && !safe.startsWith("/hr") ? safe : "/";
}

export function SignInForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Already signed in: skip the form.
  useEffect(() => {
    fetchMe()
      .then((user) => window.location.replace(destination(user)))
      .catch(() => undefined);
  }, []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await signIn(email, password);
      // A full page load, so the app starts fresh for this account.
      window.location.assign(destination(user));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2.5">
          <AssistantMark state="still" />
          <span className="text-lg font-bold tracking-tight">NordTech HR</span>
        </div>

        <h1 className="mt-10 text-3xl font-bold">Sign in</h1>
        <p className="mt-2 leading-relaxed text-ink-soft">
          Use your NordTech work email to ask HR questions and see replies from the HR team.
        </p>

        <form onSubmit={submit} className="mt-8 space-y-4">
          <div>
            <label htmlFor="email" className="text-sm font-semibold">
              Work email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@nordtech.test"
              className={FIELD}
            />
          </div>
          <div>
            <label htmlFor="password" className="text-sm font-semibold">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={FIELD}
            />
          </div>

          {error && (
            <p role="alert" className="rounded-2xl bg-alert-wash px-4 py-3 text-sm text-alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-full bg-brand px-4 py-2.5 font-semibold text-white transition-colors hover:bg-brand-deep disabled:opacity-60"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-8 text-sm text-ink-soft">
          Trouble signing in? Email{" "}
          <a href="mailto:hr@nordtech.test" className="font-semibold text-brand underline underline-offset-2">
            hr@nordtech.test
          </a>
          .
        </p>
      </div>
    </main>
  );
}
