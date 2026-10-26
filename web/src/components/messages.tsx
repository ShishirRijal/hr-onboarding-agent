"use client";

import { useState } from "react";
import Markdown from "react-markdown";
import { documentTitle, sectionLabel } from "@/lib/documents";
import type { AssistantMessage, Source, UserMessage } from "@/lib/types";
import { usePacedCount, useSmoothText } from "@/lib/use-reveal";
import { AssistantMark } from "./assistant-mark";
import { ProgressSteps } from "./progress-steps";

export function UserBubble({ message }: { message: UserMessage }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] rounded-3xl rounded-br-lg bg-brand-wash px-4 py-2.5 whitespace-pre-wrap text-ink">
        {message.text}
      </p>
    </div>
  );
}

// How long each progress step stays current before the next one, or the answer, takes over.
const STEP_MS = 650;

export function AssistantReply({
  message,
  latest,
  openChunkId,
  onRetry,
  onChooseHr,
  onOpenSource,
}: {
  message: AssistantMessage;
  latest: boolean;
  openChunkId: string | null;
  onRetry: () => void;
  onChooseHr: (askHr: boolean) => void;
  onOpenSource: (source: Source, opener: HTMLElement) => void;
}) {
  // Replies loaded from history appear as they are; only replies written now are animated.
  const [live] = useState(() => message.status === "pending" || message.status === "streaming");
  const [startedAt] = useState(() => Date.now());

  // The answer counts as one more step, so it waits until the last step has been seen.
  const hasText = message.status !== "pending";
  const shown = usePacedCount(message.steps.length + (hasText ? 1 : 0), STEP_MS);
  const thinking = live && message.status !== "error" && (!hasText || shown <= message.steps.length);

  const text = useSmoothText(thinking ? "" : message.text, live && message.status !== "error");
  const typing = !thinking && (message.status === "streaming" || text.length < message.text.length);

  return (
    <div className="flex gap-3">
      <AssistantMark state={thinking || typing ? "working" : latest ? "idle" : "still"} />
      <div className="min-w-0 flex-1 pt-0.5">
        <ProgressSteps
          steps={live ? message.steps.slice(0, shown) : message.steps}
          working={thinking}
          startedAt={startedAt}
        />
        {!thinking && (
          <ReplyBody
            message={message}
            text={text}
            typing={typing}
            openChunkId={openChunkId}
            onRetry={onRetry}
            onChooseHr={onChooseHr}
            onOpenSource={onOpenSource}
          />
        )}
      </div>
    </div>
  );
}

function ReplyBody({
  message,
  text,
  typing,
  openChunkId,
  onRetry,
  onChooseHr,
  onOpenSource,
}: {
  message: AssistantMessage;
  text: string;
  typing: boolean;
  openChunkId: string | null;
  onRetry: () => void;
  onChooseHr: (askHr: boolean) => void;
  onOpenSource: (source: Source, opener: HTMLElement) => void;
}) {
  if (message.status === "error") {
    return (
      <div className="rounded-2xl bg-alert-wash px-4 py-3">
        <p className="font-semibold text-alert">No answer this time</p>
        <p className="mt-1 text-sm text-ink">{message.text}</p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 text-sm font-semibold text-brand underline underline-offset-2"
        >
          Try again
        </button>
      </div>
    );
  }

  if (message.status === "done" && !message.answered) {
    return <NotFound message={message} text={text} typing={typing} onChooseHr={onChooseHr} />;
  }

  return (
    <div>
      <div className={`answer ${typing ? "is-typing" : ""}`}>
        <Markdown>{text}</Markdown>
      </div>
      {!typing && message.status === "done" && message.sources.length > 0 && (
        <SourceList sources={message.sources} openChunkId={openChunkId} onOpen={onOpenSource} />
      )}
    </div>
  );
}

function NotFound({
  message,
  text,
  typing,
  onChooseHr,
}: {
  message: AssistantMessage;
  text: string;
  typing: boolean;
  onChooseHr: (askHr: boolean) => void;
}) {
  return (
    <div>
      <div className={`answer ${typing ? "is-typing" : ""}`}>
        <p>{text}</p>
      </div>

      {!typing && (message.hrStatus === "offered" || message.hrStatus === "sending") && (
        <div className="step-in mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={message.hrStatus === "sending"}
            onClick={() => onChooseHr(true)}
            className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-deep disabled:opacity-60"
          >
            {message.hrStatus === "sending" ? "Sending…" : "Yes, ask HR"}
          </button>
          <button
            type="button"
            disabled={message.hrStatus === "sending"}
            onClick={() => onChooseHr(false)}
            className="rounded-full bg-muted px-4 py-2 text-sm font-semibold text-ink transition-colors hover:bg-line disabled:opacity-60"
          >
            No thanks
          </button>
          {message.hrStatus === "offered" && message.hrMessage && (
            <p className="w-full text-sm text-alert">{message.hrMessage}</p>
          )}
        </div>
      )}

      {message.hrStatus === "requested" && (
        <div className="step-in mt-3 rounded-2xl bg-lamp-wash px-4 py-3">
          <p className="flex items-center gap-2 font-semibold text-lamp">
            <span className="size-2 rounded-full bg-lamp-line" aria-hidden="true" />
            Sent to HR
          </p>
          <p className="mt-0.5 text-sm text-ink">
            {message.hrMessage ?? "Your question goes to the HR team in their end-of-day summary."}
          </p>
        </div>
      )}

      {message.hrStatus === "declined" && (
        <p className="step-in mt-3 text-sm text-ink-soft">{message.hrMessage ?? "Not sent to HR."}</p>
      )}
    </div>
  );
}

function SourceList({
  sources,
  openChunkId,
  onOpen,
}: {
  sources: Source[];
  openChunkId: string | null;
  onOpen: (source: Source, opener: HTMLElement) => void;
}) {
  return (
    <div className="step-in mt-4">
      <h3 className="text-sm text-ink-soft">
        From {sources.length === 1 ? "1 policy section" : `${sources.length} policy sections`}
      </h3>
      <ul className="mt-2 flex flex-wrap gap-2">
        {sources.map((source) => {
          const section = sectionLabel(source);
          const open = source.chunk_id === openChunkId;
          return (
            <li key={source.chunk_id} className="max-w-full sm:max-w-[22rem]">
              <button
                type="button"
                onClick={(event) => onOpen(source, event.currentTarget)}
                aria-pressed={open}
                title="Open this section in the document"
                className={`block w-full rounded-xl border px-3 py-2 text-left text-sm transition-colors ${
                  open ? "border-brand-bright bg-brand-wash" : "border-line bg-surface hover:border-brand-bright"
                }`}
              >
                <span className="block truncate font-semibold text-ink">{documentTitle(source)}</span>
                {section && <span className="block truncate text-ink-soft">{section}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
