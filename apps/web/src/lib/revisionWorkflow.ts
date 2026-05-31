import type { RevisionState } from "../api/types";

export type WorkflowPhase =
  | "drafting"
  | "consultation"
  | "revision"
  | "pending_publish"
  | "published"
  | "cancelled";

const PHASE_BY_STATE: Record<RevisionState, WorkflowPhase> = {
  draft: "drafting",
  in_consultation: "consultation",
  in_revision: "revision",
  pending_publish: "pending_publish",
  published: "published",
  cancelled: "cancelled",
};

const PHASE_HINT: Record<WorkflowPhase, string> = {
  drafting:
    "起草阶段：在本页编辑正文、生成 AI 初稿。保存后点击「提交征求意见」进入多部门评审；届时在征求意见页指定评审人。",
  consultation:
    "征求意见阶段：评审人针对章节提交意见。经办人暂不可改稿，可结束本阶段后进入改稿。",
  revision:
    "改稿阶段：根据已收集意见修改正文，处理 AI 建议。开放意见已全部关闭后可提交发布审核。",
  pending_publish: "待发布阶段：请前往发布审核页面，由制度管理员复核并发布。",
  published: "修订已发布，可在制度详情查看当前版本。",
  cancelled: "修订已取消，仅可查看历史记录。",
};

export function getWorkflowPhase(state: RevisionState): WorkflowPhase {
  return PHASE_BY_STATE[state];
}

export function getPhaseHint(state: RevisionState): string {
  return PHASE_HINT[PHASE_BY_STATE[state]];
}

export function canEditDraft(state: RevisionState): boolean {
  return state === "draft" || state === "in_revision";
}

export function canGenerateAiDraft(state: RevisionState): boolean {
  return state === "draft";
}

export function getRevisionPrimaryRoute(revisionId: string, state: RevisionState): string {
  switch (state) {
    case "in_consultation":
      return `/revisions/${revisionId}/consultation`;
    case "pending_publish":
      return `/revisions/${revisionId}/publish`;
    case "published":
    case "cancelled":
      return `/revisions/${revisionId}/view`;
    default:
      return `/revisions/${revisionId}`;
  }
}

export type TransitionAction = {
  target: RevisionState;
  label: string;
  variant?: "primary" | "secondary";
};

export function getOwnerTransitions(state: RevisionState): TransitionAction[] {
  switch (state) {
    case "draft":
      return [{ target: "in_consultation", label: "提交征求意见", variant: "primary" }];
    case "in_consultation":
      return [
        { target: "in_revision", label: "结束征求意见，进入改稿", variant: "primary" },
        { target: "cancelled", label: "取消修订", variant: "secondary" },
      ];
    case "in_revision":
      return [
        { target: "in_consultation", label: "重新开放征求意见", variant: "secondary" },
        { target: "pending_publish", label: "提交发布审核", variant: "primary" },
        { target: "cancelled", label: "取消修订", variant: "secondary" },
      ];
    default:
      return [];
  }
}

export function getPostTransitionMessage(
  targetState: RevisionState,
  revisionId: string,
): { message: string; link?: { to: string; label: string } } {
  switch (targetState) {
    case "in_consultation":
      return {
        message: "已提交征求意见。",
        link: {
          to: `/revisions/${revisionId}/consultation`,
          label: "打开征求意见页面",
        },
      };
    case "in_revision":
      return { message: "已结束征求意见，进入改稿阶段。请处理下方意见并保存正文。" };
    case "pending_publish":
      return {
        message: "已提交发布审核。",
        link: {
          to: `/revisions/${revisionId}/publish`,
          label: "前往发布审核页面",
        },
      };
    case "cancelled":
      return { message: "修订已取消。" };
    default:
      return { message: "流程状态已更新。" };
  }
}
