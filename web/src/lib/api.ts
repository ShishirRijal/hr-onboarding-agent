import type {
  AnswerScope,
  ChatResponse,
  ChatSessionSummary,
  FeedbackResponse,
  HrOverview,
  HrQuestion,
  HrQuestionDetail,
  HrRequestResponse,
  ProgressStep,
  Rating,
  ReviewDetail,
  ReviewFilter,
  ReviewPage,
  ReviewVerdict,
  SessionMessage,
  SourcePassage,
  UsagePeriodKey,
  UsageReport,
  User,
} from "./types";

const UNREACHABLE = "The HR assistant can't be reached. Check that the API is running.";
export const SIGN_IN_PATH = "/sign-in";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

// A request without a valid session goes to sign-in, then back to the page it came from.
function redirectToSignIn() {
  if (window.location.pathname === SIGN_IN_PATH) return;
  const next = window.location.pathname === "/" ? "" : `?next=${encodeURIComponent(window.location.pathname)}`;
  // A full page load rather than a client-side navigation, so nothing from the expired session stays in memory.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`${SIGN_IN_PATH}${next}`);
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(UNREACHABLE, 0);
  }

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: unknown }) => (typeof body.detail === "string" ? body.detail : null))
      .catch(() => null);
    if (response.status === 401 && path !== "/auth/sign-in") redirectToSignIn();
    throw new ApiError(detail ?? `The HR assistant returned an error (${response.status}).`, response.status);
  }
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await send(path, init)).json()) as T;
}

export function signIn(email: string, password: string): Promise<User> {
  return request<User>("/auth/sign-in", { method: "POST", body: JSON.stringify({ email, password }) });
}

export async function signOut(): Promise<void> {
  await send("/auth/sign-out", { method: "POST" });
}

export function fetchMe(): Promise<User> {
  return request<User>("/auth/me");
}

export type StreamHandlers = {
  onStatus: (step: ProgressStep) => void;
  onToken: (text: string) => void;
};

// Streams an answer over server-sent events. Resolves with the final answer once the
// "done" event arrives; status and token events are delivered to the handlers as they come.
// Who is asking comes from the session on the server, not from here.
export async function streamMessage(
  input: { message: string; sessionId: string },
  handlers: StreamHandlers,
): Promise<ChatResponse> {
  const response = await send("/chat/stream", {
    method: "POST",
    body: JSON.stringify({ message: input.message, session_id: input.sessionId }),
  });
  if (!response.body) throw new ApiError(UNREACHABLE, 0);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;

      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = parseEvent(block);
        if (!event) continue;

        if (event.name === "status") handlers.onStatus(event.data as ProgressStep);
        else if (event.name === "token") handlers.onToken((event.data as { text: string }).text);
        else if (event.name === "done") return event.data as ChatResponse;
        else if (event.name === "error") {
          throw new ApiError((event.data as { detail?: string }).detail ?? "Something went wrong.", 503);
        }
      }
    }
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError("The connection to the HR assistant dropped. Try again.", 0);
  } finally {
    reader.releaseLock();
  }
  throw new ApiError("The answer was cut off before it finished. Try again.", 0);
}

function parseEvent(block: string): { name: string; data: unknown } | null {
  let name = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) name = line.slice(7);
    else if (line.startsWith("data: ")) data.push(line.slice(6));
  }
  if (data.length === 0) return null;
  return { name, data: JSON.parse(data.join("\n")) };
}

export function requestHr(interactionId: string, askHr: boolean): Promise<HrRequestResponse> {
  return request<HrRequestResponse>(`/interactions/${encodeURIComponent(interactionId)}/hr-request`, {
    method: "POST",
    body: JSON.stringify({ ask_hr: askHr }),
  });
}

// null takes a rating back.
export function sendFeedback(interactionId: string, rating: Rating | null, comment?: string): Promise<FeedbackResponse> {
  return request<FeedbackResponse>(`/interactions/${encodeURIComponent(interactionId)}/feedback`, {
    method: "POST",
    body: JSON.stringify({ rating, comment: comment ?? null }),
  });
}

export function fetchSessions(): Promise<ChatSessionSummary[]> {
  return request<ChatSessionSummary[]>("/sessions");
}

export function fetchSessionMessages(sessionId: string): Promise<SessionMessage[]> {
  return request<SessionMessage[]>(`/sessions/${encodeURIComponent(sessionId)}/messages`);
}

// Documents only change on re-ingestion, so an opened source is kept for the session.
const passages = new Map<string, Promise<SourcePassage>>();

export function fetchSourcePassage(chunkId: string): Promise<SourcePassage> {
  let passage = passages.get(chunkId);
  if (!passage) {
    passage = request<SourcePassage>(`/sources/${encodeURIComponent(chunkId)}`);
    passage.catch(() => passages.delete(chunkId));
    passages.set(chunkId, passage);
  }
  return passage;
}

export function fetchHrOverview(): Promise<HrOverview> {
  return request<HrOverview>("/hr/overview");
}

export function fetchHrQuestions(status: "requested" | "answered"): Promise<HrQuestion[]> {
  return request<HrQuestion[]>(`/hr/questions?status=${status}`);
}

export function fetchHrQuestion(interactionId: string): Promise<HrQuestionDetail> {
  return request<HrQuestionDetail>(`/hr/questions/${encodeURIComponent(interactionId)}`);
}

export function answerHrQuestion(
  interactionId: string,
  answer: string,
  appliesTo: AnswerScope,
): Promise<HrQuestionDetail> {
  return request<HrQuestionDetail>(`/hr/questions/${encodeURIComponent(interactionId)}/answer`, {
    method: "POST",
    body: JSON.stringify({ answer, applies_to: appliesTo }),
  });
}

export function fetchReviewPage(show: ReviewFilter, offset = 0): Promise<ReviewPage> {
  return request<ReviewPage>(`/hr/review?show=${show}&offset=${offset}`);
}

export function fetchReviewDetail(interactionId: string): Promise<ReviewDetail> {
  return request<ReviewDetail>(`/hr/review/${encodeURIComponent(interactionId)}`);
}

export function saveReview(interactionId: string, verdict: ReviewVerdict, answer?: string): Promise<ReviewDetail> {
  return request<ReviewDetail>(`/hr/review/${encodeURIComponent(interactionId)}`, {
    method: "POST",
    body: JSON.stringify({ verdict, answer: answer ?? null }),
  });
}

export function fetchUsageReport(period: UsagePeriodKey): Promise<UsageReport> {
  return request<UsageReport>(`/hr/usage?period=${period}`);
}
