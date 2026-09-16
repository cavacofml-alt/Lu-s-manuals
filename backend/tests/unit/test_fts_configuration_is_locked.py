"""The `english` text-search configuration must not appear in application code.

`.github/copilot-instructions.md` tells assistants and contributors to use `simple`.
That is guidance, and guidance is the weakest of the four enforcement categories in
docs/ARCHITECTURE.md §8.1.5 — a model or a person can ignore it, and switching to
`english` is the single most plausible "improvement" anyone could make here, because it
genuinely does improve recall on ordinary prose.

What it also does is make a page stating "PNL status is PROCESSED" match a search for
"NOT PROCESSED", so the system answers from evidence asserting the opposite of the
question, with a correct-looking citation to a real page. Verified on PostgreSQL 16.13.

tests/integration/test_fulltext_semantics.py proves the defect exists in PostgreSQL.
This test prevents it entering our SQL, which is the part guidance alone cannot do.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
SEARCHED = (BACKEND / "app", BACKEND / "worker", BACKEND / "migrations")

# to_tsvector('english', …), to_tsquery("english", …), phraseto_tsquery('english', …), …
FORBIDDEN = re.compile(r"""ts(vector|query)\s*\(\s*['"]english['"]""", re.IGNORECASE)

# Also catch a default-configuration index, where the config is implicit and comes from
# default_text_search_config — which is `english` on most installations.
IMPLICIT_CONFIG = re.compile(r"""to_tsvector\s*\(\s*[a-z_.]+\s*\)""", re.IGNORECASE)


def _sources() -> list[Path]:
    return [p for root in SEARCHED if root.exists() for p in root.rglob("*.py")]


def test_english_text_search_configuration_is_never_used() -> None:
    offenders: list[str] = []
    for path in _sources():
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(BACKEND)}:{lineno}: {line.strip()}")

    assert not offenders, (
        "The `english` text-search configuration was used:\n  "
        + "\n  ".join(offenders)
        + "\n\nIt discards NOT as a stopword, so a page asserting the affirmative state "
        "matches a search for the negative one. Use 'simple'. See ARCHITECTURE.md §9.1."
    )


def test_text_search_configuration_is_always_explicit() -> None:
    """A one-argument to_tsvector() inherits default_text_search_config — usually english.

    The implicit form is worse than the explicit mistake, because nothing in the code
    says which configuration is in use and it varies by installation.
    """
    offenders: list[str] = []
    for path in _sources():
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if IMPLICIT_CONFIG.search(line) and "simple" not in line:
                offenders.append(f"{path.relative_to(BACKEND)}:{lineno}: {line.strip()}")

    assert not offenders, (
        "to_tsvector() called without an explicit configuration:\n  "
        + "\n  ".join(offenders)
        + "\n\nAlways pass 'simple' explicitly; the default is server-dependent."
    )
