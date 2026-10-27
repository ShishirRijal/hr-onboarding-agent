import { Suspense } from "react";
import { HrReview } from "@/components/hr-review";

// The filter comes from the URL, which is only known at request time.
export default function HrReviewPage() {
  return (
    <Suspense fallback={<p className="pending mx-auto w-full max-w-[60rem] px-6 pt-10 text-ink-soft">Loading questions…</p>}>
      <HrReview />
    </Suspense>
  );
}
