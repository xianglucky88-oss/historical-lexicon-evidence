from __future__ import annotations

from .contract import Row, apply_rows, index_rows, read_rows, text
from .fragment_lineage import declared_fragments


def evaluate_votes(marks: list[Row], version: str) -> Row:
    """Reduce editor votes to the conclusions for the current definition version.

    Votes cast against an older version are kept as ``needs_recheck`` instead of
    being counted, so a stale conclusion never steers a current decision.
    """
    assigned = {}
    stale = set()
    for mark in marks:
        editor = text(mark, "editor")
        if text(mark, "version") == version:
            if editor in assigned:
                raise ValueError("duplicate current editor vote")
            assigned[editor] = text(mark, "sense")
        else:
            stale.add(editor)
    senses = sorted(set(assigned.values()))
    status = "disputed" if len(senses) > 1 else "agreed" if len(assigned) >= 2 else "pending"
    return {"status": status, "votes": assigned, "needs_recheck": sorted(stale - assigned.keys())}


def transform(row: Row) -> Row:
    """分开当前版标注和须重审的旧版引文，并报告当前义项冲突。

    A citation may be split into audited wording fragments; the review is then
    reported per fragment, because a split sense can rest on wording that only
    one edition contains.
    """
    version = text(row, "definition_version")
    result = {}
    for citation, quote in index_rows(read_rows(row, "citations"), "citation").items():
        fragments = declared_fragments(quote)
        if fragments:
            if "votes" in quote:
                raise ValueError(f"votes must be attached to fragments: {citation}")
            detail = {}
            for fragment in fragments:
                name = text(fragment, "fragment")
                if name in detail:
                    raise ValueError(f"duplicate fragment: {name}")
                marks = read_rows(fragment, "votes") if "votes" in fragment else []
                detail[name] = evaluate_votes(marks, version)
            result[citation] = {"fragments": detail}
        else:
            result[citation] = evaluate_votes(read_rows(quote, "votes"), version)
    return {"citations": result}


def build_facts(data: Row) -> list[Row]:
    return apply_rows(data, transform)
