export type SectionNode = {
  section_id: string;
  level: number;
  title: string;
};

export const GENERAL_SECTION_ID = "general";
export const GENERAL_SECTION_TITLE = "全文 / 综合意见";

const HEADING_RE = /^(#{1,6})\s+(.+?)(?:\s+\{#([a-zA-Z0-9_-]+)\})?\s*$/gm;

function slugify(title: string): string {
  const base = title
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9\u4e00-\u9fff-]/g, "");
  return `sec-${base.slice(0, 32) || "untitled"}`;
}

/** Parse Markdown headings into a section tree (mirrors backend build_section_tree). */
export function buildSectionTree(markdown: string): SectionNode[] {
  const tree: SectionNode[] = [];
  HEADING_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = HEADING_RE.exec(markdown)) !== null) {
    const level = match[1].length;
    const title = match[2].trim();
    const section_id = match[3] || slugify(title);
    tree.push({ section_id, level, title });
  }
  return tree;
}

export function getSectionTitle(sectionId: string, sections: SectionNode[]): string {
  if (sectionId === GENERAL_SECTION_ID) {
    return GENERAL_SECTION_TITLE;
  }
  const found = sections.find((s) => s.section_id === sectionId);
  return found?.title ?? sectionId;
}

export function formatSectionOption(section: SectionNode): string {
  const pad = section.level > 1 ? `${"　".repeat(section.level - 1)}└ ` : "";
  return `${pad}${section.title}`;
}

export function sectionOptions(sections: SectionNode[]): { value: string; label: string }[] {
  const items = sections.map((s) => ({
    value: s.section_id,
    label: formatSectionOption(s),
  }));
  return [{ value: GENERAL_SECTION_ID, label: GENERAL_SECTION_TITLE }, ...items];
}
