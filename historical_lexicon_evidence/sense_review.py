from __future__ import annotations

from .contract import Row, apply_rows, index_rows, read_rows, text


def transform(row: Row) -> Row:
    """分开当前版标注和须重审的旧版引文，并报告当前义项冲突。"""
    version = text(row, "definition_version")
    result = {}
    for citation, quote in index_rows(read_rows(row, "citations"), "citation").items():
        assigned = {}
        stale = set()
        for mark in read_rows(quote, "votes"):
            editor = text(mark, "editor")
            if text(mark, "version") == version:
                if editor in assigned:
                    raise ValueError("duplicate current editor vote")
                assigned[editor] = text(mark, "sense")
            else:
                stale.add(editor)
        senses = sorted(set(assigned.values()))
        status = "disputed" if len(senses) > 1 else "agreed" if len(assigned) >= 2 else "pending"
        result[citation] = dict(status=status, votes=assigned, needs_recheck=sorted(stale - assigned.keys()))
    return {"citations": result}


def build_facts(data: Row) -> list[Row]:
    return apply_rows(data, transform)
