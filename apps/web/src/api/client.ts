import type {
  Comment,
  CommentUpdate,
  DraftJobResponse,
  DraftMarkdown,
  ImportDocxResponse,
  JobStatus,
  LlmSuggestion,
  NotificationItem,
  Policy,
  PolicyCreate,
  PublishRequestResponse,
  PublishResponse,
  Revision,
  RevisionReviewer,
  ReviewAssignment,
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
  if (res.status >= 500) {
    return `服务器错误 (${res.status})，请稍后重试或查看后台日志`;
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
  if (res.status === 401 && auth) {
    clearToken();
    const returnTo = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.assign(`/login?expired=1&from=${returnTo}`);
    throw new Error("登录已过期，请重新登录");
  }
  if (!res.ok) {
    throw new Error(await parseError(res));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function requestBlob(path: string): Promise<Blob> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (res.status === 401) {
    clearToken();
    const returnTo = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.assign(`/login?expired=1&from=${returnTo}`);
    throw new Error("登录已过期，请重新登录");
  }
  if (!res.ok) {
    throw new Error(await parseError(res));
  }
  return res.blob();
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
    return request<Policy[]>("/policies");
  },

  getPolicy(id: string) {
    return request<Policy>(`/policies/${id}`);
  },

  listPolicyRevisions(policyId: string) {
    return request<Revision[]>(`/policies/${policyId}/revisions`);
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

  getJobStatus(jobId: string) {
    return request<JobStatus>(`/jobs/${jobId}`);
  },

  listAiSuggestions(revisionId: string) {
    return request<LlmSuggestion[]>(`/revisions/${revisionId}/ai/suggestions`);
  },

  transitionRevision(revisionId: string, targetState: string) {
    return request<Revision>(`/revisions/${revisionId}/transition`, {
      method: "POST",
      body: JSON.stringify({ target_state: targetState }),
    });
  },

  getDraftMarkdown(revisionId: string) {
    return request<DraftMarkdown>(`/revisions/${revisionId}/draft-markdown`);
  },

  saveDraftMarkdown(revisionId: string, markdown: string) {
    return request<DraftMarkdown>(`/revisions/${revisionId}/draft-markdown`, {
      method: "PUT",
      body: JSON.stringify({ markdown }),
    });
  },

  acceptSuggestion(suggestionId: string) {
    return request<LlmSuggestion>(`/ai/suggestions/${suggestionId}/accept`, {
      method: "POST",
    });
  },

  updateComment(commentId: string, update: CommentUpdate) {
    return request<Comment>(`/comments/${commentId}`, {
      method: "PATCH",
      body: JSON.stringify(update),
    });
  },

  enqueueCommentPatch(commentId: string) {
    return request<DraftJobResponse>(`/comments/${commentId}/ai/patch`, {
      method: "POST",
    });
  },

  publishRevision(revisionId: string) {
    return request<PublishResponse>(`/revisions/${revisionId}/publish`, {
      method: "POST",
    });
  },

  requestPublishPdf(revisionId: string) {
    return request<PublishRequestResponse>(`/revisions/${revisionId}/publish-request`, {
      method: "POST",
    });
  },

  createRevision(policyId: string, changeBrief: string, targetVersionLabel: string) {
    return request<Revision>("/revisions", {
      method: "POST",
      body: JSON.stringify({
        policy_id: policyId,
        change_brief: changeBrief,
        target_version_label: targetVersionLabel,
      }),
    });
  },

  updateRevisionMeta(
    revisionId: string,
    update: { change_brief?: string; target_version_label?: string },
  ) {
    return request<Revision>(`/revisions/${revisionId}`, {
      method: "PATCH",
      body: JSON.stringify(update),
    });
  },

  createPolicy(body: PolicyCreate) {
    return request<Policy>("/policies", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  fetchRevisionFile(revisionId: string, key: string) {
    return requestBlob(`/revisions/${revisionId}/files?key=${encodeURIComponent(key)}`);
  },

  importDocx(revisionId: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    return request<ImportDocxResponse>(`/revisions/${revisionId}/import-docx`, {
      method: "POST",
      body: form,
    });
  },

  listReviewers(revisionId: string) {
    return request<RevisionReviewer[]>(`/revisions/${revisionId}/reviewers`);
  },

  listReviewAssignments() {
    return request<ReviewAssignment[]>("/reviews/assignments");
  },

  assignReviewer(revisionId: string, username: string, isMandatory = true) {
    return request<RevisionReviewer>(`/revisions/${revisionId}/reviewers`, {
      method: "POST",
      body: JSON.stringify({ username, is_mandatory: isMandatory }),
    });
  },

  removeReviewer(revisionId: string, reviewerId: string) {
    return request<void>(`/revisions/${revisionId}/reviewers/${reviewerId}`, {
      method: "DELETE",
    });
  },

  listNotifications() {
    return request<NotificationItem[]>("/notifications");
  },

  markNotificationsRead() {
    return request<{ marked: number }>("/notifications/read", {
      method: "POST",
    });
  },
};
