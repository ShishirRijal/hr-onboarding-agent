"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchSessionMessages, sendMessage } from "@/lib/api";
import { useAppState } from "@/lib/app-state";
import type { AssistantMessage, ChatMessage, SessionMessage } from "@/lib/types";
import { Composer } from "./composer";
import { EmptyState } from "./empty-state";
import { AssistantReply, UserBubble } from "./messages";

function historyToMessages(history: SessionMessage[]): ChatMessage[] {
  return history.flatMap((item) => [
    { id: `${item.interaction_id}-q`, role: "user" as const, text: item.question },
    {
      id: item.interaction_id,
      role: "assistant" as const,
      question: item.question,
      status: "done" as const,
      text: item.answer,
      sources: item.sources,
      confidenceLabel: item.confidence_label,
      escalated: item.escalated,
    },
  ]);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong while getting an answer.";
}

export function ChatView({ sessionId }: { sessionId: string | null }) {
  const { office, saveSession, setActiveSessionId } = useAppState();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [historyState, setHistoryState] = useState<"loading" | "ready" | "error">(
    sessionId ? "loading" : "ready",
  );
  const sessionIdRef = useRef(sessionId);
  const endRef = useRef<HTMLDivElement>(null);
  const pending = messages.some((message) => message.role === "assistant" && message.status === "pending");

  useEffect(() => {
    setActiveSessionId(sessionId);
  }, [sessionId, setActiveSessionId]);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    fetchSessionMessages(sessionId)
      .then((history) => {
        if (cancelled) return;
        setMessages(historyToMessages(history));
        setHistoryState("ready");
      })
      .catch(() => {
        if (!cancelled) setHistoryState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const updateAssistant = useCallback((id: string, patch: Partial<AssistantMessage>) => {
    setMessages((current) =>
      current.map((message) =>
        message.id === id && message.role === "assistant" ? { ...message, ...patch } : message,
      ),
    );
  }, []);

  const ask = useCallback(
    async (assistantId: string, question: string) => {
      let id = sessionIdRef.current;
      if (!id) {
        // A new chat gets its URL on the first question, without remounting this view.
        id = crypto.randomUUID();
        sessionIdRef.current = id;
        window.history.replaceState(null, "", `/c/${id}`);
        setActiveSessionId(id);
      }
      saveSession({ id, title: question.slice(0, 80), updatedAt: Date.now() });

      try {
        const response = await sendMessage({
          message: question,
          sessionId: id,
          employeeContext: office.context,
        });
        updateAssistant(assistantId, {
          status: "done",
          text: response.answer,
          sources: response.sources,
          confidenceLabel: response.confidence_label,
          escalated: response.escalated,
        });
      } catch (error) {
        updateAssistant(assistantId, { status: "error", text: errorMessage(error) });
      }
    },
    [office.context, saveSession, setActiveSessionId, updateAssistant],
  );

  function send(question: string) {
    const assistantId = crypto.randomUUID();
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", text: question },
      { id: assistantId, role: "assistant", question, status: "pending", text: "", sources: [], escalated: false },
    ]);
    void ask(assistantId, question);
  }

  function retry(message: AssistantMessage) {
    updateAssistant(message.id, { status: "pending", text: "" });
    void ask(message.id, message.question);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[46rem] px-4 sm:px-6">
          {historyState === "loading" && <p className="pending pt-10 text-ink-soft">Loading this chat…</p>}
          {historyState === "error" && (
            <p className="pt-10 text-ink-soft">
              This chat couldn&apos;t be loaded. Check that the API is running, then reload the page.
            </p>
          )}
          {historyState === "ready" && messages.length === 0 && <EmptyState onAsk={send} />}
          {messages.length > 0 && (
            <ol aria-live="polite" className="space-y-6 py-8">
              {messages.map((message) => (
                <li key={message.id}>
                  {message.role === "user" ? (
                    <UserBubble message={message} />
                  ) : (
                    <AssistantReply message={message} onRetry={() => retry(message)} />
                  )}
                </li>
              ))}
            </ol>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="mx-auto w-full max-w-[46rem] px-4 pb-4 sm:px-6">
        <Composer disabled={pending || historyState !== "ready"} onSend={send} />
        <p className="mt-2 text-center text-xs text-ink-soft">
          Answers come from NordTech policy documents. Check the sources before acting on anything
          important.
        </p>
      </div>
    </div>
  );
}
