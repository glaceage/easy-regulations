import { useMemo } from "react";
import { buildSectionTree, getSectionTitle } from "../lib/sections";

export function SectionLabel({
  sectionId,
  markdown,
}: {
  sectionId: string;
  markdown?: string;
}) {
  const title = useMemo(() => {
    if (!markdown) {
      return sectionId;
    }
    return getSectionTitle(sectionId, buildSectionTree(markdown));
  }, [sectionId, markdown]);

  return <span title={sectionId !== title ? sectionId : undefined}>{title}</span>;
}
