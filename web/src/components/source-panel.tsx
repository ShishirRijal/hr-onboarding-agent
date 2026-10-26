"use client";

import { useEffect, useMemo, useRef, useState, type ElementType, type HTMLAttributes } from "react";
import Markdown, { type Components, type ExtraProps } from "react-markdown";
import remarkGfm from "remark-gfm";
import { ApiError, fetchSourcePassage } from "@/lib/api";
import { documentTitle, sectionLabel } from "@/lib/documents";
import type { Source, SourcePassage } from "@/lib/types";
import { CloseIcon } from "./icons";

type Span = { start: number; end: number };

// Blocks are marked when they overlap the cited span. Lists and tables are marked per item
// and per row, so a passage from the middle of a long list doesn't light up the whole list.
const CITABLE = ["p", "li", "h1", "h2", "h3", "h4", "tr", "pre", "blockquote"] as const;

function citedBlock(tag: (typeof CITABLE)[number], span: Span | null) {
  const Tag = tag as ElementType;
  return function CitedBlock({ node, className, ...props }: HTMLAttributes<HTMLElement> & ExtraProps) {
    const start = node?.position?.start.offset;
    const end = node?.position?.end.offset;
    const cited = span != null && start != null && end != null && start < span.end && end > span.start;
    return <Tag {...props} className={cited ? `${className ?? ""} cited`.trim() : className} data-cited={cited || undefined} />;
  };
}

function citedComponents(span: Span | null): Components {
  return Object.fromEntries(CITABLE.map((tag) => [tag, citedBlock(tag, span)])) as Components;
}

function spanOf(passage: SourcePassage): Span | null {
  const { highlight_start: start, highlight_end: end } = passage;
  return start != null && end != null ? { start, end } : null;
}

// Scrolls the first highlighted block to the upper part of the panel.
function scrollToCited(body: HTMLElement | null, smooth: boolean) {
  const first = body?.querySelector("[data-cited]");
  if (!body || !first) return;
  const offset = first.getBoundingClientRect().top - body.getBoundingClientRect().top + body.scrollTop;
  body.scrollTo({ top: Math.max(0, offset - body.clientHeight / 4), behavior: smooth ? "smooth" : "instant" });
}

// The document a source came from, opened beside the chat with the part the answer used
// highlighted and scrolled into view.
export function SourcePanel({ source, onClose }: { source: Source; onClose: () => void }) {
  const [result, setResult] = useState<{ chunkId: string; passage?: SourcePassage; error?: string } | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const loaded = result?.chunkId === source.chunk_id ? result : null;
  const title = documentTitle(source);
  const section = sectionLabel(source);
  const span = loaded?.passage ? spanOf(loaded.passage) : null;
  const components = useMemo(
    () => citedComponents(span),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the span's offsets are its identity
    [span?.start, span?.end],
  );

  useEffect(() => {
    let cancelled = false;
    fetchSourcePassage(source.chunk_id)
      .then((passage) => !cancelled && setResult({ chunkId: source.chunk_id, passage }))
      .catch((error: unknown) => {
        if (cancelled) return;
        const message = error instanceof ApiError ? error.message : "This source couldn't be opened.";
        setResult({ chunkId: source.chunk_id, error: message });
      });
    return () => {
      cancelled = true;
    };
  }, [source.chunk_id]);

  // Focus moves into the panel and Escape closes it.
  useEffect(() => {
    headingRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  useEffect(() => {
    if (loaded?.passage) scrollToCited(bodyRef.current, false);
  }, [loaded?.passage]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end lg:static lg:z-auto" role="dialog" aria-label={title}>
      <button
        type="button"
        className="absolute inset-0 bg-ink/30 lg:hidden"
        aria-label="Close source"
        onClick={onClose}
      />
      <aside className="source-panel relative flex h-full w-full max-w-[36rem] flex-col border-l border-birch bg-paper shadow-xl lg:w-[30rem] lg:shadow-none xl:w-[36rem]">
        <header className="flex items-start gap-3 border-b border-birch px-5 py-4">
          <div className="min-w-0 flex-1">
            <h2 ref={headingRef} tabIndex={-1} className="truncate font-semibold text-ink">
              {title}
            </h2>
            {section && <p className="truncate text-sm text-ink-soft">{section}</p>}
            {span && (
              <button
                type="button"
                onClick={() => scrollToCited(bodyRef.current, true)}
                className="mt-2 flex items-center gap-2 text-sm text-baltic hover:text-baltic-deep"
              >
                <span className="h-3.5 w-[3px] rounded-full bg-baltic" aria-hidden="true" />
                Show the part used for this answer
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="-mr-1.5 rounded-md p-1.5 text-ink-soft hover:bg-ice"
            aria-label="Close source"
          >
            <CloseIcon className="size-5" />
          </button>
        </header>

        <div ref={bodyRef} className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7">
          {!loaded && <p className="shimmer text-sm">Opening {title}</p>}
          {loaded?.error && (
            <p className="text-sm text-ink">{loaded.error}</p>
          )}
          {loaded?.passage && (
            <div className="answer document">
              <Markdown remarkPlugins={[remarkGfm]} components={components}>
                {loaded.passage.content}
              </Markdown>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
