"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchReviewDetail, fetchReviewPage, saveReview } from "@/lib/api";
import { stripCitations } from "@/lib/citations";
import { formatDateTime } from "@/lib/format";
import { formatNumber, formatUsd } from "@/lib/usage";
import type { ReviewDetail, ReviewFilter, ReviewItem, ReviewVerdict, Source } from "@/lib/types";
import { HrPage } from "./hr-inbox";
import { EarlierTurns } from "./hr-question";
import { useHrState } from "./hr-shell";
import { CheckIcon, ChevronIcon } from "./icons";
import { AnswerText } from "./messages";
import { SourcePanel } from "./source-panel";

const FILTERS: { value: ReviewFilter; label: string; empty: string }[] = [
  { value: "all", label: "All", empty: "No questions yet. Everything employees ask the assistant appears here." },
  { value: "unhelpful", label: "Marked unhelpful", empty: "No answers have been marked unhelpful." },
  { value: "helpful", label: "Marked helpful", empty: "No answers have been marked helpful yet." },
  { value: "not_answered", label: "Not answered", empty: "The assistant has answered every question so far." },
  { value: "reviewed", label: "Reviewed", empty: "No answers reviewed yet." },
];

const FIELD =
  "w-full rounded-xl border border-line bg-surface px-3.5 py-2.5 leading-relaxed text-ink transition-[border-color,box-shadow] placeholder:text-ink-faint focus-visible:border-brand-bright focus-visible:ring-4 focus-visible:ring-brand-bright/15 focus-visible:outline-none";

function filterOf(value: string | null): ReviewFilter {
  return FILTERS.some((filter) => filter.value === value) ? (value as ReviewFilter) : "all";
}

