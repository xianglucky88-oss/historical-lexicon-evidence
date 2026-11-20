from __future__ import annotations

from .contract import Row, apply_rows, choice, index_rows, integer, read_rows, text
from .fragment_lineage import declared_fragments, fragment_ref, resolve_fragments
from .sense_review import evaluate_votes


KINDS = ("written", "published", "edition")


def _date_record(value: Row) -> Row:
    kind = choice(value, "kind", set(KINDS))
    lower = integer(value, "year_min")
    applies = value.get("applies_to")
    return {
        "kind": kind,
        "range": [lower, integer(value, "year_max", minimum=lower)],
        "applies_to": text(value, "applies_to") if applies is not None else None,
    }


def _records(owner: Row) -> list[Row]:
    return [_date_record(value) for value in read_rows(owner, "dates")] if "dates" in owner else []


def _plain_case(quote: Row) -> tuple[Row, list[int] | None]:
    """Citation-level dates keep the original behaviour: written, then published."""
    evidence = {}
    for record in _records(quote):
        if record["applies_to"] is not None:
            raise ValueError("citation-level dates cannot name particular wording")
        if record["kind"] in evidence:
            raise ValueError(f"duplicate date kind: {record['kind']}")
        evidence[record["kind"]] = record["range"]
    adopted = next((kind for kind in ("written", "published") if kind in evidence), None)
    detail = {"adopted": adopted, "evidence": evidence}
    return detail, evidence[adopted] if adopted is not None else None


def _names(applies: str, reference: str, origin: str) -> bool:
    """Whether an ``applies_to`` value names this wording.

    Only the fragment's own reference or the reference of the fragment that
    first carries the wording count; a bare fragment name could match an
    unrelated quotation and is therefore rejected.
    """
    return applies in {reference, origin}


def _evidence(fragment: Row, reference: str,
              origin: str) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """Split a fragment's own dates into applicable evidence and foreign evidence.

    ``applies_to`` is the only way a date can claim a particular wording; a
    date naming other wording is reported as excluded and never adopted, and
    nothing is attributed by similarity or adjacency.
    """
    evidence: dict[str, list[int]] = {}
    foreign: dict[str, list[int]] = {}
    for record in _records(fragment):
        applies = record["applies_to"]
        target = foreign if applies is not None and not _names(applies, reference, origin) \
            else evidence
        if record["kind"] in target:
            raise ValueError(f"duplicate {record['kind']} date evidence for {reference}")
        target[record["kind"]] = record["range"]
    return evidence, foreign


def _review_status(marks: list[Row], version: str, sense: str) -> str | None:
    """Return the pending reason, or ``None`` when the current review accepts it.

    A current-version conclusion naming the queried sense is usable even when
    only one editor has filed it.  The fragment stays pending when no current
    conclusion exists (only older-version votes, ``stale_review``), when the
    current conclusions name only another sense — the old-sense review the
    split left behind, ``old_sense`` — or when they conflict and the sense is
    not settled (``review_unresolved``).  None of these dates the new sense.
    """
    if not marks:
        return "review_unresolved"
    result = evaluate_votes(marks, version)
    if not result["votes"]:
        return "stale_review" if result["needs_recheck"] else "review_unresolved"
    concluded = set(result["votes"].values())
    if sense not in concluded:
        return "old_sense"
    if concluded != {sense}:
        return "review_unresolved"
    return None


def _merge_marks(groups: list[list[Row]]) -> list[Row]:
    """Merge the votes of every witness of one wording, keeping one vote per editor.

    Editors are identified by ``editor`` and ``version``.  A witness may repeat
    another witness's conclusion and that copy is dropped; two different
    conclusions in the same witness, or a conflicting conclusion across
    witnesses, is rejected rather than silently resolved.
    """
    merged: dict[tuple[str, str], str] = {}
    for marks in groups:
        seen: set[tuple[str, str]] = set()
        for mark in marks:
            key = (text(mark, "editor"), text(mark, "version"))
            value = text(mark, "sense")
            if key in seen:
                raise ValueError(f"duplicate editor vote: {key[0]}")
            seen.add(key)
            if merged.setdefault(key, value) != value:
                raise ValueError(f"conflicting vote across witnesses: {key[0]}")
    return [{"editor": editor, "version": version, "sense": sense}
            for (editor, version), sense in sorted(merged.items())]


