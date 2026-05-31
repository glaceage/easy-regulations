import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { RevisionReviewer } from "../api/types";

export function ReviewerPanel({
  revisionId,
  canManage,
}: {
  revisionId: string;
  canManage: boolean;
}) {
  const [reviewers, setReviewers] = useState<RevisionReviewer[]>([]);
  const [username, setUsername] = useState("");
  const [mandatory, setMandatory] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await api.listReviewers(revisionId);
      setReviewers(list);
    } catch {
      setReviewers([]);
    }
  }, [revisionId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleAssign(e: FormEvent) {
    e.preventDefault();
    if (!username.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.assignReviewer(revisionId, username.trim(), mandatory);
      setUsername("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "指定失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemove(reviewerId: string) {
    setError(null);
    try {
      await api.removeReviewer(revisionId, reviewerId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "移除失败");
    }
  }

  return (
    <div className="card" style={{ marginBottom: "1.25rem" }}>
      <h2 style={{ margin: "0 0 0.75rem", fontSize: "1rem" }}>指定评审人</h2>
      <p style={{ margin: "0 0 0.75rem", color: "var(--color-text-muted)", fontSize: 13 }}>
        在多部门征求意见阶段指定相关部门负责人；标记为「必反馈」的评审人须在发布前提交意见。
      </p>
      {error && <div className="error-banner">{error}</div>}
      {reviewers.length === 0 ? (
        <p style={{ margin: "0 0 0.75rem", color: "var(--color-text-muted)", fontSize: 13 }}>
          尚未指定评审人，请添加相关部门负责人。
        </p>
      ) : (
        <ul className="comment-list" style={{ maxHeight: "none", marginBottom: "0.75rem" }}>
          {reviewers.map((r) => (
            <li key={r.id} className="comment-item">
              <div className="comment-meta">
                {r.display_name}（{r.username}）
                {r.is_mandatory ? " · 必反馈" : " · 参考"}
              </div>
              {canManage && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ fontSize: 12, marginTop: "0.25rem" }}
                  onClick={() => void handleRemove(r.id)}
                >
                  移除
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canManage && (
        <form onSubmit={(e) => void handleAssign(e)} className="toolbar" style={{ alignItems: "flex-end" }}>
          <div className="form-group" style={{ margin: 0, flex: 1 }}>
            <label htmlFor="reviewer_username">评审人用户名</label>
            <input
              id="reviewer_username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="reviewer1"
            />
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: 13 }}>
            <input
              type="checkbox"
              checked={mandatory}
              onChange={(e) => setMandatory(e.target.checked)}
            />
            必反馈
          </label>
          <button type="submit" className="btn btn-secondary" disabled={submitting}>
            {submitting ? "添加中…" : "添加评审人"}
          </button>
        </form>
      )}
    </div>
  );
}
