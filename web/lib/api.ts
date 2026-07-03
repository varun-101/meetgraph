/**
 * Typed API client. Bearer token in localStorage (MVP), attached on every call.
 * All endpoint shapes per CONTRACTS.md.
 */
import type {
  ActionItem,
  AuditRow,
  Me,
  Meeting,
  MeetingTokenResponse,
  SearchRequest,
  SearchResponse,
  Utterance,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "meetgraph_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token === null) localStorage.removeItem(TOKEN_KEY);
  else localStorage.setItem(TOKEN_KEY, token);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "API unreachable — is the backend running?");
  }
  if (res.status === 401 && typeof window !== "undefined") {
    setToken(null);
    if (!window.location.pathname.startsWith("/login"))
      window.location.href = "/login";
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/* ---------- auth ---------- */

export async function login(email: string, password: string): Promise<void> {
  const form = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API_URL}/auth/jwt/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  }).catch(() => {
    throw new ApiError(0, "API unreachable — is the backend running?");
  });
  if (!res.ok) throw new ApiError(res.status, "Invalid email or password");
  const data = await res.json();
  setToken(data.access_token);
}

export async function register(
  email: string,
  password: string,
  name: string,
): Promise<void> {
  await apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, name }),
  });
}

export function logout() {
  setToken(null);
  window.location.href = "/login";
}

/* ---------- rbac ---------- */

export const getMe = () => apiFetch<Me>("/rbac/me");

export const createOrg = (name: string) =>
  apiFetch<{ id: string; name: string }>("/rbac/orgs", {
    method: "POST",
    body: JSON.stringify({ name }),
  });

export const createProject = (org_id: string, name: string) =>
  apiFetch<{ id: string; org_id: string; name: string }>("/rbac/projects", {
    method: "POST",
    body: JSON.stringify({ org_id, name }),
  });

export const listProjects = (orgId: string) =>
  apiFetch<{ id: string; org_id: string; name: string; my_role?: string }[]>(
    `/rbac/projects?org_id=${orgId}`,
  );

export const getAudit = (orgId: string) =>
  apiFetch<AuditRow[]>(`/rbac/audit?org_id=${orgId}`);

/* ---------- meetings ---------- */

export const listMeetings = (projectId: string) =>
  apiFetch<Meeting[]>(`/meetings?project_id=${projectId}`);

export const createMeeting = (project_id: string, title: string) =>
  apiFetch<Meeting>("/meetings", {
    method: "POST",
    body: JSON.stringify({ project_id, title }),
  });

export const getMeeting = (id: string) => apiFetch<Meeting>(`/meetings/${id}`);

export const getMeetingToken = (id: string, guestToken?: string) =>
  apiFetch<MeetingTokenResponse>(
    guestToken
      ? `/meetings/${id}/guest-token?guest_token=${encodeURIComponent(guestToken)}`
      : `/meetings/${id}/token`,
    { method: "POST" },
  );

export const getTranscript = (id: string) =>
  apiFetch<{ meeting_id: string; canonical_text: string; utterances: Utterance[] }>(
    `/meetings/${id}/transcript`,
  );

export const getMeetingActions = (id: string) =>
  apiFetch<ActionItem[]>(`/meetings/${id}/actions`);

export const getProjectActions = (projectId: string) =>
  apiFetch<ActionItem[]>(`/projects/${projectId}/actions`);

export const patchAction = (id: string, status: string) =>
  apiFetch<ActionItem>(`/actions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });

/* ---------- memory ---------- */

export const searchMemory = (req: SearchRequest) =>
  apiFetch<SearchResponse>("/memory/search", {
    method: "POST",
    body: JSON.stringify(req),
  });

export const getBrief = (projectId: string) =>
  apiFetch<{
    project_id: string;
    markdown: string;
    citations: (string | object)[];
    generated_at?: string;
    cached?: boolean;
  }>(`/memory/brief/${projectId}`);
