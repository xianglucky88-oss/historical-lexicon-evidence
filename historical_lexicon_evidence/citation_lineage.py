from __future__ import annotations

from .contract import Row, apply_rows, index_rows, read_rows, text
from .fragment_lineage import declared_fragments, fragment_ref, resolve_fragments


def _citation_path(citation: str, items: dict[str, Row]) -> tuple[list[str], str | None]:
    path = [citation]
    current = citation
    seen = {citation}
    while current in items and items[current].get("reprinted_from") is not None:
        current = text(items[current], "reprinted_from")
        if current in seen:
            raise ValueError("cyclic reprint provenance")
        seen.add(current)
        path.append(current)
    return path, current if current in items else None


def transform(row: Row) -> Row:
    """沿明确的转载关系保留每条引文及其已审定片段的照录路径与起始版次，只统计可追到的独立原始用例。

    Fragment paths are traced separately, so one quotation can show its old
    wording and its added wording pointing at different editions.  A fragment
    that first carries a wording is the independent case; an anthology copying
    it keeps its own witness path but adds no case.  When a quotation's
    fragments resolve to different starting editions, its citation-level
    origin is left unresolved instead of naming one of them.
    """
    items = index_rows(read_rows(row, "citations"), "citation")
    declared = {citation: declared_fragments(item) for citation, item in items.items()}
    if any(declared.values()):
        missing = sorted(citation for citation, fragments in declared.items() if not fragments)
        if missing:
            raise ValueError(f"every citation must declare fragments when any does: {', '.join(missing)}")
    resolved = resolve_fragments(items)
    paths = {}
    independent = set()
    for citation, item in items.items():
        path, source = _citation_path(citation, items)
        fragments = declared[citation]
        if fragments:
            detail = {}
            editions = set()
            for fragment in fragments:
                name = text(fragment, "fragment")
                result = resolved[fragment_ref(citation, name)]
                detail[name] = result
                if result["status"] == "confirmed":
                    editions.add(result["origin"].split("/", 1)[0])
                    independent.add(result["origin"])
            entry = {"path": path,
                     "origin": next(iter(editions)) if len(editions) == 1 else None,
                     "fragments": detail}
        else:
            entry = {"path": path, "origin": source}
            if source is not None:
                independent.add(source)
        paths[citation] = entry
    return {"citations": paths, "independent_origins": sorted(independent)}


def build_facts(data: Row) -> list[Row]:
    return apply_rows(data, transform)