def _fragment_detail(citation: str, fragment: Row, resolved: Row, marks: list[Row],
                     version: str, sense: str) -> Row:
    reference = fragment_ref(citation, text(fragment, "fragment"))
    evidence, foreign = _evidence(fragment, reference, resolved["origin"] or reference)
    detail = {
        "status": "pending",
        "reason": None,
        "path": resolved["path"],
        "origin": resolved["origin"],
        "starting_edition": resolved["starting_edition"],
        "adopted": None,
        "evidence": evidence,
    }
    if foreign:
        # Dates that name other wording are shown but never used here.
        detail["excluded_evidence"] = foreign
    if resolved["status"] != "confirmed":
        # The copying chain stops before an evidenced starting edition.
        detail["reason"] = resolved["reason"]
        return detail
    if reference != resolved["origin"]:
        # A select edition re-quotes wording first carried elsewhere.  Its path
        # stays verifiable and it maps to the shared case, but it contributes
        # no case of its own and its reprint date never dates the wording.
        detail["status"] = "duplicate"
        detail["reason"] = "shared_case"
        return detail
    reason = _review_status(marks, version, sense)
    if reason is not None:
        detail["reason"] = reason
        return detail
    adopted = next((kind for kind in ("written", "published") if kind in evidence), None)
    if adopted is not None:
        detail["adopted"] = adopted
        detail["status"] = "dated"
        detail["range"] = evidence[adopted]
        return detail
    if {"written", "published"} & set(foreign):
        # Dated evidence exists, but it belongs to different wording.
        detail["reason"] = "date_mismatch"
        return detail
    detail["status"] = "undated"
    detail["reason"] = "edition_only" if "edition" in evidence else "no_dates"
    return detail


def transform(row: Row) -> Row:
    """以署写证据优先、首刊次之形成可用日期区间，印本日期单列。

    Wording fragments are dated from their own audited evidence only.  A
    fragment stays pending when its review concludes the old sense, when its
    copying chain does not reach an evidenced starting edition, or when the
    date evidence does not apply to that wording.  A reprint edition is
    reported next to the writing and first-publication evidence but is never
    adopted.  Anthologies that re-quote one source fragment share a single
    independent case; every witness path stays visible, and no reprint date
    dates the source wording.
    """
    citations = index_rows(read_rows(row, "citations"), "citation")
    fragments = {citation: declared_fragments(quote) for citation, quote in citations.items()}
    split = any(fragments.values())
    if split:
        missing = sorted(citation for citation, items in fragments.items() if not items)
        if missing:
            raise ValueError(f"every citation must declare fragments when any does: {', '.join(missing)}")
        for citation, quote in citations.items():
            if "votes" in quote:
                raise ValueError(f"votes must be attached to fragments: {citation}")
            if "dates" in quote:
                raise ValueError(f"date evidence must be attached to fragments: {citation}")
        for field in ("definition_version", "sense"):
            if field not in row:
                raise ValueError(f"{field} is required when citations are split into fragments")
        version = text(row, "definition_version")
        sense = text(row, "sense")
    else:
        version = sense = ""
    resolved = resolve_fragments(citations)

    # Editors reviewing a re-quoted wording may have attached their conclusion
    # to any witness of it.  Gather every witness's votes per case so a review
    # filed on an anthology still speaks for the shared case.
    groups: dict[str, list[list[Row]]] = {}
    for citation, quote in citations.items():
        for fragment in fragments[citation]:
            reference = fragment_ref(citation, text(fragment, "fragment"))
            origin = resolved[reference]["origin"]
            if origin is not None:
                groups.setdefault(origin, []).append(
                    read_rows(fragment, "votes") if "votes" in fragment else []
                )

    cases: dict[str, list[int]] = {}
    citations_out = {}
    pending = []
    undated = []
    for citation, quote in citations.items():
        if not fragments[citation]:
            detail, range_ = _plain_case(quote)
            citations_out[citation] = detail
            if range_ is not None:
                cases[citation] = range_
            continue
        fragment_out = {}
        for fragment in fragments[citation]:
            name = text(fragment, "fragment")
            reference = fragment_ref(citation, name)
            origin = resolved[reference]["origin"]
            marks = _merge_marks(groups[origin]) if origin is not None else []
            result = _fragment_detail(citation, fragment, resolved[reference], marks,
                                      version, sense)
            fragment_out[name] = result
            if result["status"] == "dated":
                cases[reference] = result["range"]
            elif result["status"] == "pending":
                # Held for verification: an old-sense conclusion, an unusable
                # review, a broken copying chain, or dates that name other
                # wording.  None of these is merged into the earliest date.
                pending.append({"fragment": reference, "reason": result["reason"]})
            elif result["status"] == "undated":
                # Only a reprint edition, or no date evidence at all.  The
                # edition imprint is reported but never substitutes for
                # written or first-publication evidence.
                undated.append({"fragment": reference, "reason": result["reason"]})
        citations_out[citation] = {"fragments": fragment_out}

    if cases:
        bound = min(upper for _, upper in cases.values())
        earliest = [min(lower for lower, _ in cases.values()), bound]
        # A case whose lower bound merely touches the bound is still earliest.
        candidates = sorted(case for case, (lower, _) in cases.items() if lower <= bound)
    else:
        earliest = None
        candidates = []
    output = {"citations": citations_out, "earliest_range": earliest,
              "earliest_candidates": candidates}
    if split:
        output["pending"] = sorted(pending, key=lambda item: (item["fragment"], item["reason"]))
        if undated:
            output["undated"] = sorted(undated, key=lambda item: (item["fragment"], item["reason"]))
    return output


def build_facts(data: Row) -> list[Row]:
    return apply_rows(data, transform)
