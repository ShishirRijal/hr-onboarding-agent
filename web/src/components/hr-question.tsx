"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { answerHrQuestion, ApiError, fetchHrQuestion } from "@/lib/api";
import { stripCitations } from "@/lib/citations";
import { firstName, formatDateTime } from "@/lib/format";
import { officeLabel } from "@/lib/offices";
import type { AnswerScope, HrQuestionDetail } from "@/lib/types";
import { Avatar } from "./account";
import { AssistantMark } from "./assistant-mark";
import { useHrState } from "./hr-shell";
import { scopeLabel } from "./hr-inbox";
import { CheckIcon, ChevronIcon } from "./icons";

const FIELD =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 leading-relaxed text-ink transition-[border-color,box-shadow] placeholder:text-ink-faint focus-visible:border-brand-bright focus-visible:ring-4 focus-visible:ring-brand-bright/15 focus-visible:outline-none";

// One question an employee sent to HR: who asked, why the assistant couldn't answer, the chat
// so far, and the answer form (or the answer, once sent).
export function HrQuestionView({ interactionId }: { interactionId: string }) {
  const { refreshOverview } = useHrState();
  const [result, setResult] = useState<{ detail?: HrQuestionDetail; error?: string } | null>(null);
  const [justSent, setJustSent] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchHrQuestion(interactionId)
      .then((detail) => !cancelled && setResult({ detail }))
      .catch((error: unknown) => {
        if (cancelled) return;
        setResult({ error: error instanceof ApiError ? error.message : "This question couldn't be loaded." });
      });
    return () => {
      cancelled = true;
    };
  }, [interactionId]);

  if (!result) return <p className="pending mx-auto w-full max-w-[60rem] px-6 pt-10 text-ink-soft">Loading this question…</p>;

  const detail = result.detail;
  const answered = detail?.status === "answered";

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-[60rem] px-4 pt-6 pb-12 sm:px-6 sm:pt-8">
        <Link
          href={answered && !justSent ? "/hr/answered" : "/hr"}
          className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:text-brand-deep"
        >
          <ChevronIcon className="size-4 rotate-180" />
          {answered && !justSent ? "Answered" : "Inbox"}
        </Link>

        {!detail ? (
          <p className="mt-8 text-ink">{result.error}</p>
        ) : (
          <>
            <p className="mt-6 text-sm text-ink-soft">Asked {formatDateTime(detail.asked_at)}</p>
            <h1 className="mt-1 text-2xl font-bold sm:text-3xl">{detail.question}</h1>

            <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
              <div className="order-2 min-w-0 space-y-10 lg:order-1">
                {answered ? (
                  <AnswerSent detail={detail} justSent={justSent} />
                ) : (
                  <AnswerForm
                    detail={detail}
                    onSent={(updated) => {
                      setResult({ detail: updated });
                      setJustSent(true);
                      refreshOverview();
                    }}
                  />
                )}
                <EarlierTurns turns={detail.earlier_turns} />
              </div>
              <div className="order-1 space-y-3 lg:order-2">
                <AskerCard detail={detail} />
                <section aria-labelledby="why" className="rounded-2xl bg-muted p-4">
                  <h2 id="why" className="text-sm font-semibold text-ink">
                    Why the assistant couldn&apos;t answer
                  </h2>
                  <p className="mt-1 text-sm text-ink">{detail.reason}</p>
                  <h2 className="mt-4 text-sm font-semibold text-ink">Documents it checked</h2>
                  {detail.documents_checked.length === 0 ? (
                    <p className="mt-1 text-sm text-ink-soft">None matched the question.</p>
                  ) : (
                    <ul className="mt-1 space-y-0.5 text-sm text-ink">
                      {detail.documents_checked.map((document) => (
                        <li key={document}>{document}</li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function AskerCard({ detail }: { detail: HrQuestionDetail }) {
  const { asker } = detail;
  return (
    <section aria-labelledby="asker" className="rounded-2xl bg-muted p-4">
      <h2 id="asker" className="text-sm font-semibold text-ink">
        Asked by
      </h2>
      <div className="mt-3 flex items-center gap-3">
        <Avatar name={asker.name} />
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink">{asker.name}</p>
          {asker.job_title && <p className="truncate text-sm text-ink-soft">{asker.job_title}</p>}
        </div>
      </div>
      <dl className="mt-3 space-y-1 text-sm">
        {asker.department && (
          <div className="flex gap-2">
            <dt className="text-ink-soft">Department</dt>
            <dd className="min-w-0 text-ink">{asker.department}</dd>
          </div>
        )}
        {asker.office && (
          <div className="flex gap-2">
            <dt className="text-ink-soft">Office</dt>
            <dd className="min-w-0 text-ink">{officeLabel(asker)}</dd>
          </div>
        )}
        {asker.email && (
          <div className="flex gap-2">
            <dt className="text-ink-soft">Email</dt>
            <dd className="min-w-0 break-all">
              <a href={`mailto:${asker.email}`} className="font-semibold text-brand underline underline-offset-2">
                {asker.email}
              </a>
            </dd>
          </div>
        )}
      </dl>
    </section>
  );
}

function AnswerForm({ detail, onSent }: { detail: HrQuestionDetail; onSent: (detail: HrQuestionDetail) => void }) {
  const country = detail.asker.country;
  const name = firstName(detail.asker.name);
  const [answer, setAnswer] = useState("");
  // Many answers depend on the country's rules, so the narrower choice is the default.
  const [scope, setScope] = useState<AnswerScope>(country ? "country" : "everyone");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const options: { value: AnswerScope; label: string; hint: string; disabled?: boolean }[] = [
    {
      value: "country",
      label: country ? `Employees in ${country}` : "Employees in their country",
      hint: "For rules that differ by country, like leave, pay or public holidays.",
      disabled: !country,
    },
    { value: "everyone", label: "Everyone at NordTech", hint: "For answers that are the same in every office." },
  ];

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!answer.trim()) return;
    setBusy(true);
    setError(null);
    try {
      onSent(await answerHrQuestion(detail.interaction_id, answer.trim(), scope));
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "The answer couldn't be sent. Try again.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-2xl border border-line p-4 sm:p-5">
      <h2 className="text-lg font-bold">
        <label htmlFor="answer">Your answer</label>
      </h2>
      <p id="answer-help" className="mt-1 text-sm leading-relaxed text-ink-soft">
        It appears in {name}&apos;s chat, and it&apos;s added to what the assistant knows, so it can answer similar
        questions without coming to HR.
      </p>
      <textarea
        id="answer"
        aria-describedby="answer-help"
        rows={6}
        required
        maxLength={5000}
        value={answer}
        onChange={(event) => setAnswer(event.target.value)}
        className={`mt-3 ${FIELD}`}
      />

      <fieldset className="mt-4">
        <legend className="text-sm font-semibold">Who does this answer apply to?</legend>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {options.map((option) => (
            <label
              key={option.value}
              className={`flex items-start gap-3 rounded-xl border px-3 py-2.5 transition-colors ${
                option.disabled
                  ? "border-line opacity-60"
                  : "cursor-pointer border-line hover:border-brand-bright has-[:checked]:border-brand-bright has-[:checked]:bg-brand-wash"
              }`}
            >
              <input
                type="radio"
                name="scope"
                value={option.value}
                checked={scope === option.value}
                disabled={option.disabled}
                onChange={() => setScope(option.value)}
                className="mt-1 accent-brand"
              />
              <span>
                <span className="block text-sm font-semibold text-ink">{option.label}</span>
                <span className="block text-sm text-ink-soft">{option.hint}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {error && (
        <p role="alert" className="mt-4 rounded-2xl bg-alert-wash px-4 py-3 text-sm text-alert">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={busy || !answer.trim()}
        className="mt-5 rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-deep disabled:bg-muted disabled:text-ink-faint"
      >
        {busy ? "Sending…" : `Send to ${name}`}
      </button>
    </form>
  );
}

function AnswerSent({ detail, justSent }: { detail: HrQuestionDetail; justSent: boolean }) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const name = firstName(detail.asker.name);

  // After sending, focus moves here so screen readers hear that it went out.
  useEffect(() => {
    if (justSent) headingRef.current?.focus();
  }, [justSent]);

  return (
    <section aria-labelledby="sent" className="rounded-2xl border border-line p-4 sm:p-5">
      <h2 id="sent" ref={headingRef} tabIndex={-1} className="flex items-center gap-2 text-lg font-bold">
        <CheckIcon className="size-5 text-brand" />
        {justSent ? `Sent to ${name}` : "Answered"}
      </h2>
      <p className="mt-1 text-sm leading-relaxed text-ink-soft">
        {detail.hr_answered_by && `By ${detail.hr_answered_by}`}
        {detail.hr_answered_at && `, ${formatDateTime(detail.hr_answered_at)}`}. It&apos;s in {name}&apos;s chat and in
        the assistant&apos;s knowledge for {scopeLabel(detail.hr_answer_country)}.
      </p>
      <p className="mt-4 leading-relaxed whitespace-pre-wrap text-ink">{detail.hr_answer}</p>
    </section>
  );
}

export function EarlierTurns({ turns }: { turns: { question: string; answer: string }[] }) {
  return (
    <section aria-labelledby="earlier">
      <h2 id="earlier" className="text-lg font-bold">
        Earlier in this chat
      </h2>
      {turns.length === 0 ? (
        <p className="mt-1 text-sm text-ink-soft">This was the first question in the chat.</p>
      ) : (
        <ol className="mt-4 space-y-5">
          {turns.map((turn, index) => (
            <li key={index} className="space-y-3">
              <div className="flex justify-end">
                <p className="max-w-[85%] rounded-3xl rounded-br-lg bg-brand-wash px-4 py-2.5 whitespace-pre-wrap text-ink">
                  {turn.question}
                </p>
              </div>
              <div className="flex gap-3">
                <AssistantMark state="still" />
                <div className="answer min-w-0 flex-1 pt-0.5">
                  <Markdown>{stripCitations(turn.answer)}</Markdown>
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
