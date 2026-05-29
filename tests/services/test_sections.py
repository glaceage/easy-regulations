from apps.api.services.sections import build_section_tree, ensure_section_ids, extract_section_body

SAMPLE = """---
title: 测试制度
version: 1.0
---

# 总则 {#sec-1}

## 1.1 目的 {#sec-1-1}

为规范考勤。
"""


def test_build_section_tree_finds_headings():
    tree = build_section_tree(SAMPLE)
    ids = {node["section_id"] for node in tree}
    assert ids == {"sec-1", "sec-1-1"}


def test_ensure_section_ids_adds_missing_ids():
    md = "## 新章节\n\n内容"
    updated, tree = ensure_section_ids(md)
    assert "{#" in updated
    assert len(tree) >= 1


def test_extract_section_body():
    body = extract_section_body(SAMPLE, "sec-1-1")
    assert "为规范考勤" in body
