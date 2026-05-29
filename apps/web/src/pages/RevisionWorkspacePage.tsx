import MDEditor from "@uiw/react-md-editor";
import "@uiw/react-md-editor/markdown-editor.css";
import "@uiw/react-markdown-preview/markdown.css";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Comment, LlmSuggestion, Revision } from "../api/types";
import { StateBadge } from "../components/StateBadge";

const COMMENT_STATUS: Record<string, string> = {
  open: "待处理",
  resolved: "已解决",
  wont_fix: "不予修改",
};

export function RevisionWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const [revision, setRevision] = useState<Revision | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [suggestions, setSuggestions] = useState<LlmSuggestion[]>([]);
  const [markdown, setMarkdown] = useState("# 制度正文\n\n在此编辑 Markdown 草案。\n");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);
  const [newSectionId, setNewSectionId] = useState("sec-1");
  const [newCommentBody, setNewCommentBody] = useState("");
  const [commentSubmitting, setCommentSubmitting] = useState(false);

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
        await Promise.all([loadComments(id), loadSuggestions(id)]);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, loadComments, loadSuggestions]);

  async function handleAiDraft() {
    if (!id) return;
    setAiLoading(true);
    setInfo(null);
    setError(null);
    try {
      const { job_id } = await api.enqueueAiDraft(id);
      setInfo(`AI 草案生成任务已提交（任务 ID：${job_id}）。完成后请刷新页面查看建议。`);
      setTimeout(() => {
        void loadSuggestions(id);
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setAiLoading(false);
    }
  }

  async function handleAddComment(e: FormEvent) {
    e.preventDefault();
    if (!id || !newCommentBody.trim()) return;
    setCommentSubmitting(true);
    setError(null);
    try {
      await api.createComment(id, newSectionId.trim() || "sec-1", newCommentBody.trim());
      setNewCommentBody("");
      await loadComments(id);
      setInfo("意见已提交");
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
      </p>
      <div className="toolbar">
        <h1 className="page-title" style={{ margin: 0, flex: 1 }}>
          修订工作台
        </h1>
        <StateBadge state={revision.state} />
        {revision.target_version_label && (
          <span style={{ fontSize: 14, color: "var(--color-text-muted)" }}>
            目标版本：{revision.target_version_label}
          </span>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}
      {info && <div className="info-banner">{info}</div>}

      <div className="card" style={{ marginBottom: "1.25rem" }}>
        <h2 style={{ margin: "0 0 0.5rem", fontSize: "1rem" }}>修订说明</h2>
        <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>
          {revision.change_brief || "（未填写修订说明）"}
        </p>
      </div>

      <div className="workspace-layout">
        <div>
          <div className="toolbar">
            <button type="button" className="btn btn-primary" onClick={() => void handleAiDraft()} disabled={aiLoading}>
              {aiLoading ? "提交中…" : "生成 AI 草案"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => id && void loadSuggestions(id)}
            >
              刷新 AI 建议
            </button>
          </div>
          <div className="info-banner" style={{ marginBottom: "0.75rem" }}>
            正文保存 API 尚未接入；当前编辑器为本地预览。导入 docx 或 AI 生成后，建议将在此加载。
          </div>
          <div data-color-mode="light">
            <MDEditor value={markdown} onChange={(v) => setMarkdown(v ?? "")} height={480} />
          </div>
          {suggestions.length > 0 && (
            <div className="card" style={{ marginTop: "1rem" }}>
              <h3 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>AI 修改建议</h3>
              <ul className="comment-list" style={{ maxHeight: "none" }}>
                {suggestions.map((s) => (
                  <li key={s.id} className="comment-item">
                    <div className="comment-meta">
                      {s.section_id} · {s.action} · {s.status}
                    </div>
                    <p style={{ margin: "0.25rem 0" }}>{s.rationale}</p>
                    <pre style={{ fontSize: 12, overflow: "auto", background: "#f8fafb", padding: "0.5rem" }}>
                      {s.suggested_markdown.slice(0, 400)}
                      {s.suggested_markdown.length > 400 ? "…" : ""}
                    </pre>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <aside className="card comments-panel">
          <h3>征求意见</h3>
          <ul className="comment-list">
            {comments.length === 0 ? (
              <li style={{ color: "var(--color-text-muted)", fontSize: 13 }}>暂无意见</li>
            ) : (
              comments.map((c) => (
                <li key={c.id} className="comment-item">
                  <div className="comment-meta">
                    {c.section_id} · {COMMENT_STATUS[c.status] ?? c.status}
                  </div>
                  <p style={{ margin: 0 }}>{c.body}</p>
                </li>
              ))
            )}
          </ul>
          <form onSubmit={(e) => void handleAddComment(e)} style={{ marginTop: "1rem" }}>
            <div className="form-group">
              <label htmlFor="section_id">章节 ID</label>
              <input
                id="section_id"
                value={newSectionId}
                onChange={(e) => setNewSectionId(e.target.value)}
                placeholder="sec-1"
              />
            </div>
            <div className="form-group">
              <label htmlFor="comment_body">意见内容</label>
              <textarea
                id="comment_body"
                rows={3}
                value={newCommentBody}
                onChange={(e) => setNewCommentBody(e.target.value)}
                required
              />
            </div>
            <button type="submit" className="btn btn-secondary" style={{ width: "100%" }} disabled={commentSubmitting}>
              {commentSubmitting ? "提交中…" : "提交意见"}
            </button>
          </form>
        </aside>
      </div>
    </>
  );
}
