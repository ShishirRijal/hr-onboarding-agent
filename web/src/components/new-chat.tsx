"use client";

import { useAppState } from "@/lib/app-state";
import { ChatView } from "./chat-view";

// Keyed so "New chat" clears the view even when the current chat started on this page.
export function NewChat() {
  const { newChatKey } = useAppState();
  return <ChatView key={newChatKey} sessionId={null} />;
}
