import MDEditor from "@uiw/react-md-editor";
import "@uiw/react-md-editor/markdown-editor.css";
import "@uiw/react-markdown-preview/markdown.css";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Comment, Revision, RevisionState } from "../api/types";
import { ReviewerPanel } from "../components/ReviewerPanel";
import { SectionOutline } from "../components/SectionOutline";
import { SectionLabel } from "../components/SectionLabel";
import { StateBadge } from "../components/StateBadge";
import { WorkflowStepper } from "../components/WorkflowStepper";
import { getAuthRole, isOwnerLike, isReviewer } from "../lib/auth";
import {
  buildSectionTree,
  GENERAL_SECTION_ID,
  getSectionTitle,
  sectionOptions,
} from "../lib/sections";
import {
  getOwnerTransitions,
  getPostTransitionMessage,
} from "../lib/revisionWorkflow";

const COMMENT_STATUS: Record<string, string> = {
  open: "待处理",
  accepted: "已采纳",
  rejected: "不予修改",
  deferred: "暂缓",
};

export function ConsultationPage() {
  const { id } = useParams<{ id: string }>();
  const reviewerUser = isReviewer(getAuthRole());
  const ownerLike = isOwnerLike(getAuthRole());

  const [revision, setRevision] = useState<Revision | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [markdown, setMarkdown] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [infoLink, setInfoLink] = useState<{ to: string; label: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [newSectionId, setNewSectionId] = useState(GENERAL_SECTION_ID);
  const [newCommentBody, setNewCommentBody] = useState("");
  const [commentSubmitting, setCommentSubmitting] = useState(false);
  const [transitionLoading, setTransitionLoading] = useState(false);
  const commentFormRef = useRef<HTMLDivElement>(null);

  const sections = useMemo(() => buildSectionTree(markdown), [markdown]);
  const sectionSelectOptions = useMemo(() => sectionOptions(sections), [sections]);

  const ownerTransitions = useMemo(
    () => (revision && ownerLike ? getOwnerTransitions(revision.state) : []),
    [revision, ownerLike],
  );

  const loadComments = useCallback(async (revisionId: string) => {
    const list = await api.listComments(revisionId);
    setComments(list);
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
        if (rev.state !== "in_consultation") {
          setError("当前不在征求意见阶段，请从制度详情进入对应工作台。");
          setRevision(rev);
          return;
        }
        setRevision(rev);
        const draft = await api.getDraftMarkdown(id);
        if (cancelled) return;
        setMarkdown(draft.markdown);
        await loadComments(id);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, loadComments]);

  async function handleTransition(targetState: string) {
    if (!id) return;
    setTransitionLoading(true);
    setError(null);
    setInfo(null);
    setInfoLink(null);
    try {
      const rev = await api.transitionRevision(id, targetState);
      setRevision(rev);
      const guidance = getPostTransitionMessage(targetState as RevisionState, id);
      setInfo(guidance.message);
      setInfoLink(guidance.link ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "状态更新失败");
    } finally {
      setTransitionLoading(false);
    }
  }

  function handleSelectSectionForComment(sectionId: string) {
    setNewSectionId(sectionId);
    commentFormRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const textarea = commentFormRef.current?.querySelector("textarea");
    if (textarea instanceof HTMLTextAreaElement) {
      textarea.focus();
    }
  }

  async function handleAddComment(e: FormEvent) {
    e.preventDefault();
    if (!id || !newCommentBody.trim()) return;
    setCommentSubmitting(true);
    setError(null);
    try {
      await api.createComment(id, newSectionId, newCommentBody.trim());
      setNewCommentBody("");
      await loadComments(id);
      setInfo("意见已提交，经办人将在改稿阶段处理。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交意见失败");
    } finally {
      setCommentSubmitting(false);
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

  return (
    <>
      <p>
        <Link to={`/policies/${revision.policy_id}`}>← 返回制度详情</Link>
        {" · "}
        <Link to={`/revisions/${revision.id}`}>起草工作台</Link>
      </p>
      <div className="toolbar">
        <h1 className="page-title" style={{ margin: 0, flex: 1 }}>
          征求意见
        </h1>
        <StateBadge state={revision.state} />
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

      {revision.state === "in_consultation" && (
        <>
          <div className="info-banner">
            多部门征求意见阶段：经办人指定评审人并跟踪反馈；评审人针对章节提交意见。起草与改稿请使用「起草工作台」。
          </div>

          {ownerLike && id && <ReviewerPanel revisionId={id} canManage />}

          {ownerTransitions.length > 0 && (
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
            <h2 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>制度正文（只读）</h2>
            {reviewerUser && (
              <>
                <p style={{ margin: "0 0 0.5rem", fontSize: 13, color: "var(--color-text-muted)" }}>
                  阅读正文后，可在下方章节列表点击「对此节提意见」，或在提交表单中选择章节。
                </p>
                <SectionOutline
                  sections={sections}
                  selectedSectionId={newSectionId}
                  onSelectSection={handleSelectSectionForComment}
                  showCommentActions
                />
              </>
            )}
            <div data-color-mode="light" style={{ marginTop: "1rem" }}>
              <MDEditor.Markdown source={markdown || "（正文为空）"} />
            </div>
          </div>

          <div className="card">
            <h2 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>已提交意见</h2>
            {comments.length === 0 ? (
              <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: 13 }}>暂无意见</p>
            ) : (
              <ul className="comment-list" style={{ maxHeight: "none" }}>
                {comments.map((c) => (
                  <li key={c.id} className="comment-item">
                    <div className="comment-meta">
                      <SectionLabel sectionId={c.section_id} markdown={markdown} /> ·{" "}
                      {COMMENT_STATUS[c.status] ?? c.status}
                    </div>
                    <p style={{ margin: 0 }}>{c.body}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {reviewerUser ? (
            <div className="card" style={{ marginTop: "1.25rem" }} ref={commentFormRef}>
              <h2 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>提交意见</h2>
              <form onSubmit={(e) => void handleAddComment(e)}>
                <div className="form-group">
                  <label htmlFor="comment_section">意见针对的章节</label>
                  <select
                    id="comment_section"
                    value={newSectionId}
                    onChange={(e) => setNewSectionId(e.target.value)}
                  >
                    {sectionSelectOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  {newSectionId !== GENERAL_SECTION_ID && (
                    <p style={{ margin: "0.35rem 0 0", fontSize: 12, color: "var(--color-text-muted)" }}>
                      已选：{getSectionTitle(newSectionId, sections)}
                    </p>
                  )}
                </div>
                <div className="form-group">
                  <label htmlFor="comment_body">意见内容</label>
                  <textarea
                    id="comment_body"
                    rows={4}
                    value={newCommentBody}
                    onChange={(e) => setNewCommentBody(e.target.value)}
                    required
                  />
                </div>
                <button type="submit" className="btn btn-primary" disabled={commentSubmitting}>
                  {commentSubmitting ? "提交中…" : "提交意见"}
                </button>
              </form>
            </div>
          ) : (
            <div className="info-banner" style={{ marginTop: "1.25rem" }}>
              请使用评审人账号（如 reviewer1）登录后在本页提交意见。
            </div>
          )}
        </>
      )}
    </>
  );
}
