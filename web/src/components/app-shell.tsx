"use client";

import { useEffect, useState } from "react";
import { CloseIcon, MenuIcon } from "./icons";

// The light grey sidebar beside the page, and a drawer for it on small screens. Used by both
// the employee chat and the HR platform; `sidebar` renders the one for this area.
export function AppShell({
  sidebar,
  menuLabel,
  attention,
  children,
}: {
  sidebar: (onNavigate?: () => void) => React.ReactNode;
  menuLabel: string;
  // Something in the sidebar is new, like an HR reply; marks the menu button on small screens.
  attention?: string;
  children: React.ReactNode;
}) {
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
      <aside className="hidden w-72 shrink-0 bg-muted md:flex">{sidebar()}</aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label={menuLabel}>
          <button
            type="button"
            className="absolute inset-0 bg-ink/30"
            aria-label="Close menu"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="relative flex h-full w-[min(20rem,85vw)] bg-muted shadow-xl">
            {sidebar(() => setDrawerOpen(false))}
            <button
              type="button"
              className="absolute top-4 right-3 rounded-full p-1.5 text-ink-soft hover:bg-ink/5"
              aria-label="Close menu"
              onClick={() => setDrawerOpen(false)}
            >
              <CloseIcon className="size-5" />
            </button>
          </aside>
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3 md:hidden">
          <button
            type="button"
            className="relative -ml-1 rounded-full p-1.5 text-ink-soft hover:bg-muted"
            aria-label={attention ? `${menuLabel} (${attention})` : menuLabel}
            onClick={() => setDrawerOpen(true)}
          >
            <MenuIcon className="size-5" />
            {attention && (
              <span className="absolute top-1 right-1 size-2 rounded-full bg-brand ring-2 ring-surface" aria-hidden="true" />
            )}
          </button>
          <span className="font-bold tracking-tight">NordTech HR</span>
        </header>
        {children}
      </main>
    </div>
  );
}
