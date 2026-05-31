import type { SectionNode } from "../lib/sections";
import { formatSectionOption } from "../lib/sections";

export function SectionOutline({
  sections,
  selectedSectionId,
  onSelectSection,
  showCommentActions = false,
}: {
  sections: SectionNode[];
  selectedSectionId?: string;
  onSelectSection?: (sectionId: string) => void;
  showCommentActions?: boolean;
}) {
  if (sections.length === 0) {
    return (
      <p style={{ margin: 0, color: "var(--color-text-muted)", fontSize: 13 }}>
        正文中暂无章节标题。请经办人在起草阶段使用 Markdown 标题（如 <code># 第一章 总则</code>）划分结构。
      </p>
    );
  }

  return (
    <ul className="section-outline">
      {sections.map((section) => {
        const selected = selectedSectionId === section.section_id;
        return (
          <li
            key={section.section_id}
            className={`section-outline-item level-${section.level}${selected ? " selected" : ""}`}
          >
            <span className="section-outline-title">{formatSectionOption(section)}</span>
            {showCommentActions && onSelectSection && (
              <button
                type="button"
                className="btn btn-secondary section-outline-action"
                onClick={() => onSelectSection(section.section_id)}
              >
                对此节提意见
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
