import type { RevisionState } from "../api/types";

type Step = {
  key: RevisionState;
  label: string;
};

const STEPS: Step[] = [
  { key: "draft", label: "起草" },
  { key: "in_consultation", label: "征求意见" },
  { key: "in_revision", label: "改稿" },
  { key: "pending_publish", label: "待发布" },
  { key: "published", label: "已发布" },
];

const ORDER: Record<RevisionState, number> = {
  draft: 0,
  in_consultation: 1,
  in_revision: 2,
  pending_publish: 3,
  published: 4,
  cancelled: -1,
};

export function WorkflowStepper({ state }: { state: RevisionState }) {
  if (state === "cancelled") {
    return (
      <div className="workflow-stepper workflow-stepper--cancelled">
        <span className="workflow-step workflow-step--cancelled">已取消</span>
      </div>
    );
  }

  const current = ORDER[state];

  return (
    <ol className="workflow-stepper">
      {STEPS.map((step, idx) => {
        const status =
          idx < current ? "done" : idx === current ? "active" : "upcoming";
        return (
          <li key={step.key} className={`workflow-step workflow-step--${status}`}>
            <span className="workflow-step__index">{idx + 1}</span>
            <span className="workflow-step__label">{step.label}</span>
          </li>
        );
      })}
    </ol>
  );
}
