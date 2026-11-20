"""Shared fragment-level provenance for citations.

A citation may be split into audited wording fragments.  Each fragment declares
its relation to earlier wording: ``verbatim`` (copied, with an explicit
``copied_from`` reference), ``new`` (first introduced in this citation's
edition), or ``unconfirmed``.  Only declared relations are followed; no
relation is ever inferred from textual similarity.

References have the form ``citation/fragment`` so a fragment can be followed
across witnesses and editions.
"""

from __future__ import annotations

from .contract import Row, choice, read_rows, text


RELATIONS = {"verbatim", "new", "unconfirmed"}


def fragment_ref(citation: str, fragment: str) -> str:
    """Return the canonical ``citation/fragment`` reference."""
    if "/" in citation or "/" in fragment:
        raise ValueError("citation and fragment ids must not contain '/'")
    return f"{citation}/{fragment}"


def split_ref(reference: str) -> tuple[str, str]:
    parts = reference.split("/")
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise ValueError(f"fragment reference must be citation/fragment: {reference!r}")
    return parts[0], parts[1]


def declared_fragments(citation: Row) -> list[Row]:
    """Read the audited fragments a citation declares, if any."""
    if "fragments" not in citation:
        return []
    fragments = read_rows(citation, "fragments")
    if not fragments:
        raise ValueError("fragments must not be empty when declared")
    return fragments


def relation(fragment: Row) -> str:
    """Validate and return a fragment's declared copying relation."""
    value = choice(fragment, "relation", RELATIONS)
    copied = fragment.get("copied_from")
    if value == "verbatim":
        if not isinstance(copied, str) or not copied.strip():
            raise ValueError("verbatim fragment requires copied_from")
        split_ref(copied)
    elif copied is not None:
        raise ValueError(f"{value} fragment must not have copied_from")
    return value


def fragment_records(citations: dict[str, Row]) -> dict[str, Row]:
    """Index every declared fragment by its ``citation/fragment`` reference."""
    records = {}
    for citation in citations:
        for fragment in declared_fragments(citations[citation]):
            reference = fragment_ref(citation, text(fragment, "fragment"))
            if reference in records:
                raise ValueError(f"duplicate fragment: {reference}")
            relation(fragment)
            records[reference] = fragment
    return records


def _resolved(path: list[str], origin: str | None, edition: str | None,
              status: str, reason: str | None) -> Row:
    return {
        "path": path,
        "origin": origin,
        "starting_edition": edition,
        "status": status,
        "reason": reason,
    }


def resolve_fragments(citations: dict[str, Row]) -> dict[str, Row]:
    """Trace every fragment back to its evidenced starting edition.

    The path stops at a fragment whose audited relation is ``new``; the
    citation holding that fragment supplies the starting edition.  A
    ``verbatim`` link to an undeclared fragment, an ``unconfirmed`` relation,
    or any other break in the chain stays ``pending`` instead of being guessed.
    Cycles are rejected.
    """
    records = fragment_records(citations)
    results = {}
    for reference in sorted(records):
        path = [reference]
        seen = {reference}
        current = reference
        while True:
            fragment = records.get(current)
            if fragment is None:
                results[reference] = _resolved(
                    path, None, None, "pending", "origin_unlocated"
                )
                break
            kind = relation(fragment)
            if kind == "new":
                origin_citation, _ = split_ref(current)
                if "edition" not in citations[origin_citation]:
                    raise ValueError(
                        f"starting edition missing for new fragment: {current}")
                results[reference] = _resolved(
                    path, current, text(citations[origin_citation], "edition"),
                    "confirmed", None
                )
                break
            if kind == "unconfirmed":
                results[reference] = _resolved(
                    path, None, None, "pending", "relation_unconfirmed"
                )
                break
            following = text(fragment, "copied_from")
            if following in seen:
                raise ValueError(f"cyclic reprint provenance: {following}")
            seen.add(following)
            path.append(following)
            current = following
    return results
