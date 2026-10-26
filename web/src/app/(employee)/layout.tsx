import { EmployeeShell } from "@/components/employee-shell";
import { AppStateProvider } from "@/lib/app-state";
import { SessionProvider } from "@/lib/session";

export default function EmployeeLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider area="employee">
      <AppStateProvider>
        <EmployeeShell>{children}</EmployeeShell>
      </AppStateProvider>
    </SessionProvider>
  );
}
