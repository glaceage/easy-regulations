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
      {error && <div className="error-banner">{error}</div>}
      <div className="card">
        {loading ? (
          <p style={{ color: "var(--color-text-muted)" }}>加载中…</p>
        ) : policies.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)" }}>暂无制度，请通过 API 或种子脚本创建。</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>编码</th>
                <th>标题</th>
                <th>归口部门</th>
                <th>分类</th>
                <th>更新时间</th>
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
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
