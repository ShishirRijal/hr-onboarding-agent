export type Role = "employee" | "hr";

// The signed-in user's profile. Where they work decides which country's rules the assistant uses.
export type User = {
  id: string;
  email: string;
  name: string;
  role: Role;
  job_title: string;
  department: string;
  // "Tallinn", "Tampere", "Porto", or "Remote".
  office: string;
  // The country they are employed in, also for remote employees.
  country: string;
  manager_name: string | null;
  start_date: string;
  pronouns: string | null;
};

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
// "dismissed": they asked something else without choosing, which counts as a no.
// "answered": HR replied from the HR inbox.
export type HrStatus = "offered" | "requested" | "declined" | "dismissed" | "answered";

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
  hr_answer: string | null;
  hr_answered_by: string | null;
  hr_answered_at: string | null;
  feedback: Rating | null;
  feedback_comment: string | null;
};

// The thumbs under an answer.
export type Rating = "up" | "down";

export type FeedbackResponse = {
  interaction_id: string;
  feedback: Rating | null;
  feedback_comment: string | null;
};

export type HrReply = { text: string; by: string | null; at: string | null };

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
  hrReply?: HrReply;
  feedback?: Rating | null;
  feedbackComment?: string | null;
};

export type ChatMessage = UserMessage | AssistantMessage;

export type ChatSessionSummary = {
  session_id: string;
  title: string;
  updated_at: string;
  unread_hr_replies: number;
};

export type SessionSummary = {
  id: string;
  title: string;
  updatedAt: number;
  // HR replies in this chat the user hasn't seen yet.
  unread: number;
};

export type Asker = {
  name: string;
  email: string | null;
  job_title: string | null;
  department: string | null;
  office: string | null;
  country: string | null;
};

export type HrQuestion = {
  interaction_id: string;
  question: string;
  asked_at: string;
  asker: Asker;
  status: "requested" | "answered";
  reason: string;
  hr_answer: string | null;
  hr_answered_by: string | null;
  hr_answered_at: string | null;
  // "All", or the one country the answer was added to the knowledge base for.
  hr_answer_country: string | null;
};

export type HrQuestionDetail = HrQuestion & {
  documents_checked: string[];
  earlier_turns: { question: string; answer: string }[];
};

export type HrOverview = {
  open_questions: number;
  answered_this_week: number;
  // Answers employees marked unhelpful that HR hasn't reviewed yet.
  unhelpful_to_review: number;
  common_topics: { topic: string; count: number }[];
  topics_since: string;
};

export type AnswerScope = "country" | "everyone";

// Which answers the answer review lists.
export type ReviewFilter = "all" | "unhelpful" | "helpful" | "not_answered" | "reviewed";

// "correct": the answer was right; "corrected": HR wrote the answer they'd have given.
export type ReviewVerdict = "correct" | "corrected";

// A logged question in the answer review. Anonymous: only the asker's country.
export type ReviewItem = {
  interaction_id: string;
  asked_at: string;
  question: string;
  answer: string;
  answered: boolean;
  small_talk: boolean;
  country: string | null;
  escalation_status: HrStatus | null;
  feedback: Rating | null;
  feedback_comment: string | null;
  review_verdict: ReviewVerdict | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
};

export type ReviewPage = { items: ReviewItem[]; total: number };

export type ReviewDetail = ReviewItem & {
  sources: Source[];
  confidence_label: string;
  reason: string | null;
  hr_answer: string | null;
  review_answer: string | null;
  earlier_turns: { question: string; answer: string }[];
};
