import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ReviewAssignment } from "../api/types";
import { StateBadge } from "../components/StateBadge";

const FEEDBACK_LABEL: Record<ReviewAssignment["feedback_status"], string> = {
  awaiting: "待反馈（必反馈）",
  optional: "可反馈",
  submitted: "已提交意见",
  closed: "已结束",
};

const FEEDBACK_CLASS: Record<ReviewAssignment["feedback_status"], string> = {
  awaiting: "review-badge review-badge--awaiting",
  optional: "review-badge review-badge--optional",
  submitted: "review-badge review-badge--submitted",
  closed: "review-badge review-badge--closed",
};

export function ReviewInboxPage() {
  const [assignments, setAssignments] = useState<ReviewAssignment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.listReviewAssignments();
        if (!cancelled) setAssignments(data);
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

  const pending = useMemo(
    () => assignments.filter((a) => a.feedback_status === "awaiting"),
    [assignments],
  );
  const active = useMemo(
    () => assignments.filter((a) => a.revision_state === "in_consultation"),
    [assignments],
  );

  return (
    <>
      <h1 className="page-title">我的评审</h1>
      <div className="info-banner">
        评审人在此查看被指派的制度修订任务。处于「征求意见」阶段时，点击「开始评审」阅读正文并按章节提交意见。
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="review-stats">
        <div className="review-stat-card">
          <div className="review-stat-value">{pending.length}</div>
          <div className="review-stat-label">待反馈（必反馈）</div>
        </div>
        <div className="review-stat-card">
          <div className="review-stat-value">{active.length}</div>
          <div className="review-stat-label">进行中（征求意见）</div>
        </div>
        <div className="review-stat-card">
          <div className="review-stat-value">{assignments.length}</div>
          <div className="review-stat-label">全部指派</div>
        </div>
      </div>

      <div className="card">
        {loading ? (
          <p style={{ margin: 0, color: "var(--color-text-muted)" }}>加载中…</p>
        ) : assignments.length === 0 ? (
          <div>
            <p style={{ margin: "0 0 0.5rem" }}>暂无评审任务</p>
            <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: 13 }}>
              请等待经办人在「征求意见」阶段将您指定为评审人。您也可以在
              <Link to="/policies"> 制度库 </Link>
              浏览制度概况。
            </p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>制度</th>
                <th>目标版本</th>
                <th>流程状态</th>
                <th>评审状态</th>
                <th>我的意见数</th>
                <th>修订说明</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {assignments.map((item) => (
                <tr key={item.assignment_id}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{item.policy_title}</div>
                    <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                      {item.policy_code}
                    </div>
                  </td>
                  <td>{item.target_version_label || "—"}</td>
                  <td>
                    <StateBadge state={item.revision_state} />
                  </td>
                  <td>
                    <span className={FEEDBACK_CLASS[item.feedback_status]}>
                      {FEEDBACK_LABEL[item.feedback_status]}
                    </span>
                    {item.is_mandatory && (
                      <span style={{ marginLeft: 6, fontSize: 11, color: "var(--color-text-muted)" }}>
                        必反馈
                      </span>
                    )}
                  </td>
                  <td>{item.my_comment_count}</td>
                  <td style={{ maxWidth: 240 }}>
                    {item.change_brief.length > 72
                      ? `${item.change_brief.slice(0, 72)}…`
                      : item.change_brief || "—"}
                  </td>
                  <td>
                    {item.revision_state === "in_consultation" ? (
                      <Link
                        to={`/revisions/${item.revision_id}/consultation`}
                        className="btn btn-primary"
                        style={{ fontSize: 13 }}
                      >
                        开始评审
                      </Link>
                    ) : (
                      <Link
                        to={`/policies/${item.policy_id}`}
                        className="btn btn-secondary"
                        style={{ fontSize: 13 }}
                      >
                        查看制度
                      </Link>
                    )}
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
