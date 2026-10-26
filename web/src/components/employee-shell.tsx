"use client";

import { useAppState } from "@/lib/app-state";
import { AppShell } from "./app-shell";
import { Sidebar } from "./sidebar";

export function EmployeeShell({ children }: { children: React.ReactNode }) {
  const { sessions } = useAppState();
  const unread = sessions.some((session) => session.unread > 0);

  return (
    <AppShell
      menuLabel="Open chats"
      attention={unread ? "new reply from HR" : undefined}
      sidebar={(onNavigate) => <Sidebar onNavigate={onNavigate} />}
    >
      {children}
    </AppShell>
  );
}
