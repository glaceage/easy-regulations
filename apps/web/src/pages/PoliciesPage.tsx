import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Policy } from "../api/types";

export function PoliciesPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.listPolicies();
        if (!cancelled) setPolicies(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <h1 className="page-title">制度库</h1>
      <div className="toolbar">
        <Link to="/admin/policies/new" className="btn btn-primary">
          新建制度
        </Link>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <div className="card">
        {loading ? (
          <p style={{ color: "var(--color-text-muted)" }}>加载中…</p>
        ) : policies.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)" }}>
            暂无制度，
            <Link to="/admin/policies/new">点击新建</Link>
            或通过种子脚本创建。
          </p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>编码</th>
                <th>标题</th>
                <th>归口部门</th>
                <th>分类</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link to={`/policies/${p.id}`}>{p.code}</Link>
                  </td>
                  <td>{p.title}</td>
                  <td>{p.owner_department}</td>
                  <td>{p.category || "—"}</td>
                  <td>{new Date(p.updated_at).toLocaleString("zh-CN")}</td>
                  <td>
                    <Link to={`/policies/${p.id}#revisions`} className="btn btn-primary" style={{ fontSize: 13 }}>
                      修订 / AI 草案
                    </Link>
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
