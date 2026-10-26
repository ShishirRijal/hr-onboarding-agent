"use client";

import { useEffect, useRef, useState } from "react";

// Shows items one at a time, each at least `stepMs` after the previous one, so updates
// that arrive in a burst still read as a sequence. Returns how many to show.
export function usePacedCount(target: number, stepMs: number): number {
  const [count, setCount] = useState(0);
  const shownAt = useRef(0);

  if (target < count) setCount(target);

  useEffect(() => {
    if (count >= target) return;
    const wait = count === 0 ? 0 : Math.max(0, shownAt.current + stepMs - Date.now());
    const timer = setTimeout(() => {
      shownAt.current = Date.now();
      setCount((value) => value + 1);
    }, wait);
    return () => clearTimeout(timer);
  }, [count, target, stepMs]);

  return Math.min(count, target);
}

// Characters revealed per animation frame: faster when far behind, never slower than a
// comfortable reading pace.
const MIN_CHARS_PER_FRAME = 1.2;
const MAX_CHARS_PER_FRAME = 9;
const CATCH_UP_FRAMES = 45;

// Reveals `text` word by word at a steady pace instead of in network-sized bursts.
// When `animate` is false the full text is returned straight away.
export function useSmoothText(text: string, animate: boolean): string {
  const [length, setLength] = useState(animate ? 0 : text.length);
  const position = useRef(length);

  useEffect(() => {
    if (!animate) return;
    let frame = 0;
    const tick = () => {
      // A retry starts the text over.
      if (position.current > text.length) position.current = 0;
      const backlog = text.length - position.current;
      if (backlog <= 0) return;
      const step = Math.min(MAX_CHARS_PER_FRAME, Math.max(MIN_CHARS_PER_FRAME, backlog / CATCH_UP_FRAMES));
      let next = Math.min(text.length, position.current + step);
      // Finish the word being typed so text never stops mid-word.
      const wordEnd = text.slice(Math.floor(next)).search(/\s/);
      if (wordEnd > 0) next = Math.floor(next) + wordEnd;
      position.current = next;
      setLength(Math.floor(next));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [text, animate]);

  return animate ? closeOpenMarkdown(text.slice(0, Math.min(length, text.length))) : text;
}

// A half-revealed "**bold" would render as literal asterisks; close it until the rest arrives.
function closeOpenMarkdown(text: string): string {
  let closed = text;
  if ((closed.match(/\*\*/g)?.length ?? 0) % 2 === 1) closed += "**";
  if ((closed.match(/`/g)?.length ?? 0) % 2 === 1) closed += "`";
  return closed;
}

// Whole seconds since `since`, ticking while `running`.
export function useElapsedSeconds(since: number, running: boolean): number {
  const [now, setNow] = useState(since);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);

  return Math.max(0, Math.floor((now - since) / 1000));
}
