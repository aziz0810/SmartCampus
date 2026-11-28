const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface VisitorSession {
  session_id: string;
  access_token: string;
  expires_at: string;
  message_limit: number;
  memory_limit: number;
  messages_remaining: number;
}

export interface VisitorMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The stored visitor session is unusable (unknown, expired or bad token). */
export function isSessionGone(error: unknown): boolean {
  return (
    error instanceof ApiError && [401, 404, 410].includes(error.status)
  );
}

interface AddedMessage {
  message: VisitorMessage;
  messages_remaining: number;
}

async function request(
  path: string,
  init?: RequestInit,
  accessToken?: string,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (init?.body) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new ApiError(
      body?.detail ?? `API request failed (${response.status}).`,
      response.status,
    );
  }
  return response;
}

export async function createVisitorSession(): Promise<VisitorSession> {
  const response = await request("/api/visitor-sessions", { method: "POST" });
  return (await response.json()) as VisitorSession;
}

export async function getVisitorMessages(
  sessionId: string,
  accessToken: string,
): Promise<VisitorMessage[]> {
  const response = await request(
    `/api/visitor-sessions/${encodeURIComponent(sessionId)}/messages`,
    undefined,
    accessToken,
  );
  return (await response.json()) as VisitorMessage[];
}

export async function addVisitorMessage(
  sessionId: string,
  accessToken: string,
  content: string,
): Promise<AddedMessage> {
  const response = await request(
    `/api/visitor-sessions/${encodeURIComponent(sessionId)}/messages`,
    { method: "POST", body: JSON.stringify({ content }) },
    accessToken,
  );
  return (await response.json()) as AddedMessage;
}

export async function deleteVisitorSession(
  sessionId: string,
  accessToken: string,
): Promise<void> {
  await request(
    `/api/visitor-sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
    accessToken,
  );
}
