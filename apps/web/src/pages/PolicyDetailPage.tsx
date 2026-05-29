import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Policy } from "../api/types";

export function PolicyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await api.getPolicy(id);
        if (!cancelled) setPolicy(data);
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

  if (error || !policy) {
    return (
      <>
        <p>
          <Link to="/policies">← 返回制度库</Link>
        </p>
        <div className="error-banner">{error ?? "制度不存在"}</div>
      </>
    );
  }

  return (
    <>
      <p>
        <Link to="/policies">← 返回制度库</Link>
      </p>
      <h1 className="page-title">{policy.title}</h1>
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
        <div className="info-banner">
          版本历史与修订任务列表将在后续版本通过 API 展示。若已知修订任务 ID，可直接访问
          {" "}
          <code>/revisions/&lt;id&gt;</code>
          进入工作台。
        </div>
      </div>
    </>
  );
}
