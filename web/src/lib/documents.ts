import type { Source } from "./types";

const DOCUMENT_TITLES: Record<string, string> = {
  employee_handbook: "Employee Handbook",
  onboarding_checklist: "Onboarding Checklist",
  it_guide: "IT Setup Guide",
  leave_policy: "Leave & Absence Policy",
  working_hours_policy: "Working Hours & Payroll Policy",
  benefits_guide: "Benefits & Perks Guide",
  expense_policy: "Expense & Reimbursement Policy",
  org_chart: "Org Chart & Team Directory",
  gdpr_employee_policy: "GDPR Employee Data Policy",
  eu_ai_act_summary: "EU AI Act Compliance Summary",
};

export function documentTitle(source: Source): string {
  if (source.source_doc && DOCUMENT_TITLES[source.source_doc]) {
    return DOCUMENT_TITLES[source.source_doc];
  }
  return source.source_file ?? source.source_doc ?? "HR document";
}

// Section paths start with the document's own H1 ("NordTech Solutions — Leave & Absence
// Policy > 3. Finland — Leave & Absence"); the document title is shown separately.
export function sectionLabel(source: Source): string | null {
  if (source.section_path) {
    const parts = source.section_path.split(" > ");
    return parts.length > 1 ? parts.slice(1).join(" › ") : parts[0];
  }
  if (source.page_number != null) return `Page ${source.page_number}`;
  if (source.row_number != null) return `Row ${source.row_number}`;
  return null;
}
