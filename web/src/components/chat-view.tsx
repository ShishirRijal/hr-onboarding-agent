"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchSessionMessages, requestHr, streamMessage } from "@/lib/api";
import { useAppState } from "@/lib/app-state";
import type { AssistantMessage, ChatMessage, HrReply, ProgressStep, SessionMessage, Source } from "@/lib/types";
import { Composer } from "./composer";
import { EmptyState } from "./empty-state";
import { AssistantReply, UserBubble } from "./messages";
import { SourcePanel } from "./source-panel";

function hrReplyOf(item: SessionMessage): HrReply | undefined {
  return item.hr_answer ? { text: item.hr_answer, by: item.hr_answered_by, at: item.hr_answered_at } : undefined;
}

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
      hrReply: hrReplyOf(item),
    },
  ]);
}

// Adds HR replies that arrived while the chat was open to the questions they answer.
function withHrReplies(messages: ChatMessage[], history: SessionMessage[]): ChatMessage[] {
  const replies = new Map(history.filter((item) => item.hr_answer).map((item) => [item.interaction_id, item]));
  return messages.map((message) => {
    const reply = message.role === "assistant" && message.interactionId ? replies.get(message.interactionId) : undefined;
    return reply ? { ...message, hrStatus: "answered" as const, hrReply: hrReplyOf(reply) } : message;
  });
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong while getting an answer.";
}

function historyError(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) {
    return "This chat isn't available. It may have been started with a different account.";
  }
  return "This chat couldn't be loaded. Check that the API is running, then reload the page.";
}

function withStep(steps: ProgressStep[], step: ProgressStep): ProgressStep[] {
  // A repeated stage replaces the previous step instead of being listed twice.
  const last = steps[steps.length - 1];
  return last && last.stage === step.stage ? [...steps.slice(0, -1), step] : [...steps, step];
}

export function ChatView({ sessionId }: { sessionId: string | null }) {
  const { sessions, activeSessionId, saveSession, setActiveSessionId, markSessionRead, refreshSessions } =
    useAppState();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // The source open beside the chat, and the chip that opened it so focus can go back there.
  const [openSource, setOpenSource] = useState<{ source: Source; messageId: string } | null>(null);
  const sourceOpenerRef = useRef<HTMLElement | null>(null);
  const closeSource = useCallback(() => {
    setOpenSource(null);
    sourceOpenerRef.current?.focus();
  }, []);
  const [historyState, setHistoryState] = useState<"loading" | "ready" | "error">(
    sessionId ? "loading" : "ready",
  );
  const [historyErrorText, setHistoryErrorText] = useState("");
  const sessionIdRef = useRef(sessionId);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);
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
        // Opening the chat shows any HR replies, so they're no longer new.
        markSessionRead(sessionId);
        setHistoryState("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setHistoryErrorText(historyError(error));
        setHistoryState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, markSessionRead]);

  // The chat list is checked for HR replies now and then; one for this chat is shown in place.
  const unreadHere = sessions.find((session) => session.id === activeSessionId)?.unread ?? 0;
  useEffect(() => {
    if (!activeSessionId || unreadHere === 0 || historyState !== "ready") return;
    let cancelled = false;
    fetchSessionMessages(activeSessionId)
      .then((history) => {
        if (cancelled) return;
        setMessages((current) => withHrReplies(current, history));
        markSessionRead(activeSessionId);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [activeSessionId, unreadHere, historyState, markSessionRead]);

  // Keep the newest text in view as it is written, unless the reader has scrolled up.
  useEffect(() => {
    const scroller = scrollerRef.current;
    const content = contentRef.current;
    if (!scroller || !content) return;
    const onScroll = () => {
      followRef.current = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
    };
    const observer = new ResizeObserver(() => {
      if (followRef.current) scroller.scrollTop = scroller.scrollHeight;
    });
    scroller.addEventListener("scroll", onScroll, { passive: true });
    observer.observe(content);
    return () => {
      scroller.removeEventListener("scroll", onScroll);
      observer.disconnect();
    };
  }, []);

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
      saveSession({ id, title: question.slice(0, 80), updatedAt: Date.now(), unread: 0 });

      try {
        const response = await streamMessage(
          { message: question, sessionId: id },
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
        // The chat is stored now, with its title from the first question.
        refreshSessions();
      } catch (error) {
        updateAssistant(assistantId, { status: "error", text: errorMessage(error) });
      }
    },
    [saveSession, setActiveSessionId, updateAssistant, refreshSessions],
  );

  function send(question: string) {
    followRef.current = true;
    const assistantId = crypto.randomUUID();
    setMessages((current) => [
      // Asking something else withdraws any HR offer still waiting for an answer.
      ...current.map((message) =>
        message.role === "assistant" && message.hrStatus === "offered"
          ? { ...message, hrStatus: "dismissed" as const }
          : message,
      ),
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
    // A new id remounts the reply, so its progress and timer start over.
    const assistantId = crypto.randomUUID();
    setMessages((current) =>
      current.map((item) =>
        item.id === message.id ? { ...message, id: assistantId, status: "pending", text: "", steps: [] } : item,
      ),
    );
    void ask(assistantId, message.question);
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
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <div ref={scrollerRef} className="min-h-0 flex-1 overflow-y-auto">
          <div ref={contentRef} className="mx-auto w-full max-w-[46rem] px-4 sm:px-6">
            {historyState === "loading" && <p className="pending pt-10 text-ink-soft">Loading this chat…</p>}
            {historyState === "error" && <p className="pt-10 text-ink-soft">{historyErrorText}</p>}
            {historyState === "ready" && messages.length === 0 && <EmptyState onAsk={send} />}
            {messages.length > 0 && (
              <ol aria-live="polite" className="space-y-7 py-8">
                {messages.map((message, index) => (
                  <li key={message.id}>
                    {message.role === "user" ? (
                      <UserBubble message={message} />
                    ) : (
                      <AssistantReply
                        message={message}
                        latest={index === messages.length - 1}
                        openChunkId={openSource?.messageId === message.id ? openSource.source.chunk_id : null}
                        onRetry={() => retry(message)}
                        onChooseHr={(askHr) => void chooseHr(message, askHr)}
                        onOpenSource={(source, opener) => {
                          const alreadyOpen =
                            openSource?.messageId === message.id && openSource.source.chunk_id === source.chunk_id;
                          sourceOpenerRef.current = opener;
                          setOpenSource(alreadyOpen ? null : { source, messageId: message.id });
                        }}
                      />
                    )}
                  </li>
                ))}
              </ol>
            )}
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
      {openSource && (
        <SourcePanel key={openSource.source.chunk_id} source={openSource.source} onClose={closeSource} />
      )}
    </div>
  );
}
