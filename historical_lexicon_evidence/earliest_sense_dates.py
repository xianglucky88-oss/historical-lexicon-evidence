from __future__ import annotations

from .contract import Row, apply_rows, choice, index_rows, integer, read_rows


def transform(row: Row) -> Row:
    """以署写证据优先、首刊次之形成可用日期区间，印本日期单列。"""
    by_quote = {}
    dated = []
    for citation, quote in index_rows(read_rows(row, "citations"), "citation").items():
        dates = index_rows(read_rows(quote, "dates"), "kind")
        checked = {}
        for kind, value in dates.items():
            choice(value, "kind", {"written", "published", "edition"})
            lower = integer(value, "year_min")
            checked[kind] = [lower, integer(value, "year_max", minimum=lower)]
        selected = next((kind for kind in ("written", "published") if kind in checked), None)
        by_quote[citation] = dict(adopted=selected, evidence=checked)
        if selected is not None:
            dated.append((citation, checked[selected]))
    bound = min((date[1] for _, date in dated), default=None)
    return {"citations": by_quote, "earliest_range": [min(date[0] for _, date in dated), bound] if dated else None,
            "earliest_candidates": sorted(key for key, date in dated if date[0] <= bound)}


def build_facts(data: Row) -> list[Row]:
    return apply_rows(data, transform)
