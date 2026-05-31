import MDEditor from "@uiw/react-md-editor";
import "@uiw/react-md-editor/markdown-editor.css";
import "@uiw/react-markdown-preview/markdown.css";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Comment, Revision } from "../api/types";
import { StateBadge } from "../components/StateBadge";
import { SectionLabel } from "../components/SectionLabel";
import { WorkflowStepper } from "../components/WorkflowStepper";

const COMMENT_STATUS: Record<string, string> = {
  open: "待处理",
  accepted: "已采纳",
  rejected: "不予修改",
  deferred: "暂缓",
};

export function RevisionViewPage() {
  const { id } = useParams<{ id: string }>();
  const [revision, setRevision] = useState<Revision | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [markdown, setMarkdown] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
        const [draft, commentList] = await Promise.all([
          api.getDraftMarkdown(id),
          api.listComments(id),
        ]);
        if (cancelled) return;
        setMarkdown(draft.markdown);
        setComments(commentList);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

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
          修订快照
        </h1>
        <StateBadge state={revision.state} />
        {revision.target_version_label && (
          <span style={{ fontSize: 14, color: "var(--color-text-muted)" }}>
            版本：{revision.target_version_label}
          </span>
        )}
      </div>

      <WorkflowStepper state={revision.state} />

      {error && <div className="error-banner">{error}</div>}

      <div className="card" style={{ marginBottom: "1.25rem" }}>
        <h2 style={{ margin: "0 0 0.5rem", fontSize: "1rem" }}>修订说明</h2>
        <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>
          {revision.change_brief || "（未填写）"}
        </p>
      </div>

      <div className="card" style={{ marginBottom: "1.25rem" }}>
        <h2 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>正文（只读）</h2>
        <div data-color-mode="light">
          <MDEditor.Markdown source={markdown || "（正文为空）"} />
        </div>
      </div>

      {comments.length > 0 && (
        <div className="card">
          <h2 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>评审意见</h2>
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
        </div>
      )}
    </>
  );
}
