"use client";

import { useRef, useState } from "react";
import { SendIcon } from "./icons";

const MAX_LENGTH = 2000;

export function Composer({ disabled, onSend }: { disabled: boolean; onSend: (text: string) => void }) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = !disabled && text.trim().length > 0;

  function submit() {
    if (!canSend) return;
    onSend(text.trim());
    setText("");
    if (textareaRef.current) textareaRef.current.style.height = "";
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="flex items-end gap-2 rounded-[1.75rem] border border-line bg-surface p-2 pl-5 shadow-[0_4px_16px_rgb(6_26_55/0.06)] transition-[border-color,box-shadow] focus-within:border-brand-bright focus-within:ring-4 focus-within:ring-brand-bright/15"
    >
      <label htmlFor="message" className="sr-only">
        Your question
      </label>
      <textarea
        id="message"
        ref={textareaRef}
        rows={1}
        value={text}
        maxLength={MAX_LENGTH}
        placeholder="Ask an HR question"
        onChange={(event) => {
          setText(event.target.value);
          event.target.style.height = "";
          event.target.style.height = `${Math.min(event.target.scrollHeight, 200)}px`;
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
        className="max-h-[200px] flex-1 resize-none bg-transparent py-1.5 leading-relaxed outline-none placeholder:text-ink-faint focus-visible:outline-none"
      />
      <button
        type="submit"
        disabled={!canSend}
        aria-label="Send"
        className="grid size-10 shrink-0 place-items-center rounded-full bg-brand text-white transition-colors hover:bg-brand-deep disabled:bg-muted disabled:text-ink-faint"
      >
        <SendIcon className="size-5" />
      </button>
    </form>
  );
}
