import type { ChatResponse, EmployeeContext, SessionMessage } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("The HR assistant can't be reached. Check that the API is running.", 0);
  }

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body: { detail?: unknown }) => (typeof body.detail === "string" ? body.detail : null))
      .catch(() => null);
    throw new ApiError(detail ?? `The HR assistant returned an error (${response.status}).`, response.status);
  }
  return (await response.json()) as T;
}

export function sendMessage(input: {
  message: string;
  sessionId: string;
  employeeContext: EmployeeContext;
}): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({
      message: input.message,
      session_id: input.sessionId,
      employee_context: input.employeeContext,
    }),
  });
}

export function fetchSessionMessages(sessionId: string): Promise<SessionMessage[]> {
  return request<SessionMessage[]>(`/sessions/${encodeURIComponent(sessionId)}/messages`);
}
