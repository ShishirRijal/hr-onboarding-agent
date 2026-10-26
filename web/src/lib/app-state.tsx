"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { fetchSessions } from "./api";
import type { ChatSessionSummary, SessionSummary } from "./types";

// The chat list comes from the API, so it follows the user to any browser. It is checked
// again when the window regains focus and every minute, which is how replies from HR show up.
const REFRESH_MS = 60_000;

type AppState = {
  sessions: SessionSummary[];
  sessionsLoaded: boolean;
  refreshSessions: () => void;
  activeSessionId: string | null;
  setActiveSessionId: (sessionId: string | null) => void;
  saveSession: (session: SessionSummary) => void;
  markSessionRead: (sessionId: string) => void;
  newChatKey: number;
  resetNewChat: () => void;
};

const AppStateContext = createContext<AppState | null>(null);

function fromApi(session: ChatSessionSummary): SessionSummary {
  return {
    id: session.session_id,
    title: session.title,
    updatedAt: Date.parse(session.updated_at),
    unread: session.unread_hr_replies,
  };
}

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [newChatKey, setNewChatKey] = useState(0);
  // Chats started here whose first answer the API hasn't stored yet.
  const unsaved = useRef(new Map<string, SessionSummary>());

  const refreshSessions = useCallback(() => {
    fetchSessions()
      .then((list) => {
        const stored = list.map(fromApi);
        const storedIds = new Set(stored.map((session) => session.id));
        for (const id of storedIds) unsaved.current.delete(id);
        const merged = [...unsaved.current.values(), ...stored].sort((a, b) => b.updatedAt - a.updatedAt);
        setSessions(merged);
        setSessionsLoaded(true);
      })
      .catch(() => setSessionsLoaded(true));
  }, []);

  useEffect(() => {
    refreshSessions();
    const timer = setInterval(refreshSessions, REFRESH_MS);
    window.addEventListener("focus", refreshSessions);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refreshSessions);
    };
  }, [refreshSessions]);

  const saveSession = useCallback((session: SessionSummary) => {
    setSessions((current) => {
      const existing = current.find((item) => item.id === session.id);
      if (!existing) unsaved.current.set(session.id, session);
      const merged = existing ? { ...existing, updatedAt: session.updatedAt } : session;
      return [merged, ...current.filter((item) => item.id !== session.id)];
    });
  }, []);

  const markSessionRead = useCallback((sessionId: string) => {
    setSessions((current) =>
      current.some((item) => item.id === sessionId && item.unread > 0)
        ? current.map((item) => (item.id === sessionId ? { ...item, unread: 0 } : item))
        : current,
    );
  }, []);

  const resetNewChat = useCallback(() => setNewChatKey((key) => key + 1), []);

  const value = useMemo(
    () => ({
      sessions,
      sessionsLoaded,
      refreshSessions,
      activeSessionId,
      setActiveSessionId,
      saveSession,
      markSessionRead,
      newChatKey,
      resetNewChat,
    }),
    [sessions, sessionsLoaded, refreshSessions, activeSessionId, saveSession, markSessionRead, newChatKey, resetNewChat],
  );

  return <AppStateContext value={value}>{children}</AppStateContext>;
}

export function useAppState(): AppState {
  const state = useContext(AppStateContext);
  if (!state) throw new Error("useAppState must be used inside AppStateProvider.");
  return state;
}
