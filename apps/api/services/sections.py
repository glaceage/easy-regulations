import re
import uuid

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+\{#([a-zA-Z0-9_-]+)\})?\s*$", re.MULTILINE)


def build_section_tree(markdown: str) -> list[dict]:
    tree: list[dict] = []
    for match in HEADING_RE.finditer(markdown):
        level = len(match.group(1))
        title = match.group(2).strip()
        section_id = match.group(3) or _slugify(title)
        tree.append({"section_id": section_id, "level": level, "title": title})
    return tree


def ensure_section_ids(markdown: str) -> tuple[str, list[dict]]:
    seen: set[str] = set()

    def repl(match: re.Match[str]) -> str:
        hashes = match.group(1)
        title = match.group(2).strip()
        existing = match.group(3)
        section_id = existing or _unique_slug(title, seen)
        return f"{hashes} {title} {{#{section_id}}}"

    updated = HEADING_RE.sub(repl, markdown)
    return updated, build_section_tree(updated)


def _slugify(title: str) -> str:
    base = re.sub(r"\s+", "-", title.lower())
    base = re.sub(r"[^a-z0-9\u4e00-\u9fff-]", "", base)
    return f"sec-{base[:32] or uuid.uuid4().hex[:8]}"


def _unique_slug(title: str, seen: set[str]) -> str:
    candidate = _slugify(title)
    if candidate not in seen:
        seen.add(candidate)
        return candidate
    suffix = uuid.uuid4().hex[:6]
    unique = f"{candidate}-{suffix}"
    seen.add(unique)
    return unique


def extract_section_body(markdown: str, section_id: str) -> str:
    pattern = re.compile(rf"^#{{1,6}}\s+.+?\{{#{re.escape(section_id)}\}}\s*$", re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    start = match.end()
    next_heading = re.search(r"^#{1,6}\s+", markdown[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(markdown)
    return markdown[start:end].strip()
