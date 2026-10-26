import type {
  ChatResponse,
  EmployeeContext,
  HrRequestResponse,
  ProgressStep,
  SessionMessage,
  SourcePassage,
} from "./types";

const UNREACHABLE = "The HR assistant can't be reached. Check that the API is running.";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
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
    throw new ApiError(detail ?? `The HR assistant returned an error (${response.status}).`, response.status);
  }
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return (await (await send(path, init)).json()) as T;
}

export type StreamHandlers = {
  onStatus: (step: ProgressStep) => void;
  onToken: (text: string) => void;
};

// Streams an answer over server-sent events. Resolves with the final answer once the
// "done" event arrives; status and token events are delivered to the handlers as they come.
export async function streamMessage(
  input: { message: string; sessionId: string; employeeContext: EmployeeContext },
  handlers: StreamHandlers,
): Promise<ChatResponse> {
  const response = await send("/chat/stream", {
    method: "POST",
    body: JSON.stringify({
      message: input.message,
      session_id: input.sessionId,
      employee_context: input.employeeContext,
    }),
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
