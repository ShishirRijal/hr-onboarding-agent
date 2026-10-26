export type Source = {
  chunk_id: string;
  source_doc?: string | null;
  source_file?: string | null;
  section_path?: string | null;
  page_number?: number | null;
  row_number?: number | null;
  score: number;
};

export type EmployeeContext = {
  employee_country?: string;
  office_country?: string;
  office_location?: string;
};

export type ChatResponse = {
  session_id: string;
  interaction_id: string | null;
  answer: string;
  sources: Source[];
  confidence_score: number;
  confidence_label: string;
  escalated: boolean;
  escalation_reason: string | null;
};

export type SessionMessage = {
  interaction_id: string;
  created_at: string;
  question: string;
  answer: string;
  sources: Source[];
  confidence_score: number;
  confidence_label: string;
  escalated: boolean;
  escalation_reason: string | null;
};

export type UserMessage = { id: string; role: "user"; text: string };

export type AssistantMessage = {
  id: string;
  role: "assistant";
  question: string;
  status: "pending" | "done" | "error";
  text: string;
  sources: Source[];
  confidenceLabel?: string;
  escalated: boolean;
};

export type ChatMessage = UserMessage | AssistantMessage;

export type SessionSummary = {
  id: string;
  title: string;
  updatedAt: number;
};
