from html import escape
import re


def heading_id(text: str, used_heading_ids: set[str]) -> str:
    """heading text를 문서 안에서 유일한 anchor id로 변환합니다."""
    normalized = re.sub(r"[^0-9A-Za-z가-힣]+", "-", text.lower()).strip("-")
    anchor_id = normalized or "section"
    if anchor_id not in used_heading_ids:
        used_heading_ids.add(anchor_id)
        return anchor_id

    suffix = 2
    while f"{anchor_id}-{suffix}" in used_heading_ids:
        suffix += 1
    unique_anchor_id = f"{anchor_id}-{suffix}"
    used_heading_ids.add(unique_anchor_id)
    return unique_anchor_id


def render_toc(items: list[tuple[int, str, str]]) -> str:
    """문서 heading 목록을 anchor 기반 목차로 렌더링합니다."""
    if not items:
        return ""
    links = "".join(
        f'<li class="level-{level}"><a href="#{anchor_id}">{render_inline(title)}</a></li>'
        for level, anchor_id, title in items
    )
    return f'<nav class="toc" aria-label="문서 목차"><strong>목차</strong><ol>{links}</ol></nav>'


def render_doc_toolbar() -> str:
    """문서 섹션을 한 번에 펼치거나 접는 버튼을 렌더링합니다."""
    return (
        '<div class="doc-toolbar">'
        '<button type="button" onclick="setDocSections(true)">모두 펼치기</button>'
        '<button type="button" onclick="setDocSections(false)">모두 접기</button>'
        "</div>"
    )


def render_inline(text: str) -> str:
    """inline code를 보존하면서 Markdown inline text를 HTML로 escape합니다."""
    parts = text.split("`")
    rendered: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 1:
            rendered.append(f"<code>{escape(part)}</code>")
        else:
            rendered.append(escape(part))
    return "".join(rendered)
