"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, fetchHrQuestions } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { officeLabel } from "@/lib/offices";
import type { HrOverview, HrQuestion } from "@/lib/types";
import { useHrState } from "./hr-shell";

// Who an answer was added to the knowledge base for, to follow "for": "everyone" or
// "employees in Finland".
export function scopeLabel(country: string | null): string {
  return !country || country === "All" ? "everyone" : `employees in ${country}`;
}

function useQuestions(status: "requested" | "answered", refreshKey: unknown) {
  const [result, setResult] = useState<{ questions?: HrQuestion[]; error?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchHrQuestions(status)
      .then((questions) => !cancelled && setResult({ questions }))
      .catch((error: unknown) => {
        if (cancelled) return;
        setResult({ error: error instanceof ApiError ? error.message : "The questions couldn't be loaded." });
      });
    return () => {
      cancelled = true;
    };
  }, [status, refreshKey]);

  return result;
}

function Page({ title, intro, children }: { title: string; intro: string; children: React.ReactNode }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[60rem] px-4 pt-8 pb-12 sm:px-6 sm:pt-10">
        <h1 className="text-3xl font-bold">{title}</h1>
        <p className="mt-2 max-w-2xl leading-relaxed text-ink-soft">{intro}</p>
        {children}
      </div>
    </div>
  );
}

export function HrInbox() {
  const { overview, overviewError } = useHrState();
  // A change in the open count means questions came in or went out, so the list is reloaded.
  const result = useQuestions("requested", overview?.open_questions);

  return (
    <Page
      title="Inbox"
      intro="Questions employees sent to HR because the documents couldn't answer them. Your answer appears in the employee's chat and is added to what the assistant knows, so it can answer similar questions."
    >
      <Overview overview={overview} error={overviewError} />

      <section className="mt-10" aria-labelledby="waiting">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id="waiting" className="text-lg font-bold">
            Waiting for an answer
          </h2>
          <p className="text-sm text-ink-soft">Oldest first</p>
        </div>
        <QuestionList
          result={result}
          empty="No open questions. New ones appear here when an employee sends a question to HR."
        />
      </section>
    </Page>
  );
}

export function HrAnswered() {
  const result = useQuestions("answered", null);

  return (
    <Page
      title="Answered"
      intro="Questions the HR team has answered, newest first. Each answer is part of the assistant's knowledge for the employees it applies to."
    >
      <section className="mt-8" aria-label="Answered questions">
        <QuestionList result={result} empty="No answered questions yet." />
      </section>
    </Page>
  );
}

function Overview({ overview, error }: { overview: HrOverview | null; error: boolean }) {
  const topics = overview?.common_topics ?? [];

  return (
    <section aria-label="Overview" className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_2fr]">
      <Stat label="Open questions" value={overview?.open_questions} highlight={(overview?.open_questions ?? 0) > 0} />
      <Stat label="Answered this week" value={overview?.answered_this_week} />
      <div className="rounded-2xl bg-muted p-4 sm:col-span-2 lg:col-span-1">
        <h2 className="text-sm font-semibold text-ink">Most common unanswered topics</h2>
        <p className="text-xs text-ink-soft">Closest document section, last 30 days</p>
        {error && !overview ? (
          <p className="mt-3 text-sm text-ink-soft">The overview couldn&apos;t be loaded.</p>
        ) : !overview ? (
          <p className="pending mt-3 text-sm text-ink-soft">Loading…</p>
        ) : topics.length === 0 ? (
          <p className="mt-3 text-sm text-ink-soft">Nothing went unanswered in the last 30 days.</p>
        ) : (
          <ol className="mt-3 space-y-1.5">
            {topics.map((topic) => (
              <li key={topic.topic} className="flex items-baseline gap-3 text-sm">
                <span className="min-w-0 flex-1 truncate text-ink" title={topic.topic}>
                  {topic.topic}
                </span>
                <span className="text-ink-soft tabular-nums">
                  {topic.count}
                  <span className="sr-only"> {topic.count === 1 ? "question" : "questions"}</span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function Stat({ label, value, highlight }: { label: string; value: number | undefined; highlight?: boolean }) {
  return (
    <div className="rounded-2xl bg-muted p-4">
      <p className="text-sm font-semibold text-ink">{label}</p>
      <p className={`mt-1 text-4xl font-bold tracking-tight tabular-nums ${highlight ? "text-lamp" : "text-ink"}`}>
        {value ?? "–"}
      </p>
    </div>
  );
}

function QuestionList({
  result,
  empty,
}: {
  result: { questions?: HrQuestion[]; error?: string } | null;
  empty: string;
}) {
  if (!result) return <p className="pending mt-4 text-ink-soft">Loading questions…</p>;
  if (result.error) return <p className="mt-4 text-ink">{result.error}</p>;
  if (!result.questions?.length) {
    return <p className="mt-4 rounded-2xl border border-dashed border-line px-4 py-6 text-center text-ink-soft">{empty}</p>;
  }

  return (
    <ul className="mt-4 space-y-3">
      {result.questions.map((question) => (
        <li key={question.interaction_id}>
          <QuestionCard question={question} />
        </li>
      ))}
    </ul>
  );
}

function QuestionCard({ question }: { question: HrQuestion }) {
  const { asker } = question;
  const who = [asker.name, asker.job_title, asker.office ? officeLabel(asker) : null].filter(Boolean).join(" · ");

  return (
    <Link
      href={`/hr/q/${question.interaction_id}`}
      className="block rounded-2xl border border-line bg-surface p-4 transition-colors hover:border-brand-bright"
    >
      <p className="font-semibold text-ink">{question.question}</p>
      <p className="mt-1 text-sm text-ink-soft">{who}</p>
      {question.status === "answered" && question.hr_answer ? (
        <>
          <p className="mt-3 line-clamp-2 text-sm text-ink">{question.hr_answer}</p>
          <p className="mt-2 text-xs text-ink-soft">
            Answered by {question.hr_answered_by}
            {question.hr_answered_at && `, ${formatDateTime(question.hr_answered_at)}`} · For{" "}
            {scopeLabel(question.hr_answer_country)}
          </p>
        </>
      ) : (
        <p className="mt-2 flex flex-wrap items-center gap-x-2 text-xs text-ink-soft">
          <span>Asked {formatDateTime(question.asked_at)}</span>
          <span aria-hidden="true">·</span>
          <span>{question.reason}</span>
        </p>
      )}
    </Link>
  );
}
