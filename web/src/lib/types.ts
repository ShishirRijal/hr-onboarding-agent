export type Source = {
  chunk_id: string;
  source_doc?: string | null;
  source_file?: string | null;
  section_path?: string | null;
  page_number?: number | null;
  row_number?: number | null;
  score: number;
};

// A source opened in place: its whole document and the span the answer drew on.
export type SourcePassage = {
  chunk_id: string;
  source_doc: string | null;
  source_file: string | null;
  section_path: string | null;
  content: string;
  highlight_start: number | null;
  highlight_end: number | null;
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
  answered: boolean;
  escalation_status: HrStatus | null;
  escalation_reason: string | null;
};

// "offered": the documents had no answer and the employee was asked about HR.
export type HrStatus = "offered" | "requested" | "declined";

export type HrRequestResponse = {
  interaction_id: string;
  escalation_status: HrStatus;
  message: string;
};

export type ProgressStep = {
  stage: string;
  label: string;
  documents?: string[];
};

export type SessionMessage = {
  interaction_id: string;
  created_at: string;
  question: string;
  answer: string;
  sources: Source[];
  confidence_score: number;
  confidence_label: string;
  answered: boolean;
  escalation_status: HrStatus | null;
  escalation_reason: string | null;
};

export type UserMessage = { id: string; role: "user"; text: string };

export type AssistantMessage = {
  id: string;
  role: "assistant";
  question: string;
  // pending: working, no text yet; streaming: answer text is arriving.
  status: "pending" | "streaming" | "done" | "error";
  text: string;
  sources: Source[];
  steps: ProgressStep[];
  answered: boolean;
  interactionId?: string;
  hrStatus?: HrStatus | "sending";
  hrMessage?: string;
};

export type ChatMessage = UserMessage | AssistantMessage;

export type SessionSummary = {
  id: string;
  title: string;
  updatedAt: number;
};
