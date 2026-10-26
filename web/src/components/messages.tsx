"use client";

import Markdown from "react-markdown";
import { documentTitle, sectionLabel } from "@/lib/documents";
import type { AssistantMessage, Source, UserMessage } from "@/lib/types";
import { AssistantMark } from "./assistant-mark";
import { ProgressSteps } from "./progress-steps";

export function UserBubble({ message }: { message: UserMessage }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-baltic-wash px-4 py-2.5 whitespace-pre-wrap text-ink">
        {message.text}
      </p>
    </div>
  );
}

export function AssistantReply({
  message,
  onRetry,
  onChooseHr,
}: {
  message: AssistantMessage;
  onRetry: () => void;
  onChooseHr: (askHr: boolean) => void;
}) {
  const working = message.status === "pending" || message.status === "streaming";

  return (
    <div className="flex gap-3">
      <AssistantMark active={working} />
      <div className="min-w-0 flex-1 pt-0.5">
        <ProgressSteps steps={message.steps} working={message.status === "pending"} />
        <ReplyBody message={message} onRetry={onRetry} onChooseHr={onChooseHr} />
      </div>
    </div>
  );
}

function ReplyBody({
  message,
  onRetry,
  onChooseHr,
}: {
  message: AssistantMessage;
  onRetry: () => void;
  onChooseHr: (askHr: boolean) => void;
}) {
  if (message.status === "pending") return null;

  if (message.status === "error") {
    return (
      <div className="rounded-lg border-l-4 border-alert bg-alert-wash px-4 py-3">
        <p className="font-medium text-alert">No answer this time</p>
        <p className="mt-1 text-sm text-ink">{message.text}</p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 text-sm font-medium text-baltic underline underline-offset-2"
        >
          Try again
        </button>
      </div>
    );
  }

  if (message.status === "done" && !message.answered) {
    return <NotFound message={message} onChooseHr={onChooseHr} />;
  }

  return (
    <div>
      <div className="answer">
        <Markdown>{message.text}</Markdown>
      </div>
      {message.status === "done" && message.sources.length > 0 && <SourceList sources={message.sources} />}
    </div>
  );
}

function NotFound({ message, onChooseHr }: { message: AssistantMessage; onChooseHr: (askHr: boolean) => void }) {
  return (
    <div>
      <p className="answer">{message.text}</p>

      {(message.hrStatus === "offered" || message.hrStatus === "sending") && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={message.hrStatus === "sending"}
            onClick={() => onChooseHr(true)}
            className="rounded-lg bg-baltic px-3.5 py-1.5 text-sm font-medium text-paper hover:bg-baltic-deep disabled:opacity-60"
          >
            {message.hrStatus === "sending" ? "Sending…" : "Yes, ask HR"}
          </button>
          <button
            type="button"
            disabled={message.hrStatus === "sending"}
            onClick={() => onChooseHr(false)}
            className="rounded-lg border border-birch bg-paper px-3.5 py-1.5 text-sm font-medium text-ink hover:border-baltic hover:text-baltic disabled:opacity-60"
          >
            No thanks
          </button>
          {message.hrStatus === "offered" && message.hrMessage && (
            <p className="w-full text-sm text-alert">{message.hrMessage}</p>
          )}
        </div>
      )}

      {message.hrStatus === "requested" && (
        <div className="mt-3 rounded-lg border-l-4 border-lamp-line bg-lamp-wash px-4 py-2.5">
          <p className="font-semibold text-lamp">Sent to HR</p>
          <p className="mt-0.5 text-sm text-ink">
            {message.hrMessage ?? "Your question was sent to the HR team."}
          </p>
        </div>
      )}

      {message.hrStatus === "declined" && (
        <p className="mt-3 text-sm text-ink-soft">{message.hrMessage ?? "Not sent to HR."}</p>
      )}
    </div>
  );
}

function SourceList({ sources }: { sources: Source[] }) {
  return (
    <div className="mt-4">
      <h3 className="text-sm text-ink-soft">
        From {sources.length === 1 ? "1 policy section" : `${sources.length} policy sections`}
      </h3>
      <ul className="mt-2 flex flex-wrap gap-2">
        {sources.map((source) => {
          const section = sectionLabel(source);
          return (
            <li
              key={source.chunk_id}
              className="max-w-full rounded-md border border-birch bg-paper px-3 py-1.5 text-sm sm:max-w-[22rem]"
            >
              <span className="block truncate font-medium text-baltic-deep">{documentTitle(source)}</span>
              {section && <span className="block truncate text-ink-soft">{section}</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
