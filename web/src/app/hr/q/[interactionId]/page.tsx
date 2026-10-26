import { Suspense } from "react";
import { HrQuestionView } from "@/components/hr-question";

// The question id is only known at request time, so it resolves inside Suspense
// (Cache Components fails the build otherwise).
export default function HrQuestionPage({ params }: PageProps<"/hr/q/[interactionId]">) {
  return (
    <Suspense fallback={<p className="pending mx-auto w-full max-w-[60rem] px-6 pt-10 text-ink-soft">Loading this question…</p>}>
      {params.then(({ interactionId }) => (
        <HrQuestionView key={interactionId} interactionId={interactionId} />
      ))}
    </Suspense>
  );
}
