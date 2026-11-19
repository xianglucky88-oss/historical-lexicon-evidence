from __future__ import annotations

from .contract import Row, apply_rows, index_rows, integer, read_rows, span, text


def transform(row: Row) -> Row:
    """按有效年代、地域和词形应用已核对的映射，并保留多义候选。"""
    rules = [(text(rule, "form"), text(rule, "region"), *span(rule, "from_year", "until_year"), text(rule, "lemma")) for rule in read_rows(row, "mappings")]
    result = {}
    for citation, quote in index_rows(read_rows(row, "citations"), "citation").items():
        year = integer(quote, "year")
        form, region = text(quote, "form"), text(quote, "region")
        matches = sorted({lemma for f, r, start, end, lemma in rules if (form, region) == (f, r) and start <= year < end})
        result[citation] = dict(lemma=matches[0] if len(matches) == 1 else None, candidates=matches)
    return {"word_forms": result}


def build_facts(data: Row) -> list[Row]:
    return apply_rows(data, transform)
