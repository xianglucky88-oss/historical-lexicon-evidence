from __future__ import annotations

from .contract import Row, apply_rows, index_rows, read_rows, text


def transform(row: Row) -> Row:
    """沿明确的转载关系保留每条引文的路径，只统计可追到的独立原始用例。"""
    items = index_rows(read_rows(row, "citations"), "citation")
    paths = {}
    original = set()
    for citation in items:
        path = [citation]
        current = citation
        seen = {citation}
        while current in items and items[current]["reprinted_from"] is not None:
            current = text(items[current], "reprinted_from")
            if current in seen:
                raise ValueError("cyclic reprint provenance")
            seen.add(current)
            path.append(current)
        source = current if current in items else None
        if source is not None:
            original.add(source)
        paths[citation] = dict(path=path, origin=source)
    return {"citations": paths, "independent_origins": sorted(original)}


def build_facts(data: Row) -> list[Row]:
    return apply_rows(data, transform)
