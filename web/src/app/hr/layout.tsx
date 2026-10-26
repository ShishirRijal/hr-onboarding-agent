import type { Metadata } from "next";
import { HrShell } from "@/components/hr-shell";
import { SessionProvider } from "@/lib/session";

export const metadata: Metadata = { title: "HR platform · NordTech HR" };

// Only for the HR team: others are sent to the chat, and the API refuses their requests.
export default function HrLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider area="hr">
      <HrShell>{children}</HrShell>
    </SessionProvider>
  );
}
