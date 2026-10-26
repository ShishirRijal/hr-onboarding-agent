"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchSessionMessages, requestHr, streamMessage } from "@/lib/api";
import { useAppState } from "@/lib/app-state";
import type { AssistantMessage, ChatMessage, ProgressStep, SessionMessage } from "@/lib/types";
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
      steps: [],
      answered: item.answered,
      interactionId: item.interaction_id,
      hrStatus: item.escalation_status ?? undefined,
    },
  ]);
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong while getting an answer.";
}

function withStep(steps: ProgressStep[], step: ProgressStep): ProgressStep[] {
  // A repeated stage replaces the previous step instead of being listed twice.
  const last = steps[steps.length - 1];
  return last && last.stage === step.stage ? [...steps.slice(0, -1), step] : [...steps, step];
}

export function ChatView({ sessionId }: { sessionId: string | null }) {
  const { office, saveSession, setActiveSessionId } = useAppState();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [historyState, setHistoryState] = useState<"loading" | "ready" | "error">(
    sessionId ? "loading" : "ready",
  );
  const sessionIdRef = useRef(sessionId);
  const endRef = useRef<HTMLDivElement>(null);
  const busy = messages.some(
    (message) => message.role === "assistant" && (message.status === "pending" || message.status === "streaming"),
  );

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

  const updateAssistant = useCallback(
    (id: string, patch: Partial<AssistantMessage> | ((message: AssistantMessage) => Partial<AssistantMessage>)) => {
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== id || message.role !== "assistant") return message;
          return { ...message, ...(typeof patch === "function" ? patch(message) : patch) };
        }),
      );
    },
    [],
  );

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
        const response = await streamMessage(
          { message: question, sessionId: id, employeeContext: office.context },
          {
            onStatus: (step) => updateAssistant(assistantId, (message) => ({ steps: withStep(message.steps, step) })),
            onToken: (text) =>
              updateAssistant(assistantId, (message) => ({ status: "streaming", text: message.text + text })),
          },
        );
        updateAssistant(assistantId, {
          status: "done",
          text: response.answer,
          sources: response.sources,
          answered: response.answered,
          interactionId: response.interaction_id ?? undefined,
          hrStatus: response.escalation_status ?? undefined,
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
      {
        id: assistantId,
        role: "assistant",
        question,
        status: "pending",
        text: "",
        sources: [],
        steps: [],
        answered: false,
      },
    ]);
    void ask(assistantId, question);
  }

  function retry(message: AssistantMessage) {
    updateAssistant(message.id, { status: "pending", text: "", steps: [] });
    void ask(message.id, message.question);
  }

  async function chooseHr(message: AssistantMessage, askHr: boolean) {
    if (!message.interactionId) return;
    updateAssistant(message.id, { hrStatus: "sending" });
    try {
      const result = await requestHr(message.interactionId, askHr);
      updateAssistant(message.id, { hrStatus: result.escalation_status, hrMessage: result.message });
    } catch (error) {
      updateAssistant(message.id, { hrStatus: "offered", hrMessage: errorMessage(error) });
    }
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
            <ol aria-live="polite" className="space-y-7 py-8">
              {messages.map((message) => (
                <li key={message.id}>
                  {message.role === "user" ? (
                    <UserBubble message={message} />
                  ) : (
                    <AssistantReply
                      message={message}
                      onRetry={() => retry(message)}
                      onChooseHr={(askHr) => void chooseHr(message, askHr)}
                    />
                  )}
                </li>
              ))}
            </ol>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="mx-auto w-full max-w-[46rem] px-4 pb-4 sm:px-6">
        <Composer disabled={busy || historyState !== "ready"} onSend={send} />
        <p className="mt-2 text-center text-xs text-ink-soft">
          Answers come from NordTech policy documents. Check the sources before acting on anything
          important.
        </p>
      </div>
    </div>
  );
}
