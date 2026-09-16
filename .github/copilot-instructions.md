# Repository instructions

Documentation Intelligence AI — evidence-grounded retrieval over versioned internal
documentation. Full design: `docs/ARCHITECTURE.md`. Section markers below (§n) refer to it.

Most rules here exist because the obvious, plausible-looking code is wrong. Where a rule
seems arbitrary, the linked section says what went wrong.

## Non-negotiable invariants

### 1. Full-text search uses the `simple` configuration, never `english`

`to_tsvector('english', 'PNL NOT PROCESSED')` discards `NOT` as a stopword. A page stating
that PNL **is** processed then matches a search for `NOT PROCESSED`, and the system answers
from evidence asserting the opposite of the question — with a valid citation to a real page.
Verified on PostgreSQL 16.13. No downstream layer can detect it.

- Always `to_tsvector('simple', …)` and `phraseto_tsquery('simple', …)`.
- Never `plainto_tsquery` for technical identifiers: it drops adjacency, so `E-1052`
  matches a page where `e` and `-1052` appear far apart. Phrase queries only.
- Do not "fix" prose recall by switching to `english`. That trade is not available. (§9.1)
- CI enforces this: `tests/unit/test_fts_configuration_is_locked.py` fails on `english`
  in any SQL, and on a one-argument `to_tsvector()` whose configuration is implicit.

### 2. Document content reaches a provider only through `EgressGuard.release()`

Content crosses a provider boundary as `Released[T]`, which only the guard can construct.

```python
clearance = guard.release(Classified(text, classification), provider)
provider.submit(clearance)
```

- Never add a public method to a `Provider`. `submit()` is the only entry point; subclasses
  implement the private `_process()`. A second public method is a second way in.
- Never import a network client (`httpx`, `requests`, `boto3`, `anthropic`, `openai`, …)
  outside `app/adapters/`. CI fails on it.
- Never add `unwrap_unchecked()` calls. CI fails on new ones. It exists for local,
  no-egress paths only.
- A new component that receives document content must subclass `Provider` and declare a
  `Capability` and a `Locality`. (§8.1.1–8.1.5)

### 3. Chunks and sections span pages

A procedure starting on page 42 and ending on 44 is one section. Never model either with a
single `page_id`. Use `page_start`, `page_end`, and `cite_page` for the citation and viewer
jump. Never split a numbered procedure across chunks. (§3.1, §6)

### 4. Releases are ordered by `integer[]`, never by string

`'7.10' < '7.9'` lexically. `sort_key` is an `integer[]` (`7.4.1` → `{7,4,1}`), with
`sort_override` for schemes no rule handles. Every recency comparison goes through the
`release_order` view. (§3.1.1)

### 5. Never commit documentation files

This repository is **public**. `*.pdf` is gitignored and CI fails if one appears outside
`backend/tests/fixtures/synthetic/`. Fixtures must be synthetic or public-domain — never
internal documentation. (`docs/audit/README.md`)

### 6. Answers are structured and validated, never prose

The model returns a schema-constrained object where every claim carries evidence IDs.
Citation IDs not in the supplied evidence are rejected; quoted text is verified by
substring match against the actual chunk. A retrieval-confidence gate refuses *before*
calling the model when evidence is weak. Do not replace any of this with prompt wording
asking the model not to hallucinate. (§12)

### 7. Logs never contain document content

Chunk text, OCR output, prompts, retrieved passages, image descriptions, document titles
and filenames are all forbidden in logs, traces and error messages. IDs are fine and are
what makes debugging possible. (§8.1.3 C)

## Conventions

- Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL 16 + pgvector + pg_trgm.
- `app/api/` must not import `app/adapters/` — go through `app/services/`. `app/domain/`
  imports nothing from outer layers. Enforced by ruff.
- Type hints everywhere; `mypy --strict` must pass.
- Comments explain *why*, not *what*. Most code needs none.
- Dependencies are added in the step that first needs them, not in advance.

## Before proposing a change

```sh
make lint      # ruff + mypy
make test      # 100+ tests, including the egress property matrix
make egress    # regenerate EGRESS.md if providers or policy changed
```

**Never weaken a test to make it pass.** Several tests encode security properties or
document defects deliberately — `test_english_config_is_unsafe_here` asserts that
PostgreSQL *is* broken in a specific way, and `tests/unit/test_egress_bypass.py` performs
real bypass attempts. If one fails, the change is wrong, not the test.

## Current state

STEP 1 (skeleton, egress policy) is complete. STEP 2 is the database schema. Providers are
deliberately stubs raising `NotImplementedError` — do not implement them ahead of their
step. The roadmap is §23.
