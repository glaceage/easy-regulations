import type {
  Comment,
  DraftJobResponse,
  LlmSuggestion,
  Policy,
  Revision,
  TokenResponse,
} from "./types";

const API_BASE = "/api";
const TOKEN_KEY = "er_access_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getToken());
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    const detail = data.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => (typeof d === "object" && d && "msg" in d ? String(d.msg) : String(d))).join("; ");
    }
  } catch {
    /* ignore */
  }
  return res.statusText || `请求失败 (${res.status})`;
}

async function request<T>(
  path: string,
  options: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = true, ...init } = options;
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (auth) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    throw new Error(await parseError(res));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  login(username: string, password: string) {
    return request<TokenResponse>("/auth/login", {
      method: "POST",
      auth: false,
      body: JSON.stringify({ username, password }),
    });
  },

  listPolicies() {
    return request<Policy[]>("/policies", { auth: false });
  },

  getPolicy(id: string) {
    return request<Policy>(`/policies/${id}`, { auth: false });
  },

  getRevision(id: string) {
    return request<Revision>(`/revisions/${id}`);
  },

  listComments(revisionId: string) {
    return request<Comment[]>(`/revisions/${revisionId}/comments`);
  },

  createComment(revisionId: string, sectionId: string, body: string) {
    return request<Comment>(`/revisions/${revisionId}/comments`, {
      method: "POST",
      body: JSON.stringify({ section_id: sectionId, body }),
    });
  },

  enqueueAiDraft(revisionId: string) {
    return request<DraftJobResponse>(`/revisions/${revisionId}/ai/draft`, {
      method: "POST",
    });
  },

  listAiSuggestions(revisionId: string) {
    return request<LlmSuggestion[]>(`/revisions/${revisionId}/ai/suggestions`);
  },
};
