"use client";

import { useState } from "react";
import { documentTitleById } from "@/lib/documents";
import type { ProgressStep } from "@/lib/types";
import { useElapsedSeconds } from "@/lib/use-reveal";
import { CheckIcon, ChevronIcon } from "./icons";

function StepList({ steps, working, elapsed }: { steps: ProgressStep[]; working: boolean; elapsed: number }) {
  return (
    <ol className="space-y-1.5">
      {steps.map((step, index) => {
        const current = working && index === steps.length - 1;
        const documents = (step.documents ?? []).map(documentTitleById);
        return (
          <li key={`${step.stage}-${index}`} className={`flex gap-2 text-sm ${working ? "step-in" : ""}`}>
            <span className="mt-0.5 grid size-4 shrink-0 place-items-center">
              {current ? (
                <span className="spinner" />
              ) : (
                <CheckIcon className={`size-4 text-baltic ${working ? "check-draw" : ""}`} />
              )}
            </span>
            <span className="min-w-0">
              <span className={current ? "shimmer" : "text-ink-soft"}>{step.label}</span>
              {current && elapsed > 0 && <span className="ml-2 text-xs text-ink-faint tabular-nums">{elapsed}s</span>}
              {documents.length > 0 && (
                <span className="block truncate text-xs text-ink-faint">{documents.join(", ")}</span>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

// While the assistant works, the steps are shown live. Once the answer starts they fold
// into a one-line summary that can be reopened.
export function ProgressSteps({
  steps,
  working,
  startedAt,
}: {
  steps: ProgressStep[];
  working: boolean;
  startedAt: number;
}) {
  const [open, setOpen] = useState(false);
  const elapsed = useElapsedSeconds(startedAt, working);

  if (working && steps.length === 0) {
    return (
      <p className="step-in flex items-center gap-2 text-sm">
        <span className="grid size-4 place-items-center">
          <span className="spinner" />
        </span>
        <span className="shimmer">Sending your question</span>
      </p>
    );
  }
  if (steps.length === 0) return null;

  const reading = steps.find((step) => step.stage === "reading");
  const summary = reading ? reading.label.replace("Reading", "Read") : "How I looked for this";

  return (
    <div className="mb-3">
      {!working && (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="step-in flex items-center gap-1 text-sm text-ink-soft hover:text-baltic"
        >
          {summary}
          <ChevronIcon className={`size-4 transition-transform ${open ? "rotate-90" : ""}`} />
        </button>
      )}
      <div className={`fold ${working || open ? "is-open" : ""}`}>
        <div className="min-h-0 overflow-hidden">
          <div className={`border-l border-birch pl-3 ${working ? "" : "mt-2"}`}>
            <StepList steps={steps} working={working} elapsed={elapsed} />
          </div>
        </div>
      </div>
    </div>
  );
}
