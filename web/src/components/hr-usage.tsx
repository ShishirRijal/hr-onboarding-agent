"use client";

import { useEffect, useState } from "react";
import { ApiError, fetchUsageReport } from "@/lib/api";
import type { UsagePeriodKey, UsageReport, UsageRow } from "@/lib/types";
import { formatCompact, formatNumber, formatUsd } from "@/lib/usage";
import { HrPage } from "./hr-inbox";

const PERIODS: { value: UsagePeriodKey; label: string }[] = [
  { value: "day", label: "Today" },
  { value: "week", label: "This week" },
  { value: "month", label: "This month" },
  { value: "year", label: "This year" },
];

// The agent steps that call a model, in words for HR.
const STEPS: Record<string, string> = {
  remember_conversation: "Summarising long chats",
  understand_message: "Understanding the message",
  reply_in_chat: "Small talk replies",
  generate_answer: "Writing the answer",
  check_answer: "Checking the answer",
  revise_answer: "Rewriting the answer",
  grade_documents: "Grading the found sections",
  search_again: "Grading the second search",
  evaluation_judge: "Grading evaluation answers",
  other: "Other",
};

const SOURCES: Record<string, string> = {
  chat: "Employees' questions",
  evaluation: "Evaluation runs",
  script: "Command-line questions",
};

// The meter turns amber, then red, as the month's spend nears the limit.
const WARN_AT = 0.8;

