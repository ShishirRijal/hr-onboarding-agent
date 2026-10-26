import { Suspense } from "react";
import { ChatView } from "@/components/chat-view";

// The session id is only known at request time, so it resolves inside Suspense
// (Cache Components fails the build otherwise).
export default function SessionPage({ params }: PageProps<"/c/[sessionId]">) {
  return (
    <Suspense fallback={<p className="pending mx-auto w-full max-w-[46rem] px-6 pt-10 text-ink-soft">Loading this chat…</p>}>
      {params.then(({ sessionId }) => (
        <ChatView key={sessionId} sessionId={sessionId} />
      ))}
    </Suspense>
  );
}
