"""Locks the finding in docs/ARCHITECTURE.md §9.1 against future regression.

Why this test exists, since it will look strange to someone reading it cold:

The `english` text-search configuration discards `NOT` as a stopword. A search for the
operational state "PNL NOT PROCESSED" therefore also matches a page stating that PNL
*is* processed — the system retrieves evidence asserting the opposite of the question
and answers from it, with a real citation to a real page.

No downstream layer can catch this. The evidence is genuine, the quote verifies, the
page number is correct. Only the index configuration prevents it.

If someone later switches the index to `english` for better prose recall, this fails.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.session import get_engine

pytestmark = pytest.mark.integration

NEGATIVE = "PNL status is NOT PROCESSED"
POSITIVE = "PNL status is PROCESSED"


def _matches(conn, config: str, document: str, query: str) -> bool:
    row = conn.execute(
        text("SELECT to_tsvector(:c, :d) @@ phraseto_tsquery(:c, :q)"),
        {"c": config, "d": document, "q": query},
    ).scalar_one()
    return bool(row)


def test_simple_config_separates_negated_and_affirmed_states() -> None:
    with get_engine().connect() as conn:
        assert _matches(conn, "simple", NEGATIVE, "NOT PROCESSED")
        assert not _matches(conn, "simple", POSITIVE, "NOT PROCESSED"), (
            "The `simple` configuration must distinguish NOT PROCESSED from PROCESSED. "
            "If this fails, exact-state retrieval is broken."
        )


def test_english_config_is_unsafe_here() -> None:
    """Documents the defect itself, so the reason for `simple` cannot be lost.

    This asserts that `english` IS broken. If PostgreSQL ever changes its stopword
    handling and this starts failing, that is good news — and someone should revisit
    §9.1 rather than delete this test.
    """
    with get_engine().connect() as conn:
        assert _matches(conn, "english", POSITIVE, "NOT PROCESSED"), (
            "Expected `english` to wrongly match the affirmed state. If it no longer "
            "does, re-evaluate the decision recorded in docs/ARCHITECTURE.md §9.1."
        )


@pytest.mark.parametrize(
    "damaged",
    ["PNL NOT PROCESSEO", "PN1 NOT PROCESSED", "PNL N0T PROCESSED"],
)
def test_trigram_rescues_ocr_damage_that_exact_matching_loses(damaged: str) -> None:
    """Justifies retrieval leg 3 (§9.1): OCR corrupts exactly the strings that matter."""
    with get_engine().connect() as conn:
        assert not _matches(conn, "simple", damaged, "PNL NOT PROCESSED")
        similarity = conn.execute(
            text("SELECT similarity(:d, 'PNL NOT PROCESSED')"), {"d": damaged}
        ).scalar_one()
        assert similarity > 0.6, f"trigram similarity {similarity} too low to rescue {damaged!r}"


def test_hyphenated_codes_require_phrase_queries_not_bag_of_words() -> None:
    """Error codes fragment into tokens; adjacency is what makes them match correctly.

    `phraseto_tsquery` fragments the query the same way and preserves adjacency, so
    E-1052 matches E-1052 and not E-1053. `plainto_tsquery` drops adjacency and is
    therefore unsafe for identifiers. Leg 2 must always build phrase queries.
    """
    with get_engine().connect() as conn:
        assert _matches(conn, "simple", "error E-1052 raised", "E-1052")
        assert not _matches(conn, "simple", "error E-1053 raised", "E-1052")

        tokens = conn.execute(text("SELECT to_tsvector('simple','error E-1052')")).scalar_one()
        assert "-1052" in tokens and "'e'" in tokens, (
            "Documents the fragmentation that makes phrase queries necessary."
        )
