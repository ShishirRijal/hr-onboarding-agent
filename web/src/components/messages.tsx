"use client";

import { useId, useState } from "react";
import Markdown, { type Components } from "react-markdown";
import { hasCitations, linkCitations } from "@/lib/citations";
import { documentTitle, sectionLabel } from "@/lib/documents";
import { formatDateTime } from "@/lib/format";
import type { AssistantMessage, HrReply, Rating, Source, UserMessage } from "@/lib/types";
import { usePacedCount, useSmoothText } from "@/lib/use-reveal";
import { AssistantMark } from "./assistant-mark";
import { ThumbDownIcon, ThumbUpIcon } from "./icons";
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
  onRate,
  onOpenSource,
}: {
  message: AssistantMessage;
  latest: boolean;
  openChunkId: string | null;
  onRetry: () => void;
  onChooseHr: (askHr: boolean) => void;
  onRate: (rating: Rating | null, comment?: string) => Promise<boolean>;
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
            onRate={onRate}
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
  onRate,
  onOpenSource,
}: {
  message: AssistantMessage;
  text: string;
  typing: boolean;
  openChunkId: string | null;
  onRetry: () => void;
  onChooseHr: (askHr: boolean) => void;
  onRate: (rating: Rating | null, comment?: string) => Promise<boolean>;
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

  const done = !typing && message.status === "done";
  return (
    <div>
      <AnswerText
        text={text}
        fullText={message.text}
        sources={message.sources}
        typing={typing}
        openChunkId={openChunkId}
        onOpenSource={onOpenSource}
      />
      {done && message.interactionId && (
        <FeedbackBar rating={message.feedback ?? null} onRate={onRate} />
      )}
    </div>
  );
}

