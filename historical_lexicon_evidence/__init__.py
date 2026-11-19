"""历史词典引文证据"""

from . import citation_lineage, dated_word_forms, earliest_sense_dates, sense_review, corpus_coverage
from .contract import Row

PIPELINES = {
    "citation-lineage": citation_lineage.build_facts,
    "dated-word-forms": dated_word_forms.build_facts,
    "earliest-sense-dates": earliest_sense_dates.build_facts,
    "sense-review": sense_review.build_facts,
    "corpus-coverage": corpus_coverage.build_facts,
}

def process(pipeline: str, data: Row) -> list[Row]:
    """Validate and transform an independent input dataset into keyed facts."""
    if pipeline not in PIPELINES:
        raise ValueError(f"unknown pipeline: {pipeline}")
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    return PIPELINES[pipeline](data)
