import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Policy, Revision } from "../api/types";
import { StateBadge } from "../components/StateBadge";
import { getAuthRole, isOwnerLike, isReviewer } from "../lib/auth";
import { getRevisionPrimaryRoute } from "../lib/revisionWorkflow";

export function PolicyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const role = getAuthRole();
  const ownerLike = isOwnerLike(role);
  const reviewer = isReviewer(role);

  const [policy, setPolicy] = useState<Policy | null>(null);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [policyError, setPolicyError] = useState<string | null>(null);
  const [revisionsError, setRevisionsError] = useState<string | null>(null);
  const [loadingPolicy, setLoadingPolicy] = useState(true);
  const [loadingRevisions, setLoadingRevisions] = useState(true);
  const [showNewRevision, setShowNewRevision] = useState(false);
  const [changeBrief, setChangeBrief] = useState("");
  const [targetVersion, setTargetVersion] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    (async () => {
      setLoadingPolicy(true);
      setPolicyError(null);
      try {
        const data = await api.getPolicy(id);
        if (!cancelled) setPolicy(data);
      } catch (err) {
        if (!cancelled) setPolicyError(err instanceof Error ? err.message : "加载失败");
      } finally {
        if (!cancelled) setLoadingPolicy(false);
      }
    })();

    (async () => {
      setLoadingRevisions(true);
      setRevisionsError(null);
      try {
        const list = await api.listPolicyRevisions(id);
        if (!cancelled) setRevisions(list);
      } catch (err) {
        if (!cancelled) {
          setRevisions([]);
          setRevisionsError(err instanceof Error ? err.message : "修订任务加载失败");
        }
      } finally {
        if (!cancelled) setLoadingRevisions(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleCreateRevision(e: FormEvent) {
    e.preventDefault();
    if (!id) return;
    setCreating(true);
    setCreateError(null);
    try {
      const rev = await api.createRevision(id, changeBrief.trim(), targetVersion.trim());
      setShowNewRevision(false);
      setChangeBrief("");
      setTargetVersion("");
      navigate(getRevisionPrimaryRoute(rev.id, rev.state));
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setCreating(false);
    }
  }

  if (loadingPolicy) {
    return <p style={{ color: "var(--color-text-muted)" }}>加载中…</p>;
  }

  if (policyError || !policy) {
    return (
      <>
        <p>
          <Link to="/policies">← 返回制度库</Link>
        </p>
        <div className="error-banner">{policyError ?? "制度不存在"}</div>
      </>
    );
  }

  const activeWorkspaceRevision = revisions.find(
    (r) => r.state === "draft" || r.state === "in_revision",
  );

  function renderRevisionActions(rev: Revision) {
    if (reviewer) {
      if (rev.state === "in_consultation") {
        return (
          <Link
            to={`/revisions/${rev.id}/consultation`}
            className="btn btn-primary"
            style={{ fontSize: 13 }}
          >
            进入评审
          </Link>
        );
      }
      if (rev.state === "published" || rev.state === "cancelled") {
        return (
          <Link to={`/revisions/${rev.id}/view`} className="btn btn-secondary" style={{ fontSize: 13 }}>
            查看
          </Link>
        );
      }
      return (
        <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
          等待经办人推进流程
        </span>
      );
    }

    const primaryRoute = getRevisionPrimaryRoute(rev.id, rev.state);
    switch (rev.state) {
      case "in_consultation":
        return (
          <>
            <Link to={`/revisions/${rev.id}`} className="btn btn-secondary" style={{ fontSize: 13 }}>
              起草工作台
            </Link>
            <Link to={primaryRoute} className="btn btn-primary" style={{ fontSize: 13 }}>
              征求意见
            </Link>
          </>
        );
      case "pending_publish":
        return (
          <Link to={primaryRoute} className="btn btn-primary" style={{ fontSize: 13 }}>
            发布审核
          </Link>
        );
      case "published":
      case "cancelled":
        return (
          <Link to={primaryRoute} className="btn btn-secondary" style={{ fontSize: 13 }}>
            查看
          </Link>
        );
      default:
        return (
          <Link to={primaryRoute} className="btn btn-primary" style={{ fontSize: 13 }}>
            起草工作台
          </Link>
        );
    }
  }

  return (
    <>
      <p>
        <Link to="/policies">← 返回制度库</Link>
      </p>
      <h1 className="page-title">{policy.title}</h1>

      {reviewer && (
        <div className="toolbar" style={{ marginBottom: "1rem" }}>
          <Link to="/reviews" className="btn btn-primary">
            我的评审任务
          </Link>
        </div>
      )}

      {activeWorkspaceRevision && ownerLike && (
        <div className="toolbar" style={{ marginBottom: "1rem" }}>
          <Link
            to={getRevisionPrimaryRoute(activeWorkspaceRevision.id, activeWorkspaceRevision.state)}
            className="btn btn-primary"
          >
            起草工作台（{activeWorkspaceRevision.target_version_label || "草案"}）
          </Link>
          <span style={{ fontSize: 14, color: "var(--color-text-muted)" }}>
            编辑正文、生成 AI 草案或处理改稿
          </span>
        </div>
      )}

      {ownerLike && (
        <div className="toolbar" style={{ marginBottom: "1rem" }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setShowNewRevision((v) => !v)}
          >
            {showNewRevision ? "取消" : "新建修订任务"}
          </button>
        </div>
      )}

      {showNewRevision && ownerLike && (
        <div className="card" style={{ marginBottom: "1rem", maxWidth: 560 }}>
          {createError && <div className="error-banner">{createError}</div>}
          <form onSubmit={(e) => void handleCreateRevision(e)}>
            <div className="form-group">
              <label htmlFor="target_version">目标版本</label>
              <input
                id="target_version"
                value={targetVersion}
                onChange={(e) => setTargetVersion(e.target.value)}
                placeholder="v2.0"
                required
              />
            </div>
            <div className="form-group">
              <label htmlFor="change_brief">修订说明（至少 10 字）</label>
              <textarea
                id="change_brief"
                rows={3}
                value={changeBrief}
                onChange={(e) => setChangeBrief(e.target.value)}
                required
                minLength={10}
              />
            </div>
            <button type="submit" className="btn btn-primary" disabled={creating}>
              {creating ? "创建中…" : "创建修订任务"}
            </button>
          </form>
        </div>
      )}

      <div className="card">
        <dl className="meta-grid">
          <div className="meta-item">
            <dt>制度编码</dt>
            <dd>{policy.code}</dd>
          </div>
          <div className="meta-item">
            <dt>归口部门</dt>
            <dd>{policy.owner_department}</dd>
          </div>
          <div className="meta-item">
            <dt>分类</dt>
            <dd>{policy.category || "—"}</dd>
          </div>
          <div className="meta-item">
            <dt>当前版本 ID</dt>
            <dd>{policy.current_version_id ?? "尚无已发布版本"}</dd>
          </div>
          <div className="meta-item">
            <dt>创建时间</dt>
            <dd>{new Date(policy.created_at).toLocaleString("zh-CN")}</dd>
          </div>
          <div className="meta-item">
            <dt>更新时间</dt>
            <dd>{new Date(policy.updated_at).toLocaleString("zh-CN")}</dd>
          </div>
        </dl>
      </div>

      <h2 id="revisions" style={{ marginTop: "1.5rem", fontSize: "1.125rem" }}>
        修订任务
      </h2>
      <div className="card">
        {loadingRevisions ? (
          <p style={{ margin: 0, color: "var(--color-text-muted)" }}>正在加载修订任务…</p>
        ) : revisionsError ? (
          <div className="error-banner">
            {revisionsError}
            <p style={{ margin: "0.5rem 0 0", fontSize: 13 }}>
              请先 <Link to="/login">重新登录</Link>，再返回本页。
            </p>
          </div>
        ) : revisions.length === 0 ? (
          <p style={{ margin: 0, color: "var(--color-text-muted)" }}>暂无修订任务</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>目标版本</th>
                <th>状态</th>
                <th>修订说明</th>
                <th>更新时间</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {revisions.map((rev) => (
                <tr key={rev.id}>
                  <td>{rev.target_version_label || "—"}</td>
                  <td>
                    <StateBadge state={rev.state} />
                  </td>
                  <td style={{ maxWidth: 280 }}>
                    {rev.change_brief
                      ? rev.change_brief.length > 60
                        ? `${rev.change_brief.slice(0, 60)}…`
                        : rev.change_brief
                      : "—"}
                  </td>
                  <td>{new Date(rev.updated_at).toLocaleString("zh-CN")}</td>
                  <td>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                      {renderRevisionActions(rev)}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