// An answer with its citations as numbers that open their source. Answers without
// citations, from before they were added, list their sources underneath instead.
export function AnswerText({
  text,
  fullText = text,
  sources,
  typing = false,
  openChunkId,
  onOpenSource,
}: {
  text: string;
  // The whole answer, while `text` is still typing out.
  fullText?: string;
  sources: Source[];
  typing?: boolean;
  openChunkId: string | null;
  onOpenSource: (source: Source, opener: HTMLElement) => void;
}) {
  const components: Components = {
    a({ href, children }) {
      const number = Number(href?.match(/^#source-(\d+)$/)?.[1]);
      if (!number) return <a href={href}>{children}</a>;
      const source = sources[number - 1];
      return (
        <Citation
          number={number}
          source={source}
          open={!!source && source.chunk_id === openChunkId}
          onOpen={onOpenSource}
        />
      );
    },
  };

  return (
    <>
      <div className={`answer ${typing ? "is-typing" : ""}`}>
        <Markdown components={components}>{linkCitations(text, typing)}</Markdown>
      </div>
      {!hasCitations(fullText) && !typing && sources.length > 0 && (
        <SourceList sources={sources} openChunkId={openChunkId} onOpen={onOpenSource} />
      )}
    </>
  );
}

// Thumbs up or down under an answer. A thumbs down asks what was wrong; both go to HR's
// answer review without the employee's name.
function FeedbackBar({
  rating,
  onRate,
}: {
  rating: Rating | null;
  onRate: (rating: Rating | null, comment?: string) => Promise<boolean>;
}) {
  const [asking, setAsking] = useState(false);
  const [comment, setComment] = useState("");
  const [sending, setSending] = useState(false);
  const [thanked, setThanked] = useState(false);
  const commentId = useId();

  function choose(next: Rating) {
    // Choosing the same thumb again takes it back.
    const value = rating === next ? null : next;
    setAsking(value === "down");
    setThanked(value === "up");
    void onRate(value);
  }

  async function sendComment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSending(true);
    const saved = await onRate("down", comment.trim());
    setSending(false);
    if (saved) {
      setAsking(false);
      setThanked(true);
    }
  }

  const button = "rounded-lg p-1.5 transition-colors hover:bg-muted hover:text-ink";
  return (
    <div className="step-in mt-2">
      <div className="flex items-center gap-1 text-ink-soft">
        <button
          type="button"
          onClick={() => choose("up")}
          aria-pressed={rating === "up"}
          aria-label="Helpful"
          title="Helpful"
          className={`${button} ${rating === "up" ? "bg-brand-wash text-brand hover:bg-brand-wash hover:text-brand" : ""}`}
        >
          <ThumbUpIcon className="size-[1.125rem]" />
        </button>
        <button
          type="button"
          onClick={() => choose("down")}
          aria-pressed={rating === "down"}
          aria-label="Not helpful"
          title="Not helpful"
          className={`${button} ${rating === "down" ? "bg-muted text-ink" : ""}`}
        >
          <ThumbDownIcon className="size-[1.125rem]" />
        </button>
        {thanked && !asking && (
          <p role="status" className="ml-1 text-sm">
            Thanks. HR reviews answers without your name to improve them.
          </p>
        )}
      </div>

      {asking && (
        <form onSubmit={sendComment} className="mt-2 max-w-md">
          <label htmlFor={commentId} className="text-sm font-semibold text-ink">
            What was wrong? <span className="font-normal text-ink-soft">Optional</span>
          </label>
          <textarea
            id={commentId}
            rows={2}
            maxLength={1000}
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            className="mt-1.5 w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm leading-relaxed text-ink focus-visible:border-brand-bright focus-visible:ring-4 focus-visible:ring-brand-bright/15 focus-visible:outline-none"
          />
          <div className="mt-2 flex gap-2">
            <button
              type="submit"
              disabled={sending || !comment.trim()}
              className="rounded-full bg-brand px-3.5 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-brand-deep disabled:bg-muted disabled:text-ink-faint"
            >
              {sending ? "Sending…" : "Send feedback"}
            </button>
            <button
              type="button"
              onClick={() => {
                setAsking(false);
                setThanked(true);
              }}
              className="rounded-full px-3.5 py-1.5 text-sm font-semibold text-ink-soft hover:bg-muted hover:text-ink"
            >
              Skip
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function Citation({
  number,
  source,
  open,
  onOpen,
}: {
  number: number;
  source: Source | undefined;
  open: boolean;
  onOpen: (source: Source, opener: HTMLElement) => void;
}) {
  // The sources arrive with the finished answer, a moment after its text.
  if (!source) {
    return <span className="citation">{number}</span>;
  }
  const label = [documentTitle(source), sectionLabel(source)].filter(Boolean).join(", ");
  return (
    <button
      type="button"
      onClick={(event) => onOpen(source, event.currentTarget)}
      aria-pressed={open}
      aria-label={`Source ${number}: ${label}`}
      title={label}
      className="citation"
    >
      {number}
    </button>
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
            {message.hrMessage ?? "Your question is with the HR team. Their answer will appear in this chat."}
          </p>
        </div>
      )}

      {message.hrStatus === "answered" && message.hrReply && <HrReplyCard reply={message.hrReply} />}

      {message.hrStatus === "declined" && (
        <p className="step-in mt-3 text-sm text-ink-soft">{message.hrMessage ?? "Not sent to HR."}</p>
      )}
    </div>
  );
}

// HR's answer to a question the employee sent them, written in the HR inbox. Shown as
// HR typed it, under a reminder that the question went to HR.
function HrReplyCard({ reply }: { reply: HrReply }) {
  return (
    <div className="step-in mt-3">
      <p className="flex items-center gap-2 text-sm font-semibold text-lamp">
        <span className="size-2 rounded-full bg-lamp-line" aria-hidden="true" />
        Sent to HR
      </p>
      <div className="mt-2 rounded-2xl border border-line bg-surface px-4 py-3 shadow-[0_1px_3px_rgb(6_26_55/0.06)]">
        <h3 className="flex flex-wrap items-baseline gap-x-2 text-sm">
          <span className="font-semibold text-ink">Answer from HR</span>
          <span className="text-ink-soft">
            {[reply.by, reply.at ? formatDateTime(reply.at) : null].filter(Boolean).join(" · ")}
          </span>
        </h3>
        <p className="mt-1.5 leading-relaxed whitespace-pre-wrap text-ink">{reply.text}</p>
      </div>
    </div>
  );
}

export function SourceList({
  sources,
  openChunkId,
  onOpen,
}: {
  sources: Source[];
  openChunkId: string | null;
  onOpen: (source: Source, opener: HTMLElement) => void;
}) {
  // Answers HR wrote in the HR inbox aren't policy sections.
  const noun = sources.some((source) => source.source_doc === "hr_answers") ? "source" : "policy section";
  return (
    <div className="step-in mt-4">
      <h3 className="text-sm text-ink-soft">
        From {sources.length === 1 ? `1 ${noun}` : `${sources.length} ${noun}s`}
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
