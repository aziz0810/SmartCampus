/**
 * Auth API calls: login, register, /me, claim visitor session.
 */
const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface UserOut {
  id: number;
  email: string;
  full_name: string;
  role: "candidat" | "responsable";
  is_active: boolean;
  last_login_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserOut;
}

export interface ClaimSessionResponse {
  session_id: string;
  claimed: boolean;
}

class AuthApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "AuthApiError";
  }
}

async function authRequest<T>(
  path: string,
  body: unknown,
  accessToken?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }
  const res = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new AuthApiError(
      data?.detail ?? `Auth error (${res.status}).`,
      res.status,
    );
  }
  return res.json() as Promise<T>;
}

export async function apiLogin(
  email: string,
  password: string,
): Promise<TokenResponse> {
  return authRequest<TokenResponse>("/api/auth/login", { email, password });
}

export async function apiRegister(
  email: string,
  full_name: string,
  password: string,
  visitor_session_id?: string,
): Promise<TokenResponse> {
  return authRequest<TokenResponse>("/api/auth/register", {
    email,
    full_name,
    password,
    visitor_session_id: visitor_session_id ?? null,
  });
}

export async function apiMe(accessToken: string): Promise<UserOut> {
  const res = await fetch(`${apiBaseUrl}/api/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new AuthApiError("Not authenticated.", res.status);
  return res.json() as Promise<UserOut>;
}

export async function apiClaimSession(
  accessToken: string,
  visitor_session_id: string,
): Promise<ClaimSessionResponse> {
  return authRequest<ClaimSessionResponse>(
    "/api/auth/claim-session",
    { visitor_session_id },
    accessToken,
  );
}

export { AuthApiError };
