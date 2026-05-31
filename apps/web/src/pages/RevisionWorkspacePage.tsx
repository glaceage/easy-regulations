import MDEditor from "@uiw/react-md-editor";
import "@uiw/react-md-editor/markdown-editor.css";
import "@uiw/react-markdown-preview/markdown.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Comment, CommentStatus, LlmSuggestion, Revision, RevisionState } from "../api/types";
import { StateBadge } from "../components/StateBadge";
import { SectionLabel } from "../components/SectionLabel";
import { WorkflowStepper } from "../components/WorkflowStepper";
import { getAuthRole, isOwnerLike } from "../lib/auth";
import {
  canEditDraft,
  canGenerateAiDraft,
  getOwnerTransitions,
  getPhaseHint,
  getPostTransitionMessage,
  getWorkflowPhase,
} from "../lib/revisionWorkflow";

const COMMENT_STATUS: Record<string, string> = {
  open: "待处理",
  accepted: "已采纳",
  rejected: "不予修改",
  deferred: "暂缓",
};

async function pollJob(jobId: string, timeoutMs = 120_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const job = await api.getJobStatus(jobId);
    if (job.status === "complete") {
      if (job.error) throw new Error(job.error);
      return;
    }
    if (job.status === "failed" || job.error) {
      throw new Error(job.error ?? "后台任务失败");
    }
  }
  throw new Error("后台任务超时，请稍后刷新");
}