// What the assistant's OpenAI calls cost, from the tokens each call used.
export function HrUsage() {
  const [period, setPeriod] = useState<UsagePeriodKey>("month");
  const [result, setResult] = useState<{ period: UsagePeriodKey; report?: UsageReport; error?: string } | null>(null);
  const loaded = result?.period === period ? result : null;
  // The headline numbers don't depend on the chosen period, so they stay while it changes.
  const [latest, setLatest] = useState<UsageReport | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchUsageReport(period)
      .then((report) => {
        if (cancelled) return;
        setResult({ period, report });
        setLatest(report);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setResult({ period, error: error instanceof ApiError ? error.message : "Usage couldn't be loaded." });
      });
    return () => {
      cancelled = true;
    };
  }, [period]);

  return (
    <HrPage
      title="Usage"
      intro="What the assistant's OpenAI calls cost, counted from the tokens each call used at OpenAI's list prices. Your OpenAI bill is the final word; this shows where the money goes."
    >
      {!latest ? (
        <p className={`mt-8 ${result?.error ? "text-ink" : "pending text-ink-soft"}`}>
          {result?.error ?? "Loading usage…"}
        </p>
      ) : (
        <>
          <MonthAndBudget report={latest} />
          <section aria-label="Other periods" className="mt-3 grid gap-3 sm:grid-cols-3">
            {latest.periods
              .filter((item) => item.key !== "month")
              .map((item) => (
                <div key={item.key} className="rounded-2xl bg-muted p-4">
                  <p className="text-sm font-semibold text-ink">{item.label}</p>
                  <p className="mt-1 text-3xl font-bold tracking-tight text-ink">{formatUsd(item.cost_usd)}</p>
                  <p className="mt-1 text-sm text-ink-soft">
                    {formatCompact(item.input_tokens + item.output_tokens)} tokens ·{" "}
                    {item.questions === 1 ? "1 question" : `${item.questions} questions`}
                  </p>
                </div>
              ))}
          </section>

          <section aria-labelledby="breakdown" className="mt-12">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 id="breakdown" className="text-lg font-bold">
                Where it goes
              </h2>
              <div role="group" aria-label="Period" className="flex flex-wrap gap-1.5">
                {PERIODS.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    onClick={() => setPeriod(item.value)}
                    aria-pressed={item.value === period}
                    className={`rounded-full px-3.5 py-1.5 text-sm transition-colors ${
                      item.value === period ? "bg-ink font-semibold text-white" : "bg-muted text-ink hover:bg-line"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {!loaded ? (
              <p className="pending mt-4 text-ink-soft">Loading…</p>
            ) : loaded.error || !loaded.report ? (
              <p className="mt-4 text-ink">{loaded.error}</p>
            ) : (
              <Breakdown report={loaded.report} />
            )}
          </section>

          <Prices report={latest} />
        </>
      )}
    </HrPage>
  );
}

function MonthAndBudget({ report }: { report: UsageReport }) {
  const month = report.periods.find((item) => item.key === "month");
  const { monthly_limit_usd: limit, spent_usd: spent, remaining_usd: remaining } = report.budget;
  const share = limit ? Math.min(spent / limit, 1) : 0;
  const state = !limit ? null : share >= 1 ? "reached" : share >= WARN_AT ? "near" : "ok";
  const fill = { ok: "bg-brand", near: "bg-lamp-line", reached: "bg-alert" };
  const track = { ok: "bg-brand-wash", near: "bg-lamp-wash", reached: "bg-alert-wash" };

  return (
    <section aria-labelledby="month" className="mt-8 rounded-2xl border border-line p-5">
      <h2 id="month" className="text-sm font-semibold text-ink">
        This month
      </h2>
      <p className="mt-1 text-5xl font-bold tracking-tight text-ink">{formatUsd(spent)}</p>
      {month && (
        <p className="mt-1 text-sm text-ink-soft">
          {formatNumber(month.input_tokens + month.output_tokens)} tokens in {formatNumber(month.calls)} model calls,
          for {month.questions === 1 ? "1 question" : `${formatNumber(month.questions)} questions`}
        </p>
      )}

      {limit && state ? (
        <div className="mt-5">
          <div
            role="meter"
            aria-label="Monthly limit used"
            aria-valuemin={0}
            aria-valuemax={limit}
            aria-valuenow={Math.min(spent, limit)}
            aria-valuetext={`${formatUsd(spent)} of ${formatUsd(limit)}`}
            className={`h-2 overflow-hidden rounded-full ${track[state]}`}
          >
            <div className={`h-full rounded-full ${fill[state]}`} style={{ width: `${Math.max(share * 100, spent > 0 ? 1 : 0)}%` }} />
          </div>
          <p className="mt-2 text-sm text-ink">
            <span className="font-semibold">
              {Math.round(share * 100)}% of the {formatUsd(limit)} monthly limit
            </span>
            {state === "reached"
              ? ". The assistant has stopped answering until next month and points employees to HR."
              : `, ${formatUsd(remaining ?? 0)} left. When it runs out, the assistant stops answering until next month.`}
          </p>
        </div>
      ) : (
        <p className="mt-4 rounded-xl bg-muted px-3.5 py-2.5 text-sm text-ink-soft">
          No monthly limit. Set <code className="text-ink">MONTHLY_BUDGET_USD</code> in the API&apos;s settings to stop
          the assistant once a month&apos;s calls cost that much.
        </p>
      )}
    </section>
  );
}

function Breakdown({ report }: { report: UsageReport }) {
  const chosen = report.periods.find((item) => item.key === report.period);
  if (!chosen || chosen.calls === 0) {
    return (
      <p className="mt-4 rounded-2xl border border-dashed border-line px-4 py-6 text-center text-ink-soft">
        No model calls {chosen ? chosen.label.toLowerCase() : "in this period"}.
      </p>
    );
  }

  return (
    <div className="mt-4 space-y-8">
      {report.questions > 0 && report.average_cost_per_question_usd != null && (
        <p className="text-ink">
          An employee&apos;s question takes{" "}
          <span className="font-semibold">{formatNumber(report.average_tokens_per_question ?? 0)} tokens</span> and costs{" "}
          <span className="font-semibold">{formatUsd(report.average_cost_per_question_usd)}</span> on average, over{" "}
          {report.questions === 1 ? "1 question" : `${formatNumber(report.questions)} questions`}.
        </p>
      )}
      <UsageTable title="By model" rows={report.by_model} label={(name) => name} detail />
      <UsageTable title="By step" rows={report.by_step} label={(name) => STEPS[name] ?? name} />
      <UsageTable title="By source" rows={report.by_source} label={(name) => SOURCES[name] ?? name} />
      {chosen.unpriced_calls > 0 && (
        <p className="text-sm text-ink-soft">
          {chosen.unpriced_calls} calls used a model without a known price and aren&apos;t in the cost.
        </p>
      )}
    </div>
  );
}

function UsageTable({
  title,
  rows,
  label,
  detail = false,
}: {
  title: string;
  rows: UsageRow[];
  label: (name: string) => string;
  // Input and output tokens separately, where prices differ between them.
  detail?: boolean;
}) {
  const total = rows.reduce((sum, row) => sum + row.cost_usd, 0);
  const head = "px-3 py-2 text-left text-xs font-semibold text-ink-soft";
  const cell = "px-3 py-2.5 tabular-nums";

  return (
    <section aria-label={title}>
      <h3 className="font-semibold text-ink">{title}</h3>
      <div className="mt-2 overflow-x-auto rounded-2xl border border-line">
        <table className="w-full min-w-[34rem] border-collapse text-sm">
          <thead className="bg-muted">
            <tr>
              <th scope="col" className={head}>
                {title.replace("By ", "").replace(/^./, (letter) => letter.toUpperCase())}
              </th>
              <th scope="col" className={`${head} text-right`}>
                Calls
              </th>
              {detail ? (
                <>
                  <th scope="col" className={`${head} text-right`}>
                    Input tokens
                  </th>
                  <th scope="col" className={`${head} text-right`}>
                    Output tokens
                  </th>
                </>
              ) : (
                <th scope="col" className={`${head} text-right`}>
                  Tokens
                </th>
              )}
              <th scope="col" className={`${head} text-right`}>
                Cost
              </th>
              <th scope="col" className={`${head} w-40`}>
                Share of cost
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const share = total > 0 ? row.cost_usd / total : 0;
              return (
                <tr key={row.name} className="border-t border-line">
                  <th scope="row" className="px-3 py-2.5 text-left font-normal text-ink">
                    {label(row.name)}
                  </th>
                  <td className={`${cell} text-right text-ink`}>{formatNumber(row.calls)}</td>
                  {detail ? (
                    <>
                      <td className={`${cell} text-right text-ink`}>{formatNumber(row.input_tokens)}</td>
                      <td className={`${cell} text-right text-ink`}>{formatNumber(row.output_tokens)}</td>
                    </>
                  ) : (
                    <td className={`${cell} text-right text-ink`}>
                      {formatNumber(row.input_tokens + row.output_tokens)}
                    </td>
                  )}
                  <td className={`${cell} text-right font-semibold text-ink`}>{formatUsd(row.cost_usd)}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2" title={`${Math.round(share * 100)}% of the cost`}>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-brand-wash" aria-hidden="true">
                        <div className="h-full rounded-full bg-brand" style={{ width: `${share * 100}%` }} />
                      </div>
                      <span className="w-9 text-right text-xs text-ink-soft tabular-nums">{Math.round(share * 100)}%</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Prices({ report }: { report: UsageReport }) {
  return (
    <details className="mt-12 text-sm">
      <summary className="cursor-pointer font-semibold text-ink">Prices used</summary>
      <p className="mt-2 text-ink-soft">
        OpenAI&apos;s list prices in US dollars per million tokens. Repeated prompt text is billed at the cached price.
      </p>
      <div className="mt-2 overflow-x-auto rounded-2xl border border-line">
        <table className="w-full min-w-[28rem] border-collapse">
          <thead className="bg-muted">
            <tr className="text-xs text-ink-soft">
              <th scope="col" className="px-3 py-2 text-left font-semibold">
                Model
              </th>
              <th scope="col" className="px-3 py-2 text-right font-semibold">
                Input
              </th>
              <th scope="col" className="px-3 py-2 text-right font-semibold">
                Cached input
              </th>
              <th scope="col" className="px-3 py-2 text-right font-semibold">
                Output
              </th>
            </tr>
          </thead>
          <tbody>
            {report.prices.map((price) => (
              <tr key={price.model} className="border-t border-line tabular-nums text-ink">
                <th scope="row" className="px-3 py-2 text-left font-normal">
                  {price.model}
                </th>
                <td className="px-3 py-2 text-right">${price.input_usd.toFixed(3)}</td>
                <td className="px-3 py-2 text-right">${price.cached_input_usd.toFixed(3)}</td>
                <td className="px-3 py-2 text-right">${price.output_usd.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
