import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { NotificationItem } from "../api/types";

export function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [marking, setMarking] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listNotifications();
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleMarkAll() {
    setMarking(true);
    setError(null);
    try {
      await api.markNotificationsRead();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setMarking(false);
    }
  }

  const unread = items.filter((n) => !n.read).length;

  return (
    <>
      <h1 className="page-title">我的通知</h1>
      <div className="info-banner">
        系统在指派评审人、收到评审意见、提交发布审核等关键节点生成待办通知，便于及时跟进。
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="card">
        <div className="toolbar" style={{ justifyContent: "space-between", marginBottom: "0.75rem" }}>
          <span style={{ color: "var(--color-text-muted)", fontSize: 13 }}>
            共 {items.length} 条，未读 {unread} 条
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={marking || unread === 0}
            onClick={() => void handleMarkAll()}
          >
            {marking ? "处理中…" : "全部标记为已读"}
          </button>
        </div>

        {loading ? (
          <p style={{ margin: 0, color: "var(--color-text-muted)" }}>加载中…</p>
        ) : items.length === 0 ? (
          <p style={{ margin: 0, color: "var(--color-text-muted)" }}>暂无通知</p>
        ) : (
          <ul className="comment-list" style={{ maxHeight: "none" }}>
            {items.map((n) => (
              <li key={n.id} className="comment-item">
                <div className="comment-meta">
                  {n.read ? "已读" : "未读"} · {new Date(n.created_at).toLocaleString("zh-CN")}
                </div>
                <p style={{ margin: "0.25rem 0", fontWeight: n.read ? 400 : 600 }}>{n.message}</p>
                {n.revision_id && (
                  <Link
                    to={`/revisions/${n.revision_id}`}
                    className="btn btn-secondary"
                    style={{ fontSize: 12 }}
                  >
                    查看修订
                  </Link>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
