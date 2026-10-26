"use client";

import { firstName } from "@/lib/format";
import { greetingFor } from "@/lib/offices";
import { useSession } from "@/lib/session";

const SUGGESTIONS = [
  "How much annual leave do I get?",
  "When is salary paid each month?",
  "How do I set up the VPN?",
  "Can I expense a standing desk?",
];

export function EmptyState({ onAsk }: { onAsk: (question: string) => void }) {
  const { user } = useSession();

  return (
    <div className="pt-[12vh] pb-8">
      <h1 className="greeting text-6xl font-bold tracking-tighter text-brand sm:text-7xl">
        {greetingFor(user)}, {firstName(user.name)}
      </h1>
      <p className="mt-4 max-w-xl text-lg leading-relaxed text-ink-soft">
        I&apos;m NordTech&apos;s HR assistant. Ask about leave, pay, benefits, IT setup or your first
        weeks here. I answer from company policy, and if it isn&apos;t covered I can pass your question to HR.
      </p>

      <h2 className="mt-10 text-sm font-semibold text-ink">Try asking</h2>
      <ul className="mt-3 grid gap-3 sm:grid-cols-2">
        {SUGGESTIONS.map((question) => (
          <li key={question}>
            <button
              type="button"
              onClick={() => onAsk(question)}
              className="h-full w-full rounded-2xl bg-muted px-4 py-3.5 text-left font-medium text-ink transition-colors hover:bg-brand-wash"
            >
              {question}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
