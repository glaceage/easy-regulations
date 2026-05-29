import type { RevisionState } from "../api/types";

const STATE_LABELS: Record<RevisionState, string> = {
  draft: "草稿",
  in_consultation: "征求意见",
  in_revision: "修订中",
  pending_publish: "待发布",
  published: "已发布",
  cancelled: "已取消",
};

const STATE_CLASS: Record<RevisionState, string> = {
  draft: "badge-draft",
  in_consultation: "badge-consult",
  in_revision: "badge-revise",
  pending_publish: "badge-pending",
  published: "badge-published",
  cancelled: "badge-cancelled",
};

interface Props {
  state: RevisionState;
}

export function StateBadge({ state }: Props) {
  return (
    <span className={`state-badge ${STATE_CLASS[state]}`}>
      {STATE_LABELS[state] ?? state}
    </span>
  );
}
