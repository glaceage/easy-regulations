export type RevisionState =
  | "draft"
  | "in_consultation"
  | "in_revision"
  | "pending_publish"
  | "published"
  | "cancelled";

export type CommentStatus = "open" | "accepted" | "rejected" | "deferred";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Policy {
  id: string;
  code: string;
  title: string;
  category: string;
  owner_department: string;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Revision {
  id: string;
  policy_id: string;
  base_version_id: string;
  owner_user_id: string;
  state: RevisionState;
  change_brief: string;
  draft_markdown_key: string;
  draft_content_sha256: string;
  target_version_label: string;
  created_at: string;
  updated_at: string;
}

export interface Comment {
  id: string;
  revision_id: string;
  section_id: string;
  author_id: string;
  body: string;
  status: CommentStatus;
  resolution_note: string | null;
  is_mandatory_reviewer: boolean;
  created_at: string;
  updated_at: string;
}

export interface DraftJobResponse {
  job_id: string;
}

export interface JobStatus {
  job_id: string;
  status: string;
  result: unknown;
  error: string | null;
}

export interface LlmSuggestion {
  id: string;
  revision_id: string;
  section_id: string;
  action: string;
  suggested_markdown: string;
  rationale: string;
  status: string;
  model_name: string;
  input_hash: string;
}

export interface DraftMarkdown {
  markdown: string;
  content_sha256: string;
}

export interface PublishResponse {
  revision_id: string;
  state: RevisionState;
  policy_version_id: string;
  version_label: string;
  pdf_key: string;
  markdown_key: string;
}

export interface PublishRequestResponse {
  job_id: string;
}

export interface ImportDocxResponse {
  job_id: string;
  docx_key: string;
}

export interface CommentUpdate {
  status?: CommentStatus;
  resolution_note?: string;
}

export interface RevisionCreate {
  policy_id: string;
  change_brief?: string;
  target_version_label?: string;
}

export interface PolicyCreate {
  code: string;
  title: string;
  owner_department: string;
  category?: string;
}

export interface RevisionReviewer {
  id: string;
  revision_id: string;
  user_id: string;
  username: string;
  display_name: string;
  is_mandatory: boolean;
  note: string;
  created_at: string;
}

export interface NotificationItem {
  id: string;
  message: string;
  revision_id: string | null;
  policy_id: string | null;
  read: boolean;
  created_at: string;
}

export interface ApiError {
  detail?: string | { msg: string }[];
}
