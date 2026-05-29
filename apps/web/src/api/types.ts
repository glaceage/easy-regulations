export type RevisionState =
  | "draft"
  | "in_consultation"
  | "in_revision"
  | "pending_publish"
  | "published"
  | "cancelled";

export type CommentStatus = "open" | "resolved" | "wont_fix";

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

export interface ApiError {
  detail?: string | { msg: string }[];
}
