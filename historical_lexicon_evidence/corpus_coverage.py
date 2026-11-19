from __future__ import annotations

from .contract import Row, apply_rows, integer, read_rows, text


def transform(row: Row) -> Row:
    """按同类来源比较标准化历时用例率，并标记样本量不足的分组。"""
    minimum = integer(row, "min_tokens", minimum=1)
    groups = {}
    for item in read_rows(row, "coverage"):
        era, genre = text(item, "era"), text(item, "genre")
        key = era, genre
        if key in groups:
            raise ValueError("duplicate genre coverage for era")
        tokens, uses = integer(item, "tokens"), integer(item, "uses")
        if uses > tokens:
            raise ValueError("uses exceed tokens")
        groups[key] = dict(era=era, genre=genre, tokens=tokens, uses=uses,
                           per_million=uses * 1000000 / tokens if tokens >= minimum else None)
    return {"coverage": [groups[k] for k in sorted(groups)]}


def build_facts(data: Row) -> list[Row]:
    return apply_rows(data, transform)
