"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { initials } from "@/lib/format";
import { useSession } from "@/lib/session";

export function Avatar({ name, size = "sm" }: { name: string; size?: "sm" | "lg" }) {
  return (
    <span
      aria-hidden="true"
      className={`grid shrink-0 place-items-center rounded-full bg-brand-wash font-semibold text-brand-deep ${
        size === "lg" ? "size-16 text-xl" : "size-9 text-sm"
      }`}
    >
      {initials(name)}
    </span>
  );
}

// The signed-in user at the foot of the sidebar: who they are, and a way out.
export function AccountFooter({
  detail,
  profileHref,
  onNavigate,
  children,
}: {
  detail: string;
  profileHref?: string;
  onNavigate?: () => void;
  children?: React.ReactNode;
}) {
  const { user, signOut } = useSession();
  const pathname = usePathname();
  const who = (
    <>
      <Avatar name={user.name} />
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-ink">{user.name}</span>
        <span className="block truncate text-xs text-ink-soft">{detail}</span>
      </span>
    </>
  );

  return (
    <div className="space-y-1 px-3 pt-2 pb-4">
      {children}
      {profileHref ? (
        <Link
          href={profileHref}
          onClick={onNavigate}
          aria-current={pathname === profileHref ? "page" : undefined}
          aria-label={`Your profile: ${user.name}`}
          className={`flex items-center gap-3 rounded-xl px-2 py-2 ${
            pathname === profileHref ? "bg-surface shadow-[0_1px_3px_rgb(6_26_55/0.08)]" : "hover:bg-ink/5"
          }`}
        >
          {who}
        </Link>
      ) : (
        <div className="flex items-center gap-3 px-2 py-2">{who}</div>
      )}
      <button
        type="button"
        onClick={() => void signOut()}
        className="w-full rounded-full px-3 py-2 text-left text-sm font-semibold text-ink-soft transition-colors hover:bg-ink/5 hover:text-ink"
      >
        Sign out
      </button>
    </div>
  );
}
