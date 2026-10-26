"use client";

import { useState } from "react";
import { documentTitleById } from "@/lib/documents";
import type { ProgressStep } from "@/lib/types";
import { CheckIcon, ChevronIcon } from "./icons";

function StepList({ steps, working }: { steps: ProgressStep[]; working: boolean }) {
  return (
    <ol className="space-y-1.5">
      {steps.map((step, index) => {
        const current = working && index === steps.length - 1;
        const documents = (step.documents ?? []).map(documentTitleById);
        return (
          <li key={`${step.stage}-${index}`} className="flex gap-2 text-sm">
            <span className="mt-0.5 grid size-4 shrink-0 place-items-center">
              {current ? (
                <span className="size-1.5 rounded-full bg-baltic" />
              ) : (
                <CheckIcon className="size-4 text-baltic" />
              )}
            </span>
            <span className="min-w-0">
              <span className={current ? "shimmer" : "text-ink-soft"}>{step.label}</span>
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

// While the assistant works, the steps are shown live. Once text arrives they fold
// into a one-line summary that can be reopened.
export function ProgressSteps({ steps, working }: { steps: ProgressStep[]; working: boolean }) {
  const [open, setOpen] = useState(false);

  if (working) {
    if (steps.length === 0) {
      return <p className="shimmer text-sm">Sending your question</p>;
    }
    return <StepList steps={steps} working />;
  }

  if (steps.length === 0) return null;
  const reading = steps.find((step) => step.stage === "reading");
  const summary = reading ? reading.label.replace("Reading", "Read") : "How I looked for this";

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex items-center gap-1 text-sm text-ink-soft hover:text-baltic"
      >
        {summary}
        <ChevronIcon className={`size-4 transition-transform ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <div className="mt-2 border-l border-birch pl-3">
          <StepList steps={steps} working={false} />
        </div>
      )}
    </div>
  );
}