function ReadonlyCommentsList({ comments, markdown }: { comments: Comment[]; markdown?: string }) {
  if (comments.length === 0) {
    return <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: 13 }}>暂无意见</p>;
  }
  return (
    <ul className="comment-list">
      {comments.map((c) => (
        <li key={c.id} className="comment-item">
          <div className="comment-meta">
            <SectionLabel sectionId={c.section_id} markdown={markdown} /> ·{" "}
            {COMMENT_STATUS[c.status] ?? c.status}
          </div>
          <p style={{ margin: 0 }}>{c.body}</p>
          {c.resolution_note && (
            <p style={{ margin: "0.25rem 0 0", fontSize: 12, color: "var(--color-text-muted)" }}>
              处理说明：{c.resolution_note}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

function AiSuggestionsList({
  suggestions,
  canAccept,
  onAccept,
  busyId,
  markdown,
}: {
  suggestions: LlmSuggestion[];
  canAccept: boolean;
  onAccept: (id: string) => void;
  busyId: string | null;
  markdown?: string;
}) {
  if (suggestions.length === 0) return null;
  return (
    <div className="card" style={{ marginTop: "1rem" }}>
      <h3 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>AI 修改建议</h3>
      <ul className="comment-list" style={{ maxHeight: "none" }}>
        {suggestions.map((s) => (
          <li key={s.id} className="comment-item">
            <div className="comment-meta">
              <SectionLabel sectionId={s.section_id} markdown={markdown} /> · {s.action} ·{" "}
              {COMMENT_STATUS[s.status] ?? s.status}
            </div>
            <p style={{ margin: "0.25rem 0" }}>{s.rationale}</p>
            <pre style={{ fontSize: 12, overflow: "auto", background: "#f8fafb", padding: "0.5rem" }}>
              {s.suggested_markdown.slice(0, 400)}
              {s.suggested_markdown.length > 400 ? "…" : ""}
            </pre>
            {canAccept && s.status === "pending" && (
              <button
                type="button"
                className="btn btn-primary"
                style={{ fontSize: 13 }}
                disabled={busyId === s.id}
                onClick={() => onAccept(s.id)}
              >
                {busyId === s.id ? "采纳中…" : "采纳并写入正文"}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function CommentResolution({
  comment,
  onResolve,
  onAiPatch,
  busy,
  markdown,
}: {
  comment: Comment;
  onResolve: (status: CommentStatus, note: string) => Promise<void>;
  onAiPatch: () => Promise<void>;
  busy: boolean;
  markdown?: string;
}) {
  const [note, setNote] = useState(comment.resolution_note ?? "");

  return (
    <li className="comment-item">
      <div className="comment-meta">
        <SectionLabel sectionId={comment.section_id} markdown={markdown} /> ·{" "}
        {COMMENT_STATUS[comment.status] ?? comment.status}
      </div>
      <p style={{ margin: "0 0 0.5rem" }}>{comment.body}</p>
      <div className="form-group" style={{ marginBottom: "0.5rem" }}>
        <label htmlFor={`note-${comment.id}`} style={{ fontSize: 12 }}>
          处理说明（不予修改/暂缓时必填）
        </label>
        <textarea
          id={`note-${comment.id}`}
          rows={2}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="说明采纳/驳回/暂缓的原因"
        />
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        <button
          type="button"
          className="btn btn-primary"
          style={{ fontSize: 13 }}
          disabled={busy}
          onClick={() => void onResolve("accepted", note)}
        >
          采纳
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ fontSize: 13 }}
          disabled={busy}
          onClick={() => void onResolve("rejected", note)}
        >
          不予修改
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ fontSize: 13 }}
          disabled={busy}
          onClick={() => void onResolve("deferred", note)}
        >
          暂缓
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ fontSize: 13 }}
          disabled={busy}
          onClick={() => void onAiPatch()}
        >
          AI 改稿建议
        </button>
      </div>
    </li>
  );
}

export function RevisionWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const ownerLike = isOwnerLike(getAuthRole());

  const [revision, setRevision] = useState<Revision | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [suggestions, setSuggestions] = useState<LlmSuggestion[]>([]);
  const [markdown, setMarkdown] = useState("");
  const [draftDirty, setDraftDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [infoLink, setInfoLink] = useState<{ to: string; label: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [transitionLoading, setTransitionLoading] = useState(false);
  const [acceptBusyId, setAcceptBusyId] = useState<string | null>(null);
  const [commentBusyId, setCommentBusyId] = useState<string | null>(null);

  const phase = revision ? getWorkflowPhase(revision.state) : "drafting";
  const phaseHint = revision ? getPhaseHint(revision.state) : "";
  const ownerTransitions = useMemo(
    () => (revision && ownerLike ? getOwnerTransitions(revision.state) : []),
    [revision, ownerLike],
  );

  const loadComments = useCallback(async (revisionId: string) => {
    const list = await api.listComments(revisionId);
    setComments(list);
  }, []);

  const loadSuggestions = useCallback(async (revisionId: string) => {
    try {
      const list = await api.listAiSuggestions(revisionId);
      setSuggestions(list);
    } catch {
      setSuggestions([]);
    }
  }, []);

  const loadDraft = useCallback(async (revisionId: string) => {
    try {
      const draft = await api.getDraftMarkdown(revisionId);
      setMarkdown(draft.markdown);
      setDraftDirty(false);
    } catch {
      /* leave editor empty on failure */
    }
  }, []);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const rev = await api.getRevision(id);
        if (cancelled) return;
        setRevision(rev);
        await Promise.all([loadSuggestions(id), loadDraft(id)]);
        if (
          rev.state === "in_revision" ||
          rev.state === "pending_publish" ||
          rev.state === "published"
        ) {
          await loadComments(id);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, loadComments, loadSuggestions, loadDraft]);

  async function handleSaveDraft() {
    if (!id) return;
    setSavingDraft(true);
    setError(null);
    setInfo(null);
    try {
      await api.saveDraftMarkdown(id, markdown);
      setDraftDirty(false);
      setInfo("草案已保存。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSavingDraft(false);
    }
  }

  async function handleAiDraft() {
    if (!id || !revision || !canGenerateAiDraft(revision.state)) return;
    setAiLoading(true);
    setInfo(null);
    setError(null);
    try {
      const { job_id } = await api.enqueueAiDraft(id);
      setInfo("AI 初稿任务已提交，正在后台处理…");
      await pollJob(job_id);
      await loadSuggestions(id);
      setInfo("AI 初稿生成完成，请在下方查看并采纳建议。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
      setInfo(null);
    } finally {
      setAiLoading(false);
    }
  }

  async function handleAcceptSuggestion(suggestionId: string) {
    if (!id) return;
    setAcceptBusyId(suggestionId);
    setError(null);
    setInfo(null);
    try {
      await api.acceptSuggestion(suggestionId);
      await Promise.all([loadSuggestions(id), loadDraft(id)]);
      setInfo("已采纳建议并写入正文。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "采纳失败");
    } finally {
      setAcceptBusyId(null);
    }
  }

  async function handleResolveComment(commentId: string, status: CommentStatus, note: string) {
    if (!id) return;
    if ((status === "rejected" || status === "deferred") && !note.trim()) {
      setError("不予修改或暂缓的意见必须填写处理说明。");
      return;
    }
    setCommentBusyId(commentId);
    setError(null);
    setInfo(null);
    try {
      await api.updateComment(commentId, { status, resolution_note: note });
      await loadComments(id);
      setInfo("意见处理状态已更新。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新意见失败");
    } finally {
      setCommentBusyId(null);
    }
  }

  async function handleCommentAiPatch(commentId: string) {
    if (!id) return;
    setCommentBusyId(commentId);
    setError(null);
    setInfo(null);
    try {
      const { job_id } = await api.enqueueCommentPatch(commentId);
      setInfo("AI 改稿建议任务已提交，正在后台处理…");
      await pollJob(job_id);
      await loadSuggestions(id);
      setInfo("AI 改稿建议已生成，请在「AI 修改建议」中查看。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成改稿建议失败");
    } finally {
      setCommentBusyId(null);
    }
  }

  async function handleTransition(targetState: string) {
    if (!id) return;
    setTransitionLoading(true);
    setError(null);
    setInfo(null);
    try {
      const rev = await api.transitionRevision(id, targetState);
      setRevision(rev);
      const guidance = getPostTransitionMessage(targetState as RevisionState, id);
      setInfo(guidance.message);
      setInfoLink(guidance.link ?? null);
      if (targetState === "in_revision") {
        await loadComments(id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "状态更新失败");
    } finally {
      setTransitionLoading(false);
    }
  }

  if (loading) {
    return <p style={{ color: "var(--color-text-muted)" }}>加载中…</p>;
  }

  if (!revision) {
    return (
      <>
        <p>
          <Link to="/policies">← 返回制度库</Link>
        </p>
        <div className="error-banner">{error ?? "修订任务不存在"}</div>
      </>
    );
  }

  const showDraftEditor = canEditDraft(revision.state) && ownerLike;
  const showAiDraftActions = canGenerateAiDraft(revision.state) && ownerLike;

  return (
    <>
      <p>
        <Link to={`/policies/${revision.policy_id}`}>← 返回制度详情</Link>
        {revision.state === "in_consultation" && (
          <>
            {" · "}
            <Link to={`/revisions/${revision.id}/consultation`}>前往征求意见</Link>
          </>
        )}
      </p>
      <div className="toolbar">
        <h1 className="page-title" style={{ margin: 0, flex: 1 }}>
          起草工作台
        </h1>
        <StateBadge state={revision.state} />
        {revision.target_version_label && (
          <span style={{ fontSize: 14, color: "var(--color-text-muted)" }}>
            目标版本：{revision.target_version_label}
          </span>
        )}
      </div>

      <WorkflowStepper state={revision.state} />

      {error && <div className="error-banner">{error}</div>}
      {info && (
        <div className="info-banner">
          {info}
          {infoLink && (
            <Link to={infoLink.to} style={{ marginLeft: "0.5rem" }}>
              {infoLink.label} →
            </Link>
          )}
        </div>
      )}

      {revision.state === "in_consultation" ? (
        <div className="info-banner">
          当前处于征求意见阶段，本页不可改稿。
          <Link to={`/revisions/${revision.id}/consultation`} style={{ marginLeft: "0.5rem" }}>
            打开征求意见页面 →
          </Link>
        </div>
      ) : (
        <div className="info-banner">{phaseHint}</div>
      )}

      {revision.state === "pending_publish" && (
        <div className="info-banner">
          已提交发布审核。
          <Link to={`/revisions/${revision.id}/publish`} style={{ marginLeft: "0.5rem" }}>
            前往发布审核页面 →
          </Link>
        </div>
      )}

      {ownerTransitions.length > 0 && phase !== "drafting" && (
        <div className="toolbar" style={{ marginBottom: "1rem" }}>
          {ownerTransitions.map((action) => (
            <button
              key={action.target}
              type="button"
              className={`btn btn-${action.variant ?? "secondary"}`}
              disabled={transitionLoading}
              onClick={() => void handleTransition(action.target)}
            >
              {transitionLoading ? "处理中…" : action.label}
            </button>
          ))}
        </div>
      )}

      <div className="card" style={{ marginBottom: "1.25rem" }}>
        <h2 style={{ margin: "0 0 0.5rem", fontSize: "1rem" }}>修订说明</h2>
        <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>
          {revision.change_brief || "（未填写修订说明）"}
        </p>
      </div>

      {phase === "drafting" && (
        <div className="draft-workspace">
          {showAiDraftActions && (
            <div className="toolbar">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void handleAiDraft()}
                disabled={aiLoading}
              >
                {aiLoading ? "提交中…" : "生成 AI 初稿"}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => id && void loadSuggestions(id)}
              >
                刷新 AI 建议
              </button>
            </div>
          )}
          {showDraftEditor ? (
            <>
              <div className="toolbar" style={{ marginBottom: "0.75rem" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void handleSaveDraft()}
                  disabled={savingDraft}
                >
                  {savingDraft ? "保存中…" : "保存草案"}
                </button>
                {ownerTransitions.map((action) => (
                  <button
                    key={action.target}
                    type="button"
                    className={`btn btn-${action.variant ?? "secondary"}`}
                    disabled={transitionLoading || (draftDirty && action.target === "in_consultation")}
                    title={
                      draftDirty && action.target === "in_consultation"
                        ? "请先保存草案再提交征求意见"
                        : undefined
                    }
                    onClick={() => void handleTransition(action.target)}
                  >
                    {transitionLoading ? "处理中…" : action.label}
                  </button>
                ))}
                {draftDirty && (
                  <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
                    有未保存修改
                  </span>
                )}
              </div>
              <div data-color-mode="light">
                <MDEditor
                  value={markdown}
                  onChange={(v) => {
                    setMarkdown(v ?? "");
                    setDraftDirty(true);
                  }}
                  height={480}
                />
              </div>
            </>
          ) : (
            <div className="info-banner">当前为起草阶段，请使用经办人账号编辑正文。</div>
          )}
          <AiSuggestionsList
            suggestions={suggestions}
            canAccept={showDraftEditor}
            onAccept={(sid) => void handleAcceptSuggestion(sid)}
            busyId={acceptBusyId}
            markdown={markdown}
          />
        </div>
      )}

      {phase === "revision" && (
        <div className="draft-workspace">
          <h2 style={{ fontSize: "1rem", margin: "0 0 0.75rem" }}>按意见改稿</h2>
          {showDraftEditor ? (
            <>
              <div className="info-banner" style={{ marginBottom: "0.75rem" }}>
                根据下方已收集意见修改正文；可刷新并采纳 AI 改稿建议。
              </div>
              <div className="toolbar">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void handleSaveDraft()}
                  disabled={savingDraft}
                >
                  {savingDraft ? "保存中…" : "保存草案"}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => id && void loadSuggestions(id)}
                >
                  刷新 AI 建议
                </button>
                {draftDirty && (
                  <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
                    有未保存修改
                  </span>
                )}
              </div>
              <div data-color-mode="light">
                <MDEditor
                  value={markdown}
                  onChange={(v) => {
                    setMarkdown(v ?? "");
                    setDraftDirty(true);
                  }}
                  height={420}
                />
              </div>
            </>
          ) : (
            <div className="info-banner">请使用经办人账号进行改稿。</div>
          )}
          <AiSuggestionsList
            suggestions={suggestions}
            canAccept={showDraftEditor}
            onAccept={(sid) => void handleAcceptSuggestion(sid)}
            busyId={acceptBusyId}
            markdown={markdown}
          />
          <div className="card" style={{ marginTop: "1rem" }}>
            <h3 style={{ margin: "0 0 0.75rem" }}>已收集意见</h3>
            {comments.length === 0 ? (
              <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: 13 }}>暂无意见</p>
            ) : showDraftEditor ? (
              <ul className="comment-list" style={{ maxHeight: "none" }}>
                {comments.map((c) => (
                  <CommentResolution
                    key={c.id}
                    comment={c}
                    busy={commentBusyId === c.id}
                    markdown={markdown}
                    onResolve={(status, note) => handleResolveComment(c.id, status, note)}
                    onAiPatch={() => handleCommentAiPatch(c.id)}
                  />
                ))}
              </ul>
            ) : (
              <ReadonlyCommentsList comments={comments} markdown={markdown} />
            )}
          </div>
        </div>
      )}

      {(phase === "pending_publish" || phase === "published" || phase === "cancelled") && (
        <div className="card">
          <p style={{ margin: 0, color: "var(--color-text-muted)" }}>
            修订任务处于「{revision.state}」状态，本页不可编辑。
            {phase === "pending_publish" && (
              <Link to={`/revisions/${revision.id}/publish`} style={{ marginLeft: "0.5rem" }}>
                前往发布审核 →
              </Link>
            )}
            {(phase === "published" || phase === "cancelled") && (
              <Link to={`/revisions/${revision.id}/view`} style={{ marginLeft: "0.5rem" }}>
                查看修订快照 →
              </Link>
            )}
          </p>
          {markdown.trim() && (
            <div data-color-mode="light" style={{ marginTop: "1rem" }}>
              <h3 style={{ fontSize: "1rem", margin: "0 0 0.5rem" }}>正文（只读）</h3>
              <MDEditor.Markdown source={markdown} />
            </div>
          )}
          {comments.length > 0 && (
            <>
              <h3 style={{ marginTop: "1rem" }}>历史意见</h3>
              <ReadonlyCommentsList comments={comments} markdown={markdown} />
            </>
          )}
        </div>
      )}
    </>
  );
}