// Everything employees asked the assistant, without who asked, for HR to read through, and
// to mark right or rewrite.
export function HrReview() {
  const show = filterOf(useSearchParams().get("show"));
  const { overview } = useHrState();
  const [result, setResult] = useState<{ show: ReviewFilter; items: ReviewItem[]; total: number; error?: string } | null>(
    null,
  );
  const [loadingMore, setLoadingMore] = useState(false);
  const loaded = result?.show === show ? result : null;

  useEffect(() => {
    let cancelled = false;
    fetchReviewPage(show)
      .then((page) => !cancelled && setResult({ show, ...page }))
      .catch((error: unknown) => {
        if (cancelled) return;
        const message = error instanceof ApiError ? error.message : "The questions couldn't be loaded.";
        setResult({ show, items: [], total: 0, error: message });
      });
    return () => {
      cancelled = true;
    };
  }, [show]);

  async function loadMore() {
    if (!loaded) return;
    setLoadingMore(true);
    try {
      const page = await fetchReviewPage(show, loaded.items.length);
      setResult({ ...loaded, items: [...loaded.items, ...page.items], total: page.total });
    } finally {
      setLoadingMore(false);
    }
  }

  const filter = FILTERS.find((item) => item.value === show) ?? FILTERS[0];
  return (
    <HrPage
      title="Answer review"
      intro="Every question employees have asked the assistant, newest first, without their names. Read how it answered, mark answers that are right, and rewrite the ones that aren't. Reviews are kept to test and improve the assistant; employees don't see them."
    >
      <nav aria-label="Show" className="-mx-4 mt-8 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <ul className="flex gap-1.5">
          {FILTERS.map((item) => {
            const current = item.value === show;
            const count = item.value === "unhelpful" ? (overview?.unhelpful_to_review ?? 0) : 0;
            return (
              <li key={item.value} className="shrink-0">
                <Link
                  href={item.value === "all" ? "/hr/review" : `/hr/review?show=${item.value}`}
                  aria-current={current ? "page" : undefined}
                  className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm transition-colors ${
                    current ? "bg-ink font-semibold text-white" : "bg-muted text-ink hover:bg-line"
                  }`}
                >
                  {item.label}
                  {count > 0 && (
                    <span
                      className={`rounded-full px-1.5 text-xs font-semibold tabular-nums ${
                        current ? "bg-white/20" : "bg-alert-wash text-alert"
                      }`}
                    >
                      {count}
                      <span className="sr-only"> not reviewed yet</span>
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <section className="mt-6" aria-label={filter.label}>
        {!loaded ? (
          <p className="pending text-ink-soft">Loading questions…</p>
        ) : loaded.error ? (
          <p className="text-ink">{loaded.error}</p>
        ) : loaded.items.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-line px-4 py-6 text-center text-ink-soft">
            {filter.empty}
          </p>
        ) : (
          <>
            <p className="text-sm text-ink-soft">
              {loaded.total === 1 ? "1 question" : `${loaded.total} questions`}
            </p>
            <ul className="mt-3 space-y-3">
              {loaded.items.map((item) => (
                <li key={item.interaction_id}>
                  <ReviewCard item={item} show={show} />
                </li>
              ))}
            </ul>
            {loaded.items.length < loaded.total && (
              <button
                type="button"
                onClick={() => void loadMore()}
                disabled={loadingMore}
                className="mt-4 w-full rounded-full bg-muted px-4 py-2.5 text-sm font-semibold text-ink transition-colors hover:bg-line disabled:opacity-60"
              >
                {loadingMore ? "Loading…" : `Show more (${loaded.total - loaded.items.length} left)`}
              </button>
            )}
          </>
        )}
      </section>
    </HrPage>
  );
}

function ReviewCard({ item, show }: { item: ReviewItem; show: ReviewFilter }) {
  const href = `/hr/review/${item.interaction_id}${show === "all" ? "" : `?from=${show}`}`;
  return (
    <Link
      href={href}
      className="block rounded-2xl border border-line bg-surface p-4 transition-colors hover:border-brand-bright"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs text-ink-soft">
        <span>{formatDateTime(item.asked_at)}</span>
        {item.country && <span>{item.country}</span>}
        <Tags item={item} />
      </div>
      <p className="mt-2 font-semibold text-ink">{item.question}</p>
      <p className="mt-1 line-clamp-2 text-sm text-ink-soft">{stripCitations(item.answer)}</p>
      {item.feedback === "down" && item.feedback_comment && (
        <p className="mt-2 border-l-2 border-alert/40 pl-2.5 text-sm text-ink">“{item.feedback_comment}”</p>
      )}
    </Link>
  );
}

function Tag({ tone, children }: { tone: "alert" | "brand" | "lamp" | "quiet"; children: React.ReactNode }) {
  const tones = {
    alert: "bg-alert-wash text-alert",
    brand: "bg-brand-wash text-brand-deep",
    lamp: "bg-lamp-wash text-lamp",
    quiet: "bg-muted text-ink-soft",
  };
  return <span className={`rounded-full px-2 py-0.5 font-semibold ${tones[tone]}`}>{children}</span>;
}

function Tags({ item }: { item: ReviewItem }) {
  return (
    <>
      {item.feedback === "down" && <Tag tone="alert">Marked unhelpful</Tag>}
      {item.feedback === "up" && <Tag tone="brand">Marked helpful</Tag>}
      {!item.answered && <Tag tone="lamp">{sentToHr(item) ? "Sent to HR" : "Not answered"}</Tag>}
      {item.small_talk && <Tag tone="quiet">Small talk</Tag>}
      {item.review_verdict && (
        <Tag tone="quiet">{item.review_verdict === "correct" ? "Reviewed: right" : "Reviewed: rewritten"}</Tag>
      )}
    </>
  );
}

function sentToHr(item: ReviewItem): boolean {
  return item.escalation_status === "requested" || item.escalation_status === "answered";
}

// One question in the answer review: what the assistant said, what the employee thought of
// it, and HR's review.
export function HrReviewDetailView({ interactionId }: { interactionId: string }) {
  const { refreshOverview } = useHrState();
  const from = filterOf(useSearchParams().get("from"));
  const [result, setResult] = useState<{ detail?: ReviewDetail; error?: string } | null>(null);
  const [openSource, setOpenSource] = useState<Source | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchReviewDetail(interactionId)
      .then((detail) => !cancelled && setResult({ detail }))
      .catch((error: unknown) => {
        if (cancelled) return;
        setResult({ error: error instanceof ApiError ? error.message : "This question couldn't be loaded." });
      });
    return () => {
      cancelled = true;
    };
  }, [interactionId]);

  const closeSource = useCallback(() => {
    setOpenSource(null);
    openerRef.current?.focus();
  }, []);

  const detail = result?.detail;
  const back = from === "all" ? "/hr/review" : `/hr/review?show=${from}`;

  return (
    <div className="flex min-h-0 flex-1">
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[60rem] px-4 pt-6 pb-12 sm:px-6 sm:pt-8">
          <Link href={back} className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:text-brand-deep">
            <ChevronIcon className="size-4 rotate-180" />
            Answer review
          </Link>

          {!result ? (
            <p className="pending mt-8 text-ink-soft">Loading this question…</p>
          ) : !detail ? (
            <p className="mt-8 text-ink">{result.error}</p>
          ) : (
            <>
              <p className="mt-6 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-sm text-ink-soft">
                <span>Asked {formatDateTime(detail.asked_at)}</span>
                {detail.country && <span>{detail.country}</span>}
                <span className="inline-flex flex-wrap gap-1.5 text-xs">
                  <Tags item={detail} />
                </span>
              </p>
              <h1 className="mt-1 text-2xl font-bold sm:text-3xl">{detail.question}</h1>

              <div className="mt-8 space-y-10">
                <section aria-labelledby="assistant-answer">
                  <h2 id="assistant-answer" className="text-lg font-bold">
                    The assistant&apos;s answer
                  </h2>
                  <div className="mt-3 rounded-2xl bg-muted px-4 py-3.5">
                    <AnswerText
                      text={detail.answer}
                      sources={detail.sources}
                      openChunkId={openSource?.chunk_id ?? null}
                      onOpenSource={(source, opener) => {
                        openerRef.current = opener;
                        setOpenSource(openSource?.chunk_id === source.chunk_id ? null : source);
                      }}
                    />
                    {detail.reason && <p className="mt-3 text-sm text-ink-soft">{detail.reason}</p>}
                  </div>
                  {detail.hr_answer && (
                    <p className="mt-3 text-sm text-ink-soft">
                      The employee sent this to HR, and it was answered from the{" "}
                      <Link href={`/hr/q/${detail.interaction_id}`} className="font-semibold text-brand underline underline-offset-2">
                        inbox
                      </Link>
                      .
                    </p>
                  )}
                  {detail.feedback && <EmployeeFeedback detail={detail} />}
                  {detail.usage && (
                    <p className="mt-3 text-sm text-ink-soft">
                      This answer took {formatNumber(detail.usage.tokens)} tokens in {detail.usage.calls} model calls (
                      {detail.usage.models.join(", ")}), {formatUsd(detail.usage.cost_usd)}.
                    </p>
                  )}
                </section>

                <Review
                  detail={detail}
                  onSaved={(updated) => {
                    setResult({ detail: updated });
                    refreshOverview();
                  }}
                />

                <EarlierTurns turns={detail.earlier_turns} />
              </div>
            </>
          )}
        </div>
      </div>
      {openSource && <SourcePanel key={openSource.chunk_id} source={openSource} onClose={closeSource} />}
    </div>
  );
}

function EmployeeFeedback({ detail }: { detail: ReviewDetail }) {
  const unhelpful = detail.feedback === "down";
  return (
    <div className={`mt-3 rounded-2xl px-4 py-3 ${unhelpful ? "bg-alert-wash" : "bg-brand-wash"}`}>
      <p className={`text-sm font-semibold ${unhelpful ? "text-alert" : "text-brand-deep"}`}>
        The employee marked this {unhelpful ? "unhelpful" : "helpful"}
      </p>
      {unhelpful && (
        <p className="mt-0.5 text-sm text-ink">
          {detail.feedback_comment ? `“${detail.feedback_comment}”` : "They didn't say what was wrong."}
        </p>
      )}
    </div>
  );
}

function Review({ detail, onSaved }: { detail: ReviewDetail; onSaved: (detail: ReviewDetail) => void }) {
  const [editing, setEditing] = useState(!detail.review_verdict);
  const [answer, setAnswer] = useState(detail.review_answer ?? "");
  const [busy, setBusy] = useState<ReviewVerdict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const rightLabel = detail.answered ? "The answer is right" : "Right not to answer";

  async function save(verdict: ReviewVerdict) {
    setBusy(verdict);
    setError(null);
    try {
      const updated = await saveReview(detail.interaction_id, verdict, verdict === "corrected" ? answer.trim() : undefined);
      setEditing(false);
      onSaved(updated);
      // Focus moves to the saved review so screen readers hear it was saved.
      requestAnimationFrame(() => headingRef.current?.focus());
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "The review couldn't be saved. Try again.");
    } finally {
      setBusy(null);
    }
  }

  if (!editing && detail.review_verdict) {
    return (
      <section aria-labelledby="review" className="rounded-2xl border border-line p-4 sm:p-5">
        <h2 id="review" ref={headingRef} tabIndex={-1} className="flex items-center gap-2 text-lg font-bold">
          <CheckIcon className="size-5 text-brand" />
          {detail.review_verdict === "correct" ? rightLabel : "Rewritten by HR"}
        </h2>
        <p className="mt-1 text-sm text-ink-soft">
          {[detail.reviewed_by && `By ${detail.reviewed_by}`, detail.reviewed_at && formatDateTime(detail.reviewed_at)]
            .filter(Boolean)
            .join(", ")}
        </p>
        {detail.review_answer && <p className="mt-4 leading-relaxed whitespace-pre-wrap text-ink">{detail.review_answer}</p>}
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="mt-4 text-sm font-semibold text-brand underline underline-offset-2 hover:text-brand-deep"
        >
          Change review
        </button>
      </section>
    );
  }

  return (
    <section aria-labelledby="review" className="rounded-2xl border border-line p-4 sm:p-5">
      <h2 id="review" className="text-lg font-bold">
        Your review
      </h2>
      <p className="mt-1 text-sm leading-relaxed text-ink-soft">
        Kept to test and improve the assistant. The employee doesn&apos;t see it, and it isn&apos;t added to what the
        assistant knows.
      </p>
      <button
        type="button"
        onClick={() => void save("correct")}
        disabled={busy !== null}
        className="mt-4 inline-flex items-center gap-2 rounded-full border border-line px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-brand-bright hover:bg-brand-wash disabled:opacity-60"
      >
        <CheckIcon className="size-4 text-brand" />
        {busy === "correct" ? "Saving…" : rightLabel}
      </button>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (answer.trim()) void save("corrected");
        }}
        className="mt-6"
      >
        <label htmlFor="review-answer" className="text-sm font-semibold text-ink">
          Or write the answer you&apos;d give
        </label>
        <textarea
          id="review-answer"
          rows={5}
          maxLength={5000}
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          className={`mt-2 ${FIELD}`}
        />
        {error && (
          <p role="alert" className="mt-3 rounded-2xl bg-alert-wash px-4 py-3 text-sm text-alert">
            {error}
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={busy !== null || !answer.trim()}
            className="rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-deep disabled:bg-muted disabled:text-ink-faint"
          >
            {busy === "corrected" ? "Saving…" : "Save your answer"}
          </button>
          {detail.review_verdict && (
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-full px-4 py-2.5 text-sm font-semibold text-ink-soft hover:bg-muted hover:text-ink"
            >
              Cancel
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
