"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, fetchMe, SIGN_IN_PATH, signOut as signOutRequest } from "./api";
import type { User } from "./types";

type Session = {
  user: User;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<Session | null>(null);

// Loads the signed-in user before showing the app. Without a valid session the API answers
// 401 and the request helper sends the browser to sign-in. The HR area is for the HR team
// only; the API enforces that too, this just keeps others from landing on an empty page.
export function SessionProvider({ area, children }: { area: "employee" | "hr"; children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((me) => {
        if (cancelled) return;
        if (area === "hr" && me.role !== "hr") router.replace("/");
        else setUser(me);
      })
      .catch((reason: unknown) => {
        if (cancelled || (reason instanceof ApiError && reason.status === 401)) return;
        setError(reason instanceof ApiError ? reason.message : "Something went wrong. Reload the page.");
      });
    return () => {
      cancelled = true;
    };
  }, [area, router]);

  const signOut = useCallback(async () => {
    await signOutRequest().catch(() => undefined);
    // A full page load clears everything kept in memory for this user.
    window.location.assign(SIGN_IN_PATH);
  }, []);

  const value = useMemo(() => (user ? { user, signOut } : null), [user, signOut]);

  if (!value) {
    return (
      <div className="grid h-dvh place-items-center px-6 text-center">
        {error ? <p className="text-ink">{error}</p> : <p className="pending text-ink-soft">Loading…</p>}
      </div>
    );
  }
  return <SessionContext value={value}>{children}</SessionContext>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside SessionProvider.");
  return session;
}
