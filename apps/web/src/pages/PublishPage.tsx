import MDEditor from "@uiw/react-md-editor";
import "@uiw/react-md-editor/markdown-editor.css";
import "@uiw/react-markdown-preview/markdown.css";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Comment, Revision } from "../api/types";
import { StateBadge } from "../components/StateBadge";
import { SectionLabel } from "../components/SectionLabel";
import { WorkflowStepper } from "../components/WorkflowStepper";
import { canPublish, getAuthRole } from "../lib/auth";

const COMMENT_STATUS: Record<string, string> = {
  open: "待处理",
  accepted: "已采纳",
  rejected: "不予修改",
  deferred: "暂缓",
};

async function pollJob(jobId: string, timeoutMs = 120_000): Promise<{ pdf_key?: string }> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const job = await api.getJobStatus(jobId);
    if (job.status === "complete") {
      if (job.error) throw new Error(job.error);
      const result = job.result as { pdf_key?: string } | null;
      return result ?? {};
    }
    if (job.status === "failed" || job.error) {
      throw new Error(job.error ?? "后台任务失败");
    }
  }
  throw new Error("PDF 生成超时，请稍后重试");
}

export function PublishPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const admin = canPublish(getAuthRole());

  const [revision, setRevision] = useState<Revision | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [markdown, setMarkdown] = useState("");
  const [pdfKey, setPdfKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [publishLoading, setPublishLoading] = useState(false);
  const [versionLabel, setVersionLabel] = useState("");
  const [savingVersion, setSavingVersion] = useState(false);

  const loadData = useCallback(async (revisionId: string) => {
    const [rev, draft, commentList] = await Promise.all([
      api.getRevision(revisionId),
      api.getDraftMarkdown(revisionId),
      api.listComments(revisionId),
    ]);
    setRevision(rev);
    setMarkdown(draft.markdown);
    setComments(commentList);
    setVersionLabel(rev.target_version_label ?? "");
  }, []);

  async function handleSaveVersion() {
    if (!id || !versionLabel.trim()) return;
    setSavingVersion(true);
    setError(null);
    setInfo(null);
    try {
      const updated = await api.updateRevisionMeta(id, {
        target_version_label: versionLabel.trim(),
      });
      setRevision(updated);
      setInfo("目标版本号已更新。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新版本号失败");
    } finally {
      setSavingVersion(false);
    }
  }

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        await loadData(id);
        if (cancelled) return;
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, loadData]);

  async function handleGeneratePdf() {
    if (!id) return;
    setPdfLoading(true);
    setError(null);
    setInfo(null);
    try {
      const { job_id } = await api.requestPublishPdf(id);
      setInfo("PDF 预览生成中…");
      const result = await pollJob(job_id);
      if (result.pdf_key) {
        setPdfKey(result.pdf_key);
        setInfo("PDF 预览已生成，可点击下方链接下载。");
      } else {
        setInfo("PDF 任务已完成。");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "PDF 生成失败");
    } finally {
      setPdfLoading(false);
    }
  }

  async function handlePublish() {
    if (!id || !revision) return;
    setPublishLoading(true);
    setError(null);
    setInfo(null);
    try {
      const result = await api.publishRevision(id);
      setInfo(`已发布版本 ${result.version_label}。`);
      navigate(`/policies/${revision.policy_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "发布失败");
    } finally {
      setPublishLoading(false);
    }
  }

  async function handleDownloadPdf() {
    if (!id || !pdfKey) return;
    try {
      const blob = await api.fetchRevisionFile(id, pdfKey);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "preview.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "下载失败");
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

  if (revision.state !== "pending_publish") {
    return (
      <>
        <p>
          <Link to={`/policies/${revision.policy_id}`}>← 返回制度详情</Link>
        </p>
        <div className="error-banner">
          当前状态为「{revision.state}」，仅「待发布」阶段可在此页面发布。
          <Link to={`/revisions/${revision.id}`} style={{ marginLeft: "0.5rem" }}>
            返回起草工作台
          </Link>
        </div>
      </>
    );
  }

  const openCount = comments.filter((c) => c.status === "open").length;

  return (
    <>
      <p>
        <Link to={`/policies/${revision.policy_id}`}>← 返回制度详情</Link>
        {" · "}
        <Link to={`/revisions/${revision.id}`}>起草工作台</Link>
      </p>
      <div className="toolbar">
        <h1 className="page-title" style={{ margin: 0, flex: 1 }}>
          发布审核
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
      {info && <div className="info-banner">{info}</div>}

      <div className="info-banner">
        请复核最终正文与意见处理摘要。制度管理员确认后可发布正式版本。
        {openCount > 0 && (
          <strong style={{ color: "var(--color-danger)", marginLeft: "0.5rem" }}>
            仍有 {openCount} 条未处理意见，无法发布。
          </strong>
        )}
        {!revision.target_version_label && (
          <strong style={{ color: "var(--color-danger)", marginLeft: "0.5rem" }}>
            目标版本号为空，发布前必须补充。
          </strong>
        )}
      </div>

      {admin && (
        <div className="card" style={{ marginBottom: "1.25rem" }}>
          <h2 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>目标版本号</h2>
          <form
            className="toolbar"
            style={{ alignItems: "flex-end" }}
            onSubmit={(e) => {
              e.preventDefault();
              void handleSaveVersion();
            }}
          >
            <div className="form-group" style={{ margin: 0, flex: 1, maxWidth: 240 }}>
              <label htmlFor="target_version_label">正式版本号</label>
              <input
                id="target_version_label"
                value={versionLabel}
                onChange={(e) => setVersionLabel(e.target.value)}
                placeholder="例如 v2.0"
              />
            </div>
            <button
              type="submit"
              className="btn btn-secondary"
              disabled={savingVersion || !versionLabel.trim()}
            >
              {savingVersion ? "保存中…" : "保存版本号"}
            </button>
          </form>
        </div>
      )}

      <div className="card" style={{ marginBottom: "1.25rem" }}>
        <h2 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>最终正文（只读）</h2>
        <div data-color-mode="light">
          <MDEditor.Markdown source={markdown || "（正文为空）"} />
        </div>
      </div>

      <div className="card" style={{ marginBottom: "1.25rem" }}>
        <h2 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>意见处理摘要</h2>
        {comments.length === 0 ? (
          <p style={{ margin: 0, color: "var(--color-text-muted)" }}>本次修订无评审意见</p>
        ) : (
          <ul className="comment-list" style={{ maxHeight: "none" }}>
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
        )}
      </div>

      <div className="toolbar">
        <button
          type="button"
          className="btn btn-secondary"
          disabled={pdfLoading}
          onClick={() => void handleGeneratePdf()}
        >
          {pdfLoading ? "生成中…" : "生成 PDF 预览"}
        </button>
        {pdfKey && (
          <button type="button" className="btn btn-secondary" onClick={() => void handleDownloadPdf()}>
            下载 PDF 预览
          </button>
        )}
        {admin ? (
          <button
            type="button"
            className="btn btn-primary"
            disabled={publishLoading || openCount > 0 || !revision.target_version_label}
            onClick={() => void handlePublish()}
          >
            {publishLoading ? "发布中…" : "确认发布"}
          </button>
        ) : (
          <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
            请使用制度管理员账号（如 admin）登录后发布
          </span>
        )}
      </div>
    </>
  );
}
