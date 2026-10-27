import { Suspense } from "react";
import { HrReviewDetailView } from "@/components/hr-review";

// The question id is only known at request time, so it resolves inside Suspense
// (Cache Components fails the build otherwise).
export default function HrReviewDetailPage({ params }: PageProps<"/hr/review/[interactionId]">) {
  return (
    <Suspense fallback={<p className="pending mx-auto w-full max-w-[60rem] px-6 pt-10 text-ink-soft">Loading this question…</p>}>
      {params.then(({ interactionId }) => (
        <HrReviewDetailView key={interactionId} interactionId={interactionId} />
      ))}
    </Suspense>
  );
}
