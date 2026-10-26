"use client";

import Markdown from "react-markdown";
import { documentTitle, sectionLabel } from "@/lib/documents";
import type { AssistantMessage, Source, UserMessage } from "@/lib/types";

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
}: {
  message: AssistantMessage;
  onRetry: () => void;
}) {
  if (message.status === "pending") {
    return <p className="pending text-ink-soft">Checking NordTech policies…</p>;
  }

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

  if (message.escalated) {
    return (
      <div className="rounded-lg border-l-4 border-lamp-line bg-lamp-wash px-4 py-3">
        <p className="font-semibold text-lamp">Sent to HR</p>
        <p className="mt-1 text-ink">{message.text}</p>
      </div>
    );
  }

  return (
    <div>
      <div className="answer">
        <Markdown>{message.text}</Markdown>
      </div>
      {message.sources.length > 0 && <SourceList sources={message.sources} />}
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
