"use client";

import { useEffect, useState } from "react";
import { CloseIcon, MenuIcon } from "./icons";
import { Sidebar } from "./sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (!drawerOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [drawerOpen]);

  return (
    <div className="flex h-dvh">
      <aside className="hidden w-72 shrink-0 border-r border-birch bg-paper md:flex">
        <Sidebar />
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Chats">
          <button
            type="button"
            className="absolute inset-0 bg-ink/30"
            aria-label="Close chats"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="relative flex h-full w-[min(20rem,85vw)] bg-paper shadow-xl">
            <Sidebar onNavigate={() => setDrawerOpen(false)} />
            <button
              type="button"
              className="absolute top-4 right-3 rounded-md p-1.5 text-ink-soft hover:bg-ice"
              aria-label="Close chats"
              onClick={() => setDrawerOpen(false)}
            >
              <CloseIcon className="size-5" />
            </button>
          </aside>
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-birch bg-paper px-4 py-3 md:hidden">
          <button
            type="button"
            className="-ml-1 rounded-md p-1.5 text-ink-soft hover:bg-ice"
            aria-label="Open chats"
            onClick={() => setDrawerOpen(true)}
          >
            <MenuIcon className="size-5" />
          </button>
          <span className="font-semibold">NordTech HR</span>
        </header>
        {children}
      </main>
    </div>
  );
}
