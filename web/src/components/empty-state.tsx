"use client";

import { useAppState } from "@/lib/app-state";

const SUGGESTIONS = [
  "How much annual leave do I get?",
  "When is salary paid each month?",
  "How do I set up the VPN?",
  "Can I expense a standing desk?",
];

export function EmptyState({ onAsk }: { onAsk: (question: string) => void }) {
  const { office } = useAppState();

  return (
    <div className="pt-[12vh] pb-8">
      <h1
        key={office.id}
        className="greeting text-6xl font-semibold tracking-tight text-baltic sm:text-7xl"
      >
        {office.greeting}
      </h1>
      <p className="mt-4 max-w-xl text-lg leading-relaxed text-ink-soft">
        I&apos;m NordTech&apos;s HR assistant. Ask about leave, pay, benefits, IT setup or your first
        weeks here. I answer from company policy, and anything I can&apos;t answer goes to the HR team.
      </p>

      <h2 className="mt-10 text-sm text-ink-soft">Try asking</h2>
      <ul className="mt-2 divide-y divide-birch border-y border-birch">
        {SUGGESTIONS.map((question) => (
          <li key={question}>
            <button
              type="button"
              onClick={() => onAsk(question)}
              className="w-full py-3 text-left text-ink hover:text-baltic"
            >
              {question}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
