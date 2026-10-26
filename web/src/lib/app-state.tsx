"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { DEFAULT_OFFICE, findOffice, type Office } from "./offices";
import type { SessionSummary } from "./types";

// Until there is login, the session list and office live in this browser only.
// Message history itself is stored by the API, keyed by session id.
const SESSIONS_KEY = "nordtech-hr.sessions";
const OFFICE_KEY = "nordtech-hr.office";
const MAX_SESSIONS = 50;

type AppState = {
  sessions: SessionSummary[];
  office: Office;
  setOffice: (officeId: string) => void;
  activeSessionId: string | null;
  setActiveSessionId: (sessionId: string | null) => void;
  saveSession: (session: SessionSummary) => void;
  newChatKey: number;
  resetNewChat: () => void;
};

const AppStateContext = createContext<AppState | null>(null);

function readStorage<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeStorage(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage can be unavailable (private mode); the app still works for this visit.
  }
}

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [office, setOfficeState] = useState<Office>(DEFAULT_OFFICE);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [newChatKey, setNewChatKey] = useState(0);

  useEffect(() => {
    // Hydrate from browser storage after mount so server and client render the same markup.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSessions(readStorage<SessionSummary[]>(SESSIONS_KEY, []));
    setOfficeState(findOffice(readStorage<string | null>(OFFICE_KEY, null)));
  }, []);

  const setOffice = useCallback((officeId: string) => {
    setOfficeState(findOffice(officeId));
    writeStorage(OFFICE_KEY, officeId);
  }, []);

  const saveSession = useCallback((session: SessionSummary) => {
    setSessions((current) => {
      const existing = current.find((item) => item.id === session.id);
      const merged = existing ? { ...existing, updatedAt: session.updatedAt } : session;
      const next = [merged, ...current.filter((item) => item.id !== session.id)].slice(0, MAX_SESSIONS);
      writeStorage(SESSIONS_KEY, next);
      return next;
    });
  }, []);

  const resetNewChat = useCallback(() => setNewChatKey((key) => key + 1), []);

  const value = useMemo(
    () => ({
      sessions,
      office,
      setOffice,
      activeSessionId,
      setActiveSessionId,
      saveSession,
      newChatKey,
      resetNewChat,
    }),
    [sessions, office, setOffice, activeSessionId, saveSession, newChatKey, resetNewChat],
  );

  return <AppStateContext value={value}>{children}</AppStateContext>;
}

export function useAppState(): AppState {
  const state = useContext(AppStateContext);
  if (!state) throw new Error("useAppState must be used inside AppStateProvider.");
  return state;
}
