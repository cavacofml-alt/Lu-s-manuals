# Documentation Intelligence AI — Technical Design

Status: **revision 3 — incorporates the second architecture review.**
**STEP 1 (skeleton) is implemented and committed**; STEP 2 (schema) has not started.

The previous revision said "no implementation has started". That was true when written and
became stale when STEP 1 was built. The second review caught the discrepancy, which is the
correct catch: a design document that misstates the state of the work is a liability, since
every later claim inherits its credibility. What is built is listed in §24.

Changes in this revision: the classification policy is generalised from embeddings to **all
providers that can receive document content** — answering model, reranker, vision, OCR — and
renamed accordingly (§8.1.1); the unproven claim "there is no code path" is replaced by the
mechanism and the tests that support it; the `english` full-text inversion is **empirically
verified on PostgreSQL 16.13** and is worse than first described (§9.1); release ordering made
scheme-tolerant (§3.1.1); embeddings moved to per-model tables with an online re-embedding path
(§3.6); PDF library re-evaluated on licence and capability, reversing the initial choice (§4.1);
open decisions consolidated (§21); project structure and STEP 1 plan (§22, §24).

Section numbers in `[§n]` refer to the Master Project Brief.

---

## 0. Executive summary

The system is a **document-grounded retrieval and answering service** over versioned PDF
documentation, with an evidence chain that survives from ingestion to the rendered answer.

The three decisions that determine whether this project succeeds or fails are:

1. **The identity model for documents, versions and releases.** If this is wrong, every
   downstream guarantee about "the right release" is unenforceable. Addressed in §3.
2. **Exact-phrase retrieval for technical strings.** Semantic search cannot find
   `PNL NOT PROCESSED`. Naive Postgres full-text search *also* cannot — see the stopword
   problem in §9.1, which is the single most important correctness detail in this document.
3. **Grounding enforcement as code, not as prompt text.** "Do not hallucinate" in a system
   prompt is a preference, not a control. Addressed in §12.

Everything else — OCR, images, export, the viewer — is engineering work with known shapes.

**Recommended stack:** Python 3.12 / FastAPI / SQLAlchemy 2.x / PostgreSQL 16 + pgvector /
pypdfium2 + pdfplumber (permissively licensed — see §4.1) / Tesseract (OCR fallback) /
Claude Opus 5 for answering / React + Vite + pdf.js.
No Redis, no Celery, no separate vector DB, no object store in the MVP. Rationale throughout.

Decisions still open, and what binds them, are consolidated in **§21 Open Architectural
Decisions**. Nothing in that list blocks STEP 1.

---

## 1. Current repository structure

The repository `cavacofml-alt/Lu-s-manuals` is **empty** — no commits, no branches, no files.
There is no existing code, schema, configuration or CI to preserve or migrate. Every decision
below is greenfield, which removes the usual constraint of compatibility with prior choices.

One consequence worth stating: there is **no corpus in the repository either**. Several
requirements in the brief (§33 golden dataset, §48 real-document testing, §45 authority model)
cannot be finalised without seeing representative documents. Those sections below define the
*mechanism* and flag the *inputs still required from you*.

---

## 2. Architecture

### 2.1 Shape

A modular monolith with a separate worker process. Not microservices.

```
┌────────────────────────────────────────────────────────┐
│  frontend/          React + Vite + TypeScript          │
│    chat · sources · pdf viewer · doc admin · search    │
└───────────────────────┬────────────────────────────────┘
                        │ REST + SSE
┌───────────────────────┴────────────────────────────────┐
│  api/           FastAPI — thin HTTP layer only         │
├────────────────────────────────────────────────────────┤
│  services/      use cases; owns transactions           │
│    ask · search · ingest · export · documents          │
├────────────────────────────────────────────────────────┤
│  domain/        entities, value objects, policies      │
│    authority policy · version resolution · citation    │
├────────────────────────────────────────────────────────┤
│  adapters/      ports & implementations                │
│    llm/ · embeddings/ · docproc/ · ocr/ · storage/     │
│    rerank/ · render/                                   │
├────────────────────────────────────────────────────────┤
│  db/            SQLAlchemy models, Alembic migrations  │
└────────────────────────────────────────────────────────┘
          ▲                              ▲
          │                              │
┌─────────┴──────────┐        ┌──────────┴──────────────┐
│  worker/           │        │  PostgreSQL 16          │
│  ingestion jobs    │        │  + pgvector             │
│  (separate process)│        │  + pg_trgm              │
└────────────────────┘        └─────────────────────────┘
```

The worker is a **separate OS process running the same codebase**, not a separate service.
It imports `services.ingest` directly. This gives process isolation for CPU-heavy PDF/OCR work
without the operational cost of a second deployable.

### 2.2 Why a monolith

[§40 "simple where possible"] The brief asks for modularity, which is a *code* property, not a
*deployment* property. Splitting ingestion and retrieval into separate services at this stage
would add network boundaries, deployment surface and distributed-failure modes to solve a
scaling problem that does not yet exist [§36 "do not optimize prematurely"]. The module
boundaries above are enforced by import discipline and can be extracted into services later
without rewriting business logic.

### 2.3 Ports (provider abstractions) [§21]

Every provider that can receive document content is a `Provider` subclass declaring a `Capability`
and a `Locality`, with **one** public entry point:

```python
class Provider:
    name: str
    locality: Locality        # cloud | local — does using this disclose content?
    capability: Capability    # embedding | llm | rerank | vision | ocr | storage | …

    def submit(self, released: Released[Any]) -> Any:
        # refuses anything not cleared by EgressGuard.release() for THIS provider
        ...
    def _process(self, payload: Any) -> Any:   # subclasses implement this
        ...
```

An earlier revision also declared a parallel set of `Protocol` interfaces in
`app/adapters/ports.py` — `StorageProvider.put(key, BinaryIO)`,
`EmbeddingProvider.embed_documents(list[str])` and others — taking raw content with no locality and
no guard. Nothing referenced them, but a file named "Provider interfaces" is exactly what a
developer implementing storage would find first, and implementing against it would have produced a
second egress path that no policy covered. **They are deleted.** There is one provider mechanism,
not two.

Model identity (`embedding_model_id`, `dimensions`) lives in configuration and in the
`embedding_models` registry rather than on the interface, since it determines which table a vector
is written to and a mismatch is caught at startup (§3.6).

---

## 3. Database schema

**PostgreSQL 16 + pgvector + pg_trgm.** [§16] Agreed — a separate vector database would be a
second source of truth for the same objects, and the evidence chain is fundamentally relational.
Postgres gives transactional consistency between a chunk, its vector, its page and its permissions,
which is exactly the invariant the brief cares most about.

### 3.1 Departures from the proposed schema

The brief's schema has three modelling errors that will cause real, user-visible bugs. I recommend
against implementing it as written.

**(a) `sections.page_id` is wrong — sections span pages.**
A procedure starting on page 42 and ending on page 44 is one section. Keying a section to a single
page forces either duplicate section rows per page (breaking "which section is this?") or truncation
at the page boundary (breaking §8 "avoid chunks that destroy procedural context"). A section belongs
to a **document version** and carries a page *range*.

**(b) `chunks.page_id` is wrong for the same reason.**
A semantically coherent chunk frequently crosses a page break. A single `page_id` forces a choice
between splitting mid-procedure or recording a false page. A chunk therefore carries
`page_start`/`page_end`, plus `cite_page` — the page used for citation display and viewer
navigation, which is the page where the chunk's *content begins*. This keeps §23 (jump to exact
page) honest while keeping §8 (don't destroy procedures) satisfied.

**(c) `release` as a string column on `document_versions` cannot be ordered.**
[§9, §15, §45 all depend on "which release is newer".] `'7.10' < '7.9'` under string comparison,
and `'7.4'::float` collapses `7.40` and `7.4`. Release ordering is a business fact that must be
explicit and editable, so releases become a **first-class table with an ordering key**. This also
gives release-level metadata (GA date, supported/EOL status) a home and makes §10 (release
comparison) expressible as a join rather than string parsing.

I also restructure embeddings into their own table (§3.6), add access-control primitives (§3.3),
and an `image_phash` for cross-release screenshot diffing (§10).

### 3.1.1 Canonical release ordering

The ordering key must survive heterogeneous real-world release labels:
`7.4`, `7.4.1`, `7.10`, `2026.1`, `R7.4`, `7.4 SP2`. A single integer cannot express these.

**`sort_key` is an `integer[]`.** Postgres compares integer arrays element-wise, which yields
correct results for every case above, including differing lengths:

| Label | `sort_key` | |
|---|---|---|
| `7.4` | `{7,4}` | |
| `7.4.1` | `{7,4,1}` | `{7,4} < {7,4,1}` ✓ |
| `7.9` | `{7,9}` | |
| `7.10` | `{7,10}` | `{7,9} < {7,10}` ✓ — the bug this exists to prevent |
| `R7.4` | `{7,4}` | prefix is presentation, stripped into `label` |
| `2026.1` | `{2026,1}` | `{7,10} < {2026,1}` ✓ |
| `7.4 SP2` | `{7,4,0,2}` | service pack as a trailing component |

Canonicalisation rule: strip non-numeric prefixes/suffixes into the display `label`, split the
numeric core on `.`, map each component to an integer. The function is deterministic and unit
tested against the table above.

Two safeguards, because canonicalisation of an unforeseen scheme will eventually be wrong:

- **`sort_key` is stored, not computed at query time.** The parser proposes it; a curator confirms
  it in the admin UI when registering a release. A wrong ordering is then a visible data fix, not
  a code deploy.
- **`sort_override integer[]`** takes precedence when present, for labels no rule can handle, and
  for the case where an organisation changes numbering scheme mid-life (e.g. `7.x` → `2026.x`)
  and the arithmetic ordering happens not to match the business ordering.

Ordering across two different numbering schemes is a business fact, not a parsing problem. The
schema makes it representable and correctable; it does not pretend to infer it.

### 3.2 Core DDL (proposal)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── Product releases: ordered, first-class ────────────────────────────────
CREATE TABLE releases (
    id              bigserial PRIMARY KEY,
    label           text NOT NULL UNIQUE,        -- 'R7.4'  — as displayed
    sort_key        integer[] NOT NULL,          -- {7,4}   — see §3.1.1
    sort_override   integer[],                   -- wins over sort_key when set
    ga_date         date,
    eol_date        date,
    is_current      boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now()
);
-- effective ordering key, used everywhere recency is compared
CREATE VIEW release_order AS
    SELECT id, label, coalesce(sort_override, sort_key) AS ord FROM releases;
CREATE UNIQUE INDEX ON releases (is_current) WHERE is_current;   -- at most one current

-- ── Document identity (stable across releases) ────────────────────────────
CREATE TABLE documents (
    id              bigserial PRIMARY KEY,
    title           text NOT NULL,
    document_type   text NOT NULL,   -- manual | quick_reference | release_notes | ...
    authority_tier  smallint NOT NULL,            -- see §11; lower = more authoritative
    description     text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- ── A concrete file: one document, one release ────────────────────────────
CREATE TYPE ingestion_state AS ENUM
    ('uploaded','processing','ocr','indexing','ready','failed','superseded');

CREATE TABLE document_versions (
    id                bigserial PRIMARY KEY,
    document_id       bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    release_id        bigint NOT NULL REFERENCES releases(id),
    version_label     text,                        -- document's own rev, e.g. 'Rev C'
    filename          text NOT NULL,
    checksum_sha256   char(64) NOT NULL,
    storage_ref       text NOT NULL,
    page_count        integer,
    effective_date    date,
    publication_date  date,
    state             ingestion_state NOT NULL DEFAULT 'uploaded',
    is_ocr_derived    boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, release_id, version_label),
    UNIQUE (checksum_sha256)                       -- §19 idempotency
);

CREATE TABLE pages (
    id                  bigserial PRIMARY KEY,
    document_version_id bigint NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    page_number         integer NOT NULL,          -- 1-indexed, physical PDF page
    printed_label       text,                      -- 'iv', '3-7' if it differs
    text                text,
    is_ocr              boolean NOT NULL DEFAULT false,
    ocr_confidence      real,                      -- mean word confidence, 0..1
    width               real,
    height              real,
    UNIQUE (document_version_id, page_number)
);

CREATE TABLE sections (
    id                  bigserial PRIMARY KEY,
    document_version_id bigint NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    parent_id           bigint REFERENCES sections(id) ON DELETE CASCADE,
    title               text NOT NULL,
    level               smallint NOT NULL,
    path                text NOT NULL,             -- 'ADL > Check-in > Procedure'
    page_start          integer NOT NULL,
    page_end            integer NOT NULL,
    ordinal             integer NOT NULL
);

CREATE TABLE chunks (
    id                  bigserial PRIMARY KEY,
    document_version_id bigint NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    section_id          bigint REFERENCES sections(id) ON DELETE SET NULL,
    chunk_index         integer NOT NULL,
    page_start          integer NOT NULL,
    page_end            integer NOT NULL,
    cite_page           integer NOT NULL,          -- page to open in the viewer
    heading_path        text,                      -- prepended at embed time
    text                text NOT NULL,
    token_count         integer NOT NULL,
    is_ocr              boolean NOT NULL DEFAULT false,
    tsv                 tsvector,                  -- see §9.1 for the configuration
    UNIQUE (document_version_id, chunk_index)
);

-- Embeddings live apart from chunks so the corpus can be re-embedded with a
-- different model/provider without touching chunk rows, and so two embedding
-- sets coexist during a cutover. See §3.6.
CREATE TABLE embedding_models (
    id              text PRIMARY KEY,             -- 'voyage-3' | 'bge-m3'
    provider        text NOT NULL,                -- 'voyage' | 'local'
    dimensions      integer NOT NULL,
    table_name      text NOT NULL,                -- concrete table, see below
    is_active       boolean NOT NULL DEFAULT false,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ON embedding_models (is_active) WHERE is_active;

-- One concrete table per registered model. pgvector requires a FIXED dimension
-- on the column to build an HNSW index, so a single polymorphic `vector` column
-- cannot be indexed. Registering a model therefore emits a migration creating
-- its table and index; the repository layer routes to the active model's table.
-- Model changes are rare (order of once a year), so a migration per model is an
-- acceptable price for correct indexing.
CREATE TABLE chunk_emb_voyage3 (                  -- template
    chunk_id  bigint PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    embedding vector(1024) NOT NULL
);

CREATE TABLE images (
    id                  bigserial PRIMARY KEY,
    document_version_id bigint NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    page_number         integer NOT NULL,
    section_id          bigint REFERENCES sections(id) ON DELETE SET NULL,
    storage_ref         text NOT NULL,
    thumb_ref           text,
    bbox                box,                       -- PDF user space; enables highlighting
    width               integer,
    height              integer,
    caption             text,                      -- figure caption if detected
    surrounding_text    text,
    vlm_description     text,                      -- §7.2 — generated at ingest
    kind                text,                      -- screenshot | diagram | table | logo
    phash               bit(64)                    -- §10 cross-release comparison
);

-- Image vectors follow the same per-model table pattern as chunks.
CREATE TABLE image_emb_voyage3 (                   -- template
    image_id  bigint PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
    embedding vector(1024) NOT NULL                -- caption + description + surrounding
);

CREATE TABLE ingestion_jobs (
    id                  bigserial PRIMARY KEY,
    document_version_id bigint REFERENCES document_versions(id) ON DELETE CASCADE,
    state               ingestion_state NOT NULL,
    stage               text,
    progress            real,
    attempts            smallint NOT NULL DEFAULT 0,
    error               text,
    locked_by           text,
    locked_at           timestamptz,
    started_at          timestamptz,
    completed_at        timestamptz
);

-- ── Conversations, answers, evidence ──────────────────────────────────────
CREATE TABLE conversations (
    id          bigserial PRIMARY KEY,
    user_id     bigint NOT NULL REFERENCES users(id),
    title       text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE messages (
    id               bigserial PRIMARY KEY,
    conversation_id  bigint NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             text NOT NULL,                -- user | assistant
    content          text,
    answer_json      jsonb,                        -- the StructuredAnswer, §19
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- One row per (message, evidence actually used). Reconstructs §4's chain exactly.
CREATE TABLE citations (
    id                  bigserial PRIMARY KEY,
    message_id          bigint NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    chunk_id            bigint REFERENCES chunks(id) ON DELETE SET NULL,
    image_id            bigint REFERENCES images(id) ON DELETE SET NULL,
    document_version_id bigint NOT NULL REFERENCES document_versions(id),
    page_number         integer NOT NULL,
    section_path        text,
    quoted_text         text NOT NULL,             -- snapshot: survives re-ingestion
    char_start          integer,
    char_end            integer,
    rank                smallint NOT NULL,
    retrieval_score     real
);

CREATE TABLE feedback (
    id           bigserial PRIMARY KEY,
    message_id   bigint NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    user_id      bigint NOT NULL REFERENCES users(id),
    helpful      boolean NOT NULL,
    source_wrong boolean,
    incomplete   boolean,
    wrong_version boolean,
    comment      text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
```

`citations.quoted_text` is stored denormalised **on purpose**. Chunk boundaries change when
chunking strategy changes; a citation recorded last month must still show what the answer was
actually based on. Without this snapshot, §31 (history) and the audit trail silently rot on the
first re-ingestion.

### 3.3 Access control tables [§30]

```sql
CREATE TABLE users (
    id            bigserial PRIMARY KEY,
    email         citext NOT NULL UNIQUE,
    display_name  text,
    role          text NOT NULL DEFAULT 'reader',   -- reader | curator | admin
    is_active     boolean NOT NULL DEFAULT true
);

CREATE TABLE document_acl (
    document_id  bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    group_name   text NOT NULL,
    PRIMARY KEY (document_id, group_name)
);

CREATE TABLE user_groups (
    user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_name  text NOT NULL,
    PRIMARY KEY (user_id, group_name)
);

CREATE TABLE audit_log (
    id          bigserial PRIMARY KEY,
    user_id     bigint REFERENCES users(id),
    action      text NOT NULL,        -- ask | open_document | download | upload | delete
    object_type text,
    object_id   bigint,
    metadata    jsonb,                -- never document text
    ip          inet,
    at          timestamptz NOT NULL DEFAULT now()
);
```

### 3.4 Indexes

```sql
CREATE INDEX chunks_tsv_idx      ON chunks USING gin (tsv);
CREATE INDEX chunks_trgm_idx     ON chunks USING gin (text gin_trgm_ops);
CREATE INDEX chunks_dv_idx       ON chunks (document_version_id);
CREATE INDEX dv_doc_release_idx  ON document_versions (document_id, release_id);
CREATE INDEX jobs_claim_idx      ON ingestion_jobs (state, id) WHERE state <> 'ready';

-- created with each per-model embedding table
CREATE INDEX chunk_emb_voyage3_idx ON chunk_emb_voyage3
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX image_emb_voyage3_idx ON image_emb_voyage3
    USING hnsw (embedding vector_cosine_ops);
```

**HNSW + filtering caveat.** Vector search filtered by release or by ACL can silently lose recall:
HNSW returns its `ef_search` nearest neighbours *before* the filter is applied, so a restrictive
filter can leave very few rows. pgvector 0.8+ addresses this with `hnsw.iterative_scan = relaxed_order`,
which we will enable, plus an `ef_search` floor. This must be verified with a recall test against a
realistic corpus during STEP 5 — it is a known trap, not a hypothetical.

### 3.5 Storage [§17]

Agreed: binaries do not go in Postgres. But **MinIO/S3 is not warranted for the MVP.**
`LocalFilesystemStorage` behind `StorageProvider` writes to a content-addressed tree
(`{sha256[0:2]}/{sha256}/original.pdf`, `.../images/p042-03.png`). An `S3Storage` implementation is
~80 lines when a deployment needs it. Standing up object storage on day one adds infrastructure
[§40] for zero MVP benefit. PDFs and images are always served through an authorising API endpoint,
never a static path [§30].

### 3.6 Re-embedding the corpus

Vectors from different models are not comparable, so "change the embedding model" is never an
in-place update — it is a corpus migration. The schema above makes that migration safe and
online, which is a hard requirement from the architecture review:

1. Register the new model in `embedding_models`; the migration creates `chunk_emb_<model>` and
   its HNSW index. The old model's table is untouched and stays active.
2. Backfill the new table with a resumable worker job. Retrieval continues to serve from the
   active model throughout — no downtime, no degraded window.
3. Validate: row counts match `chunks`, dimensions correct, and the **retrieval eval suite
   (§17.1) is run against the new model**. This is the point of having the eval suite: a model
   swap is precisely the kind of change that silently degrades quality [§34].
4. Flip `is_active` in one transaction. Rollback is flipping it back — the old vectors still
   exist.
5. Drop the old table only after a deliberate retention period.

Two consequences worth stating: the corpus can be re-embedded from the stored `chunks.text`
without re-parsing any PDF, and a **provider switch never requires re-ingestion**. Chunk
identity, citations, page references and images are all independent of the embedding model.

This is what "no vendor lock-in" means concretely. The `EmbeddingProvider` port makes a provider
*swappable in code*; this table structure makes it *swappable in production with data already
indexed*, which is the part that actually costs money if it is not designed in from the start.

---

## 4. Document processing pipeline [§18]

```
upload → validate → checksum → duplicate check → register version
   → extract structure → extract text (per page) → OCR decision (per page)
   → extract images → extract tables → detect sections → chunk
   → embed (batched) → index → validate → READY
```

### 4.1 PDF processing library — evaluation and decision

The architecture review declined to approve PyMuPDF on technical convenience alone and asked for a
comparison across licence, extraction quality, pages, images, tables, OCR, performance, Python
3.11+ support and deployment. That comparison follows; the conclusion reverses my initial choice.

| | **PyMuPDF** | **pypdfium2** | **pdfplumber** | **pdfminer.six** | **Docling** |
|---|---|---|---|---|---|
| Licence | **AGPL-3.0** or paid commercial | BSD-3/Apache-2.0 | MIT | MIT | MIT |
| Text + coordinates | Excellent | Good | **Excellent** (char-level) | Good | Good |
| Font/size metadata (headings) | Excellent | Adequate | Good | Good | **Model-based** |
| Page fidelity / rasterisation | Excellent | **Excellent** (PDFium) | via conversion | No | Good |
| Embedded image extraction | **Excellent** (+bbox) | Limited | Metadata/bbox only | No | Good |
| Tables | Good | None | **Excellent** | None | **Excellent** |
| Complex/damaged PDFs | Very robust | Very robust (Chromium) | Moderate | Moderate | Moderate |
| OCR | External | External | External | External | Bundled |
| Performance | **Fastest** (C) | Fast (C++) | **Slow** (pure Python) | Slow | Slowest (ML) |
| Python 3.11+ | Yes | Yes | Yes | Yes | Yes |
| Deployment | Wheels, trivial | Wheels, trivial | Pure Python | Pure Python | **Heavy** (model downloads) |

**The licence question is not marginal, and my earlier framing of it was too casual.**
AGPL-3.0 §13 is triggered by users interacting with the software *remotely over a network* — which
is exactly what this system is. The common intuition "it's internal, so we're not distributing"
addresses the GPL's distribution clause, not the AGPL's network clause. Whether internal-only use
by employees of the same legal entity engages §13 is a question for your legal function, not for
me, and not one to leave unresolved under a knowledge platform meant to last years. Artifex sells a
commercial licence precisely because many companies land in this position.

**Decision: `pypdfium2` + `pdfplumber` + `Pillow` as the default `DocumentProcessor`.**
All permissive (BSD/Apache/MIT), no legal question to resolve, no procurement step.

Division of labour: pypdfium2 does bulk text extraction and page rasterisation (fast, C++,
Chromium-grade robustness on malformed files); pdfplumber runs **only on pages where table or
fine-grained coordinate work is needed**, which contains its performance cost rather than paying
it per page.

What we give up, honestly: PyMuPDF's embedded-image extraction is better, and it is faster
overall. The image gap is mitigated by a technique the design already wanted for a different
reason — **rasterising detected image regions from the rendered page** (§7.1) rather than pulling
embedded image streams. That approach captures vector-drawn diagrams, which embedded-image
extraction misses entirely, so the permissively licensed path is actually *better* for the
diagram case, not merely acceptable.

`PyMuPDFProcessor` remains implementable behind the same port as an **optional extra**, not a
default dependency, for a deployment that holds an Artifex commercial licence or has concluded
AGPL is acceptable. The port is what makes this a configuration choice rather than a rewrite.

Docling is the most interesting alternative for structure quality and is MIT-licensed; it is
rejected for the MVP on deployment weight (ML model downloads, GPU-adjacent runtime) under §40,
and noted in §21 as a candidate if section detection proves weak on the real corpus.

### 4.2 Job execution — no Celery, no Redis

[§18 asynchronous] I recommend **a Postgres-backed job queue** claimed with
`SELECT ... FOR UPDATE SKIP LOCKED`, polled by the worker process.

Reasoning: Celery + Redis introduces a broker, a result backend, a second serialization format and
an at-least-once delivery model that must be reconciled with the database anyway. The workload here
is tens to thousands of jobs per *day*, each taking seconds to minutes — it is not throughput-bound.
A `SKIP LOCKED` queue in the database we already operate gives exactly-once-ish semantics in the
same transaction as the state change, visible in the same `ingestion_jobs` table the UI already
reads [§29], with no extra infrastructure [§40]. Stale-lock reclamation (`locked_at` older than a
timeout) covers worker crashes.

If ingestion volume ever justifies a real broker, the port boundary makes that a contained change.

### 4.3 Atomic re-ingestion

Re-processing an existing version must never leave the corpus half-indexed. The job builds all new
rows, validates them (§4.4), and only then flips `document_versions.state` to `ready` in one
transaction, marking the prior generation `superseded`. Retrieval filters on `state = 'ready'`, so a
partially-built version is invisible rather than partially visible.

### 4.4 Idempotency [§19]

Two distinct cases, which the brief conflates:

- **Byte-identical re-upload** — `checksum_sha256` collides. Return the existing version, do not
  re-ingest, record the upload attempt in the audit log. Idempotent.
- **New release of the same document** — different bytes, same `document_id`, new `release_id`.
  This is a *new version*, not a duplicate. The uploader supplies (or the system infers, subject to
  confirmation) the document identity and release; the `(document_id, release_id, version_label)`
  unique constraint prevents accidental doubles.

Auto-inferring document identity from filename is unreliable and will eventually merge two unrelated
manuals. The upload UI should propose an inferred match and **require confirmation** [§29].

### 4.5 Indexing validation

Before `READY`, assert: every page has text or an OCR record; chunk count > 0; every chunk has a
non-null embedding of the expected dimension and model; `cite_page` within `[1, page_count]`; every
image file exists in storage. Failure → `failed` with the specific assertion in `error` [§29 "show
processing errors clearly"].

---

## 5. OCR strategy [§7]

Agreed that OCR is a fallback. One refinement: **the decision is per page, not per document.**
Mixed documents — a digital manual with three scanned appendix pages, or a screenshot-heavy guide —
are common, and a document-level flag either over-OCRs (slow, lower quality than the embedded text)
or under-OCRs (silently loses the appendix).

Heuristic per page: extract embedded text; if character count below a threshold **and** the page has
significant image coverage, rasterise at ~300 DPI and OCR (Tesseract via `pytesseract`, language
configurable). Record `is_ocr` and `ocr_confidence` on the page and propagate to derived chunks.

**OCR text must be treated as lower-trust for exact-phrase matching.** This is a point the brief
doesn't make and it matters: OCR reliably corrupts exactly the strings §11 cares about — `0`/`O`,
`1`/`l`/`I`, `5`/`S` inside error codes and status values. Consequences in the design:

- keyword scores from OCR-derived chunks carry a configurable down-weight;
- trigram matching (§9.1) partly rescues near-miss OCR strings that exact matching loses;
- answers citing low-confidence OCR pages surface an "OCR-derived source" marker in the UI, so a
  user can verify against the original [§2 traceability over performance].

---

## 6. Chunking strategy [§8]

Structure-aware, not fixed-width.

1. Build the section tree from the PDF outline where present, else from font-size/weight clustering.
2. Chunk **within** section boundaries; never merge across a top-level section.
3. Target ~500 tokens, hard ceiling ~900, overlap ~80 tokens between adjacent chunks in a section.
4. **Never split a numbered procedure.** A detected step list is atomic; if it exceeds the ceiling
   it becomes an oversized chunk rather than a broken one. A truncated procedure is worse than a
   large chunk — a user who follows half a procedure is worse off than one who reads a long page.
5. Tables are extracted as a unit and serialised to Markdown, kept whole, with the caption attached.
6. Each chunk is prefixed at embed time with its `heading_path` and document/release label
   (`ADL Check-in Manual · 7.4 · ADL > Check-in > Procedure`). This is the cheapest available
   retrieval improvement: it gives the embedding the context the chunk text itself omits, and it
   disambiguates near-identical text across releases.

**Contextual retrieval** (an LLM-generated one-line situating sentence per chunk, cached) is a
known, substantial recall improvement, but it costs one cheap LLM call per chunk at ingest. I
recommend it as a **phase-2 change gated on the evaluation suite** (§17) rather than an MVP
assumption — it is exactly the kind of change the golden dataset exists to justify.

---

## 7. Image processing strategy [§5, §6, §24]

### 7.1 Extraction

Image regions are located from the page's object layout and **rasterised from the rendered page**
via pypdfium2, rather than pulled as embedded image streams (§4.1). This is the approach that makes
vector-drawn diagrams work — they have no embedded raster to extract — so one mechanism covers
screenshots and diagrams alike. Filter noise by size, aspect ratio and
repetition across pages (headers/logos appear on every page and are discarded). Captions are
detected from text runs immediately below/above the bbox matching `Figure|Fig\.|Screenshot|Diagram`
patterns; when absent, `surrounding_text` is the ±N characters of page text nearest the bbox.
Each image is written to storage with a thumbnail, and keeps
`document_version_id + page_number + section_id + bbox` — the §5 association requirement.

Rasterisation happens at a resolution high enough for §24 ("preserve reasonable quality",
"be printable") — 2× the page's nominal scale — with the original bbox retained so the viewer can
highlight the region in place (§13.2).

### 7.2 Image retrieval — the part the brief underspecifies

Retrieving images by surrounding text alone is weak, and it is the direct cause of the §50 failure
mode "can it show an unrelated screenshot?". A screenshot's surrounding text is often
"…as shown below." — which matches nothing useful.

**Recommendation: generate a description for every extracted image at ingest time using a vision
model** (Claude), store it in `images.vlm_description`, and embed `caption + description +
surrounding_text` together. A one-off cost of one cheap vision call per image buys a genuinely
searchable visual index — "the check-in screen with the PNL status field" can then match an image
whose page text never says so.

### 7.3 Showing an image [§6, §24]

An image is displayed only if **all** hold:
- it is on a page cited by the answer, or in a cited section;
- its relevance score passes an absolute threshold (not merely "best available");
- at most 2–3 images per answer, highest first.

If nothing passes, no image is shown. The brief is right that a wrong screenshot is worse than none.
No image is ever generated or substituted [§6] — the renderer has no image-generation path at all,
which makes that guarantee structural rather than behavioural.

---

## 8. Embedding strategy

### 8.1 Provider decision

**Anthropic does not offer an embeddings API.** Claude is the answering model [§21]; embeddings
must come from elsewhere. Since §30 says the documentation may be confidential, this is a data
governance decision, not only a quality one: *embedding a corpus through a third-party API sends
the full text of that corpus to the third party.*

| | Hosted (`voyage-3`) | Self-hosted (`BAAI/bge-m3`) |
|---|---|---|
| Retrieval quality | Higher out of the box | Strong; competitive |
| Corpus text leaves the network | **Yes** | **No** |
| Ops burden | None | GPU, or slower CPU inference |
| Cost | Per-token, small | Fixed infrastructure |
| Multilingual | Good | Excellent |
| Dimensions | 1024 | 1024 |

**Decision (per architecture review): hosted `voyage-3` as the initial implementation, with
`LocalEmbeddingProvider` (`bge-m3`) implemented against the same port and a documented,
tested migration path (§3.6).** Both are 1024-dimensional, so a switch does not even change the
column type.

**Why `voyage-3` for the initial provider:** strongest retrieval quality per unit of effort on
technical English documentation, no infrastructure, and a 1024-dimension output matching the
self-hosted alternative. Chosen over OpenAI `text-embedding-3-large` mainly for that dimensional
symmetry (3072 dims would make the local fallback a schema change, not a config change).

#### What is sent, and when

Being precise about this, because "we abstracted the provider" is not by itself a privacy control:

| Data | Sent to embedding provider? |
|---|---|
| Chunk text (the document body) | **Yes** — this is the entire indexed corpus |
| Section headings, document titles | **Yes**, as part of the chunk prefix (§6) |
| OCR text from scanned pages | **Yes** |
| User questions | **Yes**, at query time (one short string per question) |
| Original PDF files | No |
| Extracted images | No |
| VLM image descriptions | **Yes**, if image embeddings are enabled |
| Retrieved passages | Separately, to Anthropic, at answer time |

So: **the documentation corpus goes to two external parties** — the embedding provider at ingest
and Anthropic at answer time. A "no external processing" posture requires replacing both, and the
ports make that possible; `LLMProvider` is the second one.

#### One caveat I want on the record

The review's position that "embeddings are not irreversible, we can re-embed" is correct about
**technical** reversibility, and §3.6 now guarantees it. It does not apply to **disclosure**:
once the corpus has been transmitted, it has been disclosed, and re-embedding locally afterwards
does not undo that. These are different properties and only the first is under our control.

The practical consequence is a good one, though: since the provider is a configuration value, the
binding moment is **the first ingestion of real confidential documents**, not the writing of code.
Development and evaluation can proceed against a hosted provider with non-confidential or sample
material while the governance question is settled in parallel. **This decision therefore no longer
blocks STEP 3 or STEP 4.** It must be settled before the production corpus is ingested, and the
deployment checklist will carry it as an explicit gate.

### 8.1.1 Data classification policy [architecture review requirement]

The review's point is correct and it is the right shape: a document must never reach a cloud
provider merely because that provider happens to be configured. The guard belongs in the
architecture, not in operator attention.

Every document carries a classification; every provider declares a locality. A matrix decides, and
**the default answer is no**.

```sql
CREATE TYPE data_classification AS ENUM
    ('public','internal','confidential','highly_confidential');

ALTER TABLE documents
    ADD COLUMN classification data_classification NOT NULL DEFAULT 'confidential';
```

Defaulting to `confidential` is deliberate: an unclassified document is treated as sensitive until
someone says otherwise. The failure mode of a forgotten classification should be a refusal to
process, not a silent upload.

```yaml
embedding_policy:
  mode: mixed              # strict_local | mixed | permissive
  matrix:
    public:               [cloud, local]
    internal:             [cloud, local]     # configurable per deployment
    confidential:         [local]
    highly_confidential:  [local]
```

`mode: strict_local` collapses the whole matrix to local regardless of its contents — the
single-switch posture the review asked for, for an installation that must guarantee no egress.

**Scope: every provider, not just embeddings.** The second review was right that scoping this to
embeddings was the wrong boundary. Document content reaches the answering model, the reranker, the
vision model that describes screenshots, OCR, and any future translation or summarisation step —
each is an egress channel. A policy named `EmbeddingPolicy` would have guaranteed that the next
provider added was not covered by it. The `Capability` enum enumerates every content-receiving
role, and a provider cannot be registered without declaring one.

**Enforcement** (a policy that must be *remembered* is not a control):

1. **Type-level.** Document content is not a bare `str` at the provider boundary; it is
   `Classified[T]`. A provider cannot be handed content except through `EgressGuard.release`,
   which checks the policy against *that specific provider*. Resolving a permitted provider and
   then sending the content elsewhere is checked too, and refused.
2. **Bypass is conspicuous.** The only way out is `unwrap_unchecked(reason=...)`, which names
   itself, requires a stated justification at the call site, and is failed by a CI grep so that
   each occurrence is a review decision rather than a habit.
3. **Upload.** A document whose classification no configured provider can serve is rejected at
   upload with an explanatory error, not accepted and failed later.
4. **Startup, two independent checks.** Every *required* capability must have a provider permitted
   for the declared `handles_classification`; and under `strict_local`, the mere *presence* of any
   cloud provider in any capability fails startup — not "a local one also exists", since a
   configured cloud provider can be selected by a future code path.
5. **Audit.** Every release logs `(provider, locality, capability, classification)` and never the
   content. "Has confidential material ever left the network?" becomes a question with evidence,
   which is what §30's audit requirement is for.

**What is and is not proven.** Revision 2 claimed "there is no code path where a chunk reaches a
provider without passing this resolution". That was an assertion, not a demonstration, and the
review was right to reject it. What can be said now: the mechanism makes such a path require a
deliberate, named, CI-visible act; and the property is exercised as a test matrix over every
capability × every classification × every policy mode, plus the bypass routes. `EGRESS.md` in the
repository root is generated by running the real guard and reports whether the property holds.
That is stronger than an assertion and weaker than a proof, and it should be described as such.

### 8.1.2 What the barrier is, and what it is not

The third review challenged the claim that `Classified[T]` closes the bypass, and asked for the
execution path rather than a conceptual defence. The challenge was correct. Before the change
described here, **all three of the review's hypothesised bypasses worked**, demonstrated by running
them against the code:

```
VoyageEmbeddings().embed_documents(["CONFIDENTIAL"])  → reached provider code
payload.unwrap_unchecked("any reason")                → returned raw content
ClaudeVision().describe(classified_payload)           → accepted by the signature
```

`Classified[T]` is a **type contract**. It makes classification travel with content and makes an
unclassified call site visible to a reader and to mypy. It is not a runtime control, and saying
otherwise would have been the exact failure the review was guarding against.

**The runtime control is `Released[T]`.** A provider's public API (`Provider.submit`) accepts only a
`Released`, and `Released.__init__` refuses construction without a sentinel held privately by
`EgressGuard`. The clearance also records which provider it was issued for, so one obtained
legitimately for a local provider cannot be replayed against a cloud one. The execution path:

```
Classified(content, CONFIDENTIAL)
   → EgressGuard.release(payload, provider)
        ├─ policy.permits(classification, provider.locality)?  no  → EgressViolation
        └─ yes → Released(..., _key=_GUARD_ONLY)        ← only construction site
   → provider.submit(released)
        ├─ isinstance(released, Released)?        no → EgressViolation
        ├─ released.provider_name == self.name?   no → EgressViolation
        └─ yes → self._process(value)
```

Verified against the current code — each refused at runtime, not by a type checker:

| Attempt | Result |
|---|---|
| Direct call to a cloud adapter with a raw string | `EgressViolation` |
| `unwrap_unchecked(...)` then submit to cloud | `EgressViolation` |
| `Classified` passed straight to an adapter | `EgressViolation` |
| Hand-constructed `Released` | `EgressViolation` |
| Local clearance replayed against a cloud provider | `EgressViolation` |
| Asking the guard for a cloud clearance | `EgressViolation` |
| The sanctioned path via a permitted provider | reaches the implementation |

**Now the limits, stated plainly rather than left for someone to discover.** This is a closed
*public API*, not a sandbox. Python cannot give more than that in-process, and the following remain
possible for someone who decides to do them:

- calling `provider._process(...)` directly — a named private method;
- `object.__setattr__` or `Released.__new__` trickery to forge a clearance;
- monkeypatching the policy, the guard, or the provider's `locality` attribute;
- writing an entirely new HTTP client that ignores the adapter layer.

So the honest classification of what we have:

| Mechanism | Strength |
|---|---|
| `Released` + closed `submit` | **Runtime prevention** of ordinary and accidental misuse |
| `Classified[T]` + mypy | Type contract; catches unclassified call sites in CI |
| `unwrap_unchecked`, private `_process` | Convention, backed by a CI grep and review |
| **No credentials, no network egress** | **The only real guarantee** |

The last row is the important one and it is not a code property. A deployment that must hold
confidential documentation should have no cloud API keys configured and no outbound network route
to them. Then a bypass fails at the socket, not at a policy check. Everything above is defence in
depth that makes the accidental case impossible and the deliberate case conspicuous; it does not
replace not having the credentials. This is now a line in the deployment checklist rather than an
implicit assumption.

### 8.1.3 Egress channels that are *not* AI providers

The review asked for three boundary decisions to be explicit rather than implied. Each is decided
here.

**A. Document processing / parsing — inside the boundary.** Today `pypdfium2` and `pdfplumber` run
in-process, so parsing is not an egress channel. If a cloud parsing, layout-analysis or
table-extraction service is ever introduced, it receives the whole document and is therefore a
stronger egress channel than any of the current ones. `Capability.DOCUMENT_PROCESSING` is
**reserved in the enum now**, so such a provider cannot be added without declaring a locality and
falling under the policy. No cloud parser is planned.

**B. Storage — inside the boundary, and currently the largest gap.** A confidential PDF written to
an S3 bucket has left the machine just as surely as one sent to an embedding API, and the fact that
no model saw it is irrelevant. `StorageProvider` therefore declares a locality like any other sink:
`local_fs` is `LOCAL`, `s3` is `CLOUD`. A deployment holding confidential documents with
`STORAGE_BACKEND=s3` is a misconfiguration the policy should refuse, and the same applies to
generated thumbnails and page images, which are derived content with the same classification as
their source. S3 is not blocked as a technology — a bucket under your own control with your own
keys may be entirely acceptable — but the decision must be made deliberately per classification,
which is what putting it in the matrix achieves.

**C. Logging, tracing, telemetry — inside the boundary, by exclusion.** The rule is that document
content never enters logs at all, so the question of whether the log sink is cloud-hosted does not
arise. Concretely: the audit record emitted by `EgressGuard.release` carries provider, locality,
capability and classification, and never the payload. Extracted text, OCR output, prompts,
retrieved passages, image descriptions and answer text are all forbidden in log records, traces and
error reports. Document titles and filenames are treated as content, because a filename like
`ADL-incident-2026-03-recovery-procedure.pdf` is itself disclosure. Chunk and document **IDs** are
permitted and are what makes debugging possible (§35). A test asserts the audit record contains no
payload; the harder cases — exception messages that interpolate content, a tracing library capturing
function arguments — are a STEP 3 concern and are listed there.

### 8.1.4 What stops a *future* content sink escaping the policy

The review's closing question, answered case by case. The instruction was to demonstrate what the
code already guarantees before changing anything, so: here is what it guaranteed, which was less
than the previous revision implied.

**What was actually true before this revision: nothing forced any of them.** Reserving
`Capability.STORAGE` in an enum is a signpost, not a mechanism. And the audit found an active
hazard rather than a merely missing one — `app/adapters/ports.py` declared `StorageProvider`,
`DocumentProcessor` and `EmbeddingProvider` protocols taking raw bytes and strings, unreferenced by
anything, in the file a developer would naturally implement against. That file is now deleted
(§2.3); its existence was the "second forgotten egress mechanism" this question was looking for.

**The mechanism now.** `tests/unit/test_adapter_inventory.py` walks `app/adapters/` and fails CI
when any class there is not a `Provider` subclass, unless it is listed in `EXEMPT` with a written
reason. Two further inventory tests assert that every provider declares a `Capability` and a
`Locality`, and that no provider exposes a public method other than `submit` — the latter closing
the specific shape of the original bypass, where a public method took a bare value.

Verified by writing each of the review's three components the natural way and running CI:

| Future component, written without the guard | Result |
|---|---|
| `S3Storage.put(key, pdf_bytes)` | **CI fails** — not a `Provider` |
| `CloudPdfParser.process(pdf_bytes)` | **CI fails** — not a `Provider` |
| A `Provider` with an extra public `summarise(text)` | **CI fails** — second entry point |

**Telemetry is the honest exception, and the answer is no.** `logging` is a process-global
facility; any line of code anywhere can call `logger.info(chunk_text)` and no architecture in
Python can prevent it. There is no mechanism here and it would be dishonest to imply one. What
exists is the exclusion rule in §8.1.3 C, a test asserting the audit record carries no payload, and
review. If stronger assurance is wanted, it has to come from outside the process — a log pipeline
that redacts, or no cloud log sink at all — and that is an infrastructure decision, not a code one.

So the accurate summary, in the review's own three categories: adapters are **prevented in
runtime** from being reached without a clearance, and **prevented in CI** from existing outside the
policy; telemetry is **convention only**. Neither is a sandbox, and §8.1.2's limits still apply to
both.

### 8.1.5 The boundary, in four honest categories

The fourth review asked whether the inventory test made the rule structurally
unavoidable, or merely recognised the files it already knew about. It was the latter, and the
review's instinct was right: **`app/adapters/` was becoming the new `ports.py`** — a boundary that
holds only while every future developer remembers where things go. Each of these passed CI
untouched:

```
app/services/fake_cloud.py                CloudTranslator.translate(text) → httpx.post
app/document_processing/cloud_parser.py   parse_pdf(pdf_bytes)            → httpx.post
app/services/exfil.py                     send_to_external_service(...)   → httpx.post
```

Naming and inheritance cannot catch these, because the author of such a module is exactly the
person who never heard of `Provider`. What the three share is not a convention but a *capability*:
sending content anywhere requires a network client. So the rule became structural —

> Only the adapter layer may import a network client, and only inside a module defining a
> `Provider`.

Checked by reading imports, so it applies equally to a class, a function, a coroutine or a
module-level statement. All three examples now fail CI. A companion test fails on any module in
`app/` that nothing imports, which is what would have caught `ports.py` on the day it was written.

**The four categories, stated so nobody has to infer them:**

| Layer | Strength | What it actually does |
|---|---|---|
| `Provider` + `EgressGuard` + `Released` | **Runtime prevention** | Content cannot reach a provider's public API without a policy decision for that specific provider |
| Adapter inventory + network-import boundary | **CI prevention** | A second family of adapters, or a network client anywhere else, fails the build |
| Private `_process`, `unwrap_unchecked`, orphan check | **Convention** | Backed by greps and review; a deliberate act, not an accident |
| Arbitrary in-process code, logging, telemetry | **Not controlled** | Python is not a sandbox; `logger.info(chunk_text)` cannot be prevented from inside the process |

Known gaps in the CI layer, listed rather than left to be discovered: a shell-out to `curl`, a
dynamic `importlib` call, a raw socket reached through a transitive dependency, or a network client
smuggled in via a library we already import. Each is a deliberate act. None is prevented here.

**The only categorical guarantee remains infrastructural**, as in §8.1.2: a deployment holding
confidential documentation with no cloud credentials and no outbound route fails at the socket, not
at a policy check. Everything above makes the accidental case impossible and the deliberate case
conspicuous. It does not replace not having the keys.

#### Property 6 — the ingestion boundary

The review's requirement is right and is not yet implemented, because ingestion does not exist yet.
Recording it as a binding constraint on STEP 3 rather than leaving it to be remembered:

**Classification must be established and validated before any operation capable of egress.** The
order in the pipeline is: register the document with its classification → validate that the
deployment can serve that classification → *only then* parse, OCR, describe images or embed. The
failure mode to avoid is upload → extract → OCR → cloud VLM → *then* check the policy, at which
point the disclosure has already happened. The upload endpoint rejects a document whose
classification no configured provider can serve, before the file is queued.

#### The consequence for Claude as the answering model

Extending the policy to `LLMProvider` has an uncomfortable and important result, which the review
anticipated: **the reference deployment cannot serve confidential documents.** Claude is a cloud
provider, so a deployment that answers with Claude may hold `internal` content at most.

This is not a defect in the design; it is the design surfacing a real constraint that would
otherwise have been discovered after indexing the corpus. Holding confidential documentation
requires local embeddings *and* a local answering model. The shipped defaults therefore declare
`handles_classification=internal`, while documents still default to `confidential` (§3.3) — so an
unclassified upload is refused until someone either classifies it down deliberately or configures
local providers. Both defaults fail closed, in opposite directions, and the tension between them
is the point.

**Vision is part of this.** Describing a screenshot from a confidential PDF via a cloud vision
model discloses that page just as surely as embedding its text. Under the matrix, cloud vision is
blocked for confidential documents; the practical effect is that such documents get no VLM image
descriptions unless a local vision model is configured, and image retrieval for them falls back to
caption and surrounding text (§7.2).

The same matrix governs `LLMProvider`, because answering sends retrieved passages to Anthropic. A
`strict_local` deployment therefore also requires a local answering model — the policy makes that
dependency explicit instead of letting a confidential corpus leak at answer time after being
carefully embedded locally. **This is a consequence worth stating plainly: local embeddings alone
do not give you a private system.**

MVP scope: the enum, the matrix, the router and the four enforcement points. Per-document
classification UI and bulk reclassification are phase 2.

#### Switching to local embeddings later

1. Stand up `bge-m3` (CPU viable at ingest volumes; GPU for large backfills).
2. Set `EMBEDDING_PROVIDER=local` and register the model (§3.6 step 1).
3. Run the backfill job, then the retrieval eval suite — quality change is measured, not assumed.
4. Flip `is_active`. No re-ingestion, no re-parsing, no citation invalidation.

### 8.2 Mechanics

Batch (64–128 chunks per call), retry with backoff, persist incrementally so a failure resumes
rather than restarts. Queries and documents use the model's respective instruction prefixes where
it defines them. The provider's declared `dimensions` is asserted against the registered model's
table at startup; a mismatch is a startup failure, not a runtime surprise.

---

## 9. Hybrid retrieval [§11, §12]

### 9.1 The stopword problem — the most important detail in this document

The brief's own example, **`PNL NOT PROCESSED`**, breaks under the obvious implementation.

**Verified on PostgreSQL 16.13, not asserted from memory.** The result is worse than I described in
revision 1:

```
=# SELECT to_tsvector('english','PNL NOT PROCESSED');
 'pnl':1 'process':3          -- NOT discarded as a stopword, PROCESSED stemmed

=# SELECT to_tsvector('simple','PNL NOT PROCESSED');
 'not':2 'pnl':1 'processed':3

-- Does a search for "NOT PROCESSED" correctly separate the two states?
                                      english   simple
 "PNL status is NOT PROCESSED" matches    t        t     ← wanted
 "PNL status is PROCESSED"     matches    t        f     ← english is WRONG
```

Under the `english` configuration, a page stating that PNL **is** processed is returned as a match
for `NOT PROCESSED`. This is not a recall problem, which was my original framing — it is a
**semantic inversion**: the system retrieves evidence asserting the opposite of what was asked, and
then answers from it, with a correct-looking citation to a real page.

For an operational documentation system this is the most dangerous failure mode available. It is
not detectable by the LLM (the evidence is genuine, it simply says the opposite), not detectable by
citation validation (the page and quote are real), and not detectable by a demo (it looks like a
confident, sourced answer). Only the retrieval layer can prevent it.

Two further findings from the same session:

```
-- pg_trgm rescues OCR damage that exact phrase matching loses entirely
 'PNL NOT PROCESSEO'   similarity 0.79   exact-phrase match: f
 'PN1 NOT PROCESSED'   similarity 0.79   exact-phrase match: f
 'PNL N0T PROCESSED'   similarity 0.70   exact-phrase match: f

-- hyphenated codes fragment into multiple tokens
=# SELECT to_tsvector('simple','error E-1052');
 'e':2 '-1052':3 'error':1      -- E-1052 is not one token
```

The first justifies leg 3 quantitatively rather than by intuition.

The second needs a correction to what I wrote before testing it. I claimed fragmentation broke
exact code matching and that only trigrams could rescue it. **That was wrong**, and the test
disproved it: `phraseto_tsquery` fragments the *query* identically and preserves adjacency
(`'e' <-> '-1052'`), so `E-1052` matches correctly and does **not** match `E-1053`.

The real finding is narrower but still operationally important: correctness here depends on using
`phraseto_tsquery`, which preserves token adjacency, and **not** `plainto_tsquery`, which reduces
to an AND of fragments and can match a page where `e` and `-1052` appear far apart in unrelated
codes. So the rule for leg 2 is: **technical identifiers are always phrase queries, never bag-of-
words queries.** That is now enforced in the retrieval code rather than left to whoever writes the
next query builder.

**Design consequence: three retrieval legs, not two.**

1. **Semantic** — pgvector cosine over the active model's `chunk_emb_*` table (§3.6).
2. **Lexical** — Postgres FTS using the **`simple`** configuration (no stemming, no stopword
   removal) over a normalised copy of the text, preserving `NOT`, codes and acronyms exactly.
   Phrase queries use `phraseto_tsquery('simple', ...)`.
3. **Fuzzy exact** — `pg_trgm` similarity, which catches OCR-damaged and near-miss technical strings
   that leg 2 misses by one character.

A quoted phrase in the user's query (`"PNL NOT PROCESSED"`) or a detected all-caps technical token
escalates leg 2 to a strict phrase requirement and boosts its weight. An unstemmed `simple` index
costs some recall on ordinary prose, which legs 1 and 3 recover; the reverse trade — losing exact
technical strings — is not recoverable.

**Regression test, not just a design note.** Because this failure is invisible at every later layer,
the `english`-vs-`simple` inversion above becomes a permanent test in the suite from STEP 2: a
fixture containing both `PNL NOT PROCESSED` and `PNL PROCESSED`, asserting that a search for the
negative state does **not** return the positive one. If someone later "optimises" the index to
`english` for better prose recall, CI fails with an explanation rather than the system quietly
starting to invert operational states.

### 9.2 Fusion

**Reciprocal Rank Fusion** over the three legs, with per-leg weights in configuration. RRF needs no
score calibration between legs (cosine, `ts_rank` and trigram similarity are not comparable
quantities), is robust, and is trivially explainable in the retrieval diagnostics view [§39].

### 9.3 Version and authority resolution [§9, §45]

Applied **before** ranking, not after:

- Query mentions a release (`"in 7.3"`, `"release 7.4"`) → restrict to that release.
- Query is comparative (`"what changed between"`) → retrieve both releases, tag evidence with its
  release, and hand the LLM an explicitly grouped comparison context [§10].
- Otherwise → prefer the current release; retrieve older releases only as a fallback when the
  current release yields nothing above threshold, and mark such evidence as non-current so the
  answer can say so.

**Permissions are applied as a pre-filter in the SQL, never as a post-filter after ranking.** This
matters for two reasons: post-filtering yields a short or empty top-k for restricted users (a
correctness bug), and the difference between "no results" and "filtered results" is an information
side channel that reveals the existence of documents a user may not know about [§30].

### 9.4 Reranking [§13]

A **cross-encoder reranker** over the top ~50 fused candidates, reducing to ~8–12. This is the
highest-quality-per-unit-effort component in the whole retrieval stack: bi-encoder embeddings are
optimised for recall, and a cross-encoder that sees query and passage together is substantially
better at precision — which is what determines whether the cited page is the right page.

Default: a local cross-encoder (`bge-reranker-v2-m3`), consistent with the embedding privacy stance
and cheap enough to run on CPU at this candidate count. An LLM-as-reranker implementation sits behind
the same port for comparison via the eval suite.

Post-rerank, a **document-diversity pass** caps chunks per document version so one verbose manual
cannot crowd out the quick reference that answers the question better [§45].

---

## 10. Release comparison [§10]

Not in the MVP, but the schema must not preclude it. It doesn't:

- `releases.sort_key` gives a total order;
- `documents.id` is stable across releases, so the same manual is joinable release-to-release;
- `sections.path` gives a structural alignment key ("ADL > Check-in > Procedure" in 7.3 vs 7.4);
- `images.phash` gives cheap "this screenshot changed" detection without image comparison at
  query time.

The phase-3 implementation aligns sections by `path` (with fuzzy title matching for renames), diffs
aligned text, and uses phash distance for changed screenshots — then has the LLM summarise the diff
with both sides cited. Release-notes documents (`document_type = 'release_notes'`) are retrieved
preferentially for such queries.

---

## 11. Document authority model [§45]

The brief is right to say the proposed ranking should not be assumed. My position:
**authority is two independent axes, and collapsing them into one list is the error.**

- **Recency axis** — `releases.sort_key`, and whether a version is current, superseded or EOL.
- **Type axis** — `documents.authority_tier`, a per-document-type integer in configuration.

A *current* quick reference and an *older* full manual are not comparable on a single list: which
wins depends on the question. So the policy is a small configurable weighting applied at rerank
time, with a default of:

```yaml
authority:
  release_weight: 0.6        # recency dominates by default
  type_weight: 0.4
  tiers:                     # lower = more authoritative
    release_notes: 1         # for release-scoped questions
    manual: 1
    operational_procedure: 1
    quick_reference: 2
    user_guide: 2
    training: 3
    other: 4
  never_mix_releases_silently: true
```

The one rule that is **not** configurable is the invariant: when two retrieved sources from
different releases materially disagree, the system surfaces the conflict and cites both [§15]. It
does not resolve it silently, whatever the weights say. Conflict detection is implemented as an
explicit check — when the final evidence set contains chunks from two releases within the same
document lineage and the reranker scores both highly, the prompt receives an explicit
`CONFLICT_CANDIDATE` marker and the answer template requires it to be addressed.

The tier table is a starting point that **should be revised once I can see your actual corpus** —
particularly whether "operational procedure" outranks "manual" in your organisation, which is a
business fact I cannot infer.

---

## 12. LLM architecture and hallucination control [§14]

**Model: `claude-opus-5`** for answering (1M context, $5/$25 per MTok). `claude-haiku-4-5` for the
cheap, high-volume ingest-time jobs (image descriptions, optional chunk contextualisation) where
quality requirements are lower and volume is thousands of calls.

### 12.1 Grounding is enforced in code

This is where I most strongly extend the brief. §14 lists prompt instructions; instructions alone
cannot deliver the guarantee §49-O demands. Four mechanisms, of which only the first is a prompt:

1. **Prompt constraints.** Evidence is supplied as numbered blocks with explicit
   `[E3] doc=… release=7.4 page=42 section=…`. The model is instructed to cite block IDs and to
   refuse when evidence is insufficient.
2. **A retrieval confidence gate, before the LLM is called.** If the best reranked score is below
   an absolute threshold, or too few passages clear it, the system returns the §14 refusal
   **without calling the model at all**. A model given weak evidence produces a plausible answer
   from it; the fix is not to ask it not to.
3. **Citation validation, after the response.** The model returns structured output where every
   step and claim carries evidence IDs. Any ID not in the supplied set is a fabrication — the
   response is rejected and retried once, then downgraded to refusal. This closes the
   "cites a page that doesn't exist" failure directly.
4. **Quote verification.** Each citation includes a verbatim `quoted_text` span, checked by
   normalised substring match against the actual chunk text. A quote that isn't in the evidence is
   a hard failure, not a warning. This is the check that makes §4's chain auditable rather than
   merely asserted.

Failing (3) or (4) is logged as a hallucination event and is a first-class metric [§33].

### 12.2 Structured output [§43]

The answer is generated as a schema-constrained object via `output_config.format`, not parsed out of
prose:

```jsonc
{
  "sufficient_evidence": true,
  "summary": "…",
  "steps": [{"n": 1, "text": "…", "evidence": ["E3"]}],
  "warnings": [{"text": "…", "evidence": ["E7"]}],
  "conflict": null,          // or {releases:["7.3","7.4"], explanation, evidence:[…]}
  "images": ["IMG12"],
  "citations": [{"id":"E3","quote":"…"}],
  "answer_confidence": "high"
}
```

Chat, PDF and email are three renderers over this one object [§43] — which is what makes §25's
"do not screenshot the chat UI" structurally impossible to violate.

### 12.3 Conversation context [§31]

Prior turns are used **only** for query rewriting ("does the latest release change *this*?" → a
standalone query). The rewritten query goes through full retrieval, and the answering prompt
receives evidence plus the rewritten question — never prior answer text as if it were evidence.
This enforces §31's "conversation context must never override documentation evidence" by
construction: previous answers are not in the grounding context at all.

### 12.4 Prompt caching

System prompt and answer schema are stable and cached; evidence and question go after the last
cache breakpoint. This is a straightforward cost reduction on a workload where the static prefix is
a meaningful fraction of input tokens.

---

## 13. Citation system, viewer, and export

### 13.1 Citations [§3, §27]

Each citation renders as document title · type · release · page · section, with **Open document**
and **View evidence**. `citations` rows persist the full chain including the quoted span, so an
answer from six months ago still resolves.

### 13.2 PDF viewer [§23]

React + **pdf.js** (`react-pdf`), two-panel: answer left, viewer right. Clicking a citation jumps to
`cite_page`. Highlighting uses the stored `char_start`/`char_end` against the pdf.js text layer,
with bbox-based highlighting for image evidence. If text-layer alignment fails (common on OCR
pages), the viewer degrades to page-level navigation rather than highlighting the wrong span —
a wrong highlight is worse than none.

PDFs are streamed through an authorising endpoint with HTTP range support, never a public URL [§30].

### 13.3 PDF export [§25]

`StructuredAnswer` → Jinja HTML template → **WeasyPrint** → PDF. Recommended over headless Chrome:
no browser to install or sandbox, deterministic output, far smaller footprint, and entirely adequate
for a print-oriented document layout. Images are embedded from storage at full resolution — the §50
check "can the PDF export lose images?" is covered by an export test asserting that every image in
the answer object appears in the output.

### 13.4 Email output [§26]

Same object, a different renderer producing subject + plain-text and HTML bodies. Tone is handled by
the template and a constrained rewrite, with a lint pass rejecting "As an AI", "Based on my
analysis" and similar. Crucially, **the email renderer emits only content already present in the
validated answer object** — it cannot introduce unsupported claims, which answers the §50 question
"can the email output contain unsupported claims?" structurally.

---

## 14. Security [§30]

- **AuthN**: OIDC/SSO where available, local sessions otherwise; short-lived tokens.
- **AuthZ**: roles (`reader`/`curator`/`admin`) plus group-based `document_acl`. Enforced at the
  *query* layer (§9.3), not at the response layer.
- **No IDOR**: every document, page, image and export endpoint re-checks ACL on the object. Internal
  IDs are never sufficient [§30].
- **Secrets**: API keys from environment/secret manager, never in the database or logs. The key is
  read once at startup into the provider adapter.
- **Logging**: structured logs record chunk *IDs*, scores and counts — never chunk text, query text
  by default, or OCR output [§35]. Query text logging is opt-in per deployment and flagged as
  sensitive.
- **Audit**: every ask, document open, download and upload recorded [§30].
- **Uploads**: MIME sniffing, size caps, page-count caps; PDFs are parsed in the worker process,
  never the API process, with resource limits — malformed PDFs are a real crash/DoS vector.

---

## 15. API design [§42]

```
POST   /api/v1/documents                 multipart upload → 202 {version_id, job_id}
GET    /api/v1/documents                 filters: type, release, status, q
GET    /api/v1/documents/{id}
GET    /api/v1/document-versions/{id}
GET    /api/v1/document-versions/{id}/file          range-capable stream
GET    /api/v1/document-versions/{id}/pages/{n}
GET    /api/v1/images/{id}                          + ?thumb=1
GET    /api/v1/jobs/{id}                            ingestion status
GET    /api/v1/releases

POST   /api/v1/search                    {query, filters} → passages w/ doc·release·page
POST   /api/v1/conversations
POST   /api/v1/conversations/{id}/messages          → StructuredAnswer (SSE streaming)
GET    /api/v1/conversations/{id}
GET    /api/v1/messages/{id}/evidence               full chain for "View evidence"
POST   /api/v1/messages/{id}/export/pdf
POST   /api/v1/messages/{id}/export/email
POST   /api/v1/messages/{id}/feedback
```

OpenAPI is generated by FastAPI from Pydantic models; `StructuredAnswer` is a Pydantic model shared
by the API schema, the LLM output schema and the renderers — one definition, three uses.

---

## 16. Frontend [§22]

**React + Vite + TypeScript + TanStack Query**, not Next.js. This is an authenticated internal tool
with no SEO requirement and no meaningful server-rendering benefit; Next.js would add a Node runtime,
a second deployable and SSR/auth complexity for nothing. Components: chat, sources rail, pdf.js
viewer, document management table with live job status, direct search.

Design posture per §22 — dense, information-first, keyboard-navigable; evidence always visible but
secondary to the answer [§27].

---

## 17. Testing, evaluation, observability

### 17.1 Evaluation [§33]

Agreed that it is mandatory. One sequencing correction: **a golden dataset cannot be authored before
real documents exist.** Attempting it produces test cases written against imagined content, which is
worse than none. Therefore:

- **Tier 1 — retrieval eval (no LLM, deterministic, cheap).** Per case: question → expected
  document, release, page(s). Metrics: recall@k, MRR, page accuracy, release accuracy. This runs in
  CI on every retrieval change and catches the majority of regressions at near-zero cost.
- **Tier 2 — answer eval (LLM-judged, run before releases).** Faithfulness (every claim supported by
  cited evidence), completeness, and **refusal correctness on a deliberate set of unanswerable
  questions** — the metric that proves §49-O, and the one most teams forget to measure.
- **Tier 3 — adversarial set** derived directly from §50: conflicting releases, OCR-damaged exact
  strings, near-duplicate screenshots, superseded procedures.

The eval harness ships in the MVP; the dataset is populated during STEP 4 from your real corpus.
**I need ~30–50 real questions with known answers from you** to seed it — this is the second input I
need, and it is the difference between a measurable system and an anecdotal one.

### 17.2 Regression testing [§34]

Every eval run writes a scored record keyed by a config hash (chunker, embedding model, prompt,
retrieval weights, reranker, LLM). CI fails on a drop beyond tolerance in recall@10, page accuracy
or faithfulness. Unit tests cover chunk-boundary invariants, citation-chain integrity, ACL
filtering, and idempotent re-upload.

### 17.3 Observability [§35]

Structured JSON logs plus OpenTelemetry spans across the ask path (rewrite → retrieve → rerank →
LLM → validate). Metrics: ingestion duration by stage, OCR page rate, extraction failures, retrieval
and LLM latency percentiles, token usage and cost per answer, refusal rate, hallucination-check
failures, feedback ratios. A **retrieval diagnostics view** [§39] shows, per answer, every candidate
with its three leg scores, fused rank, rerank score and inclusion decision — this is what makes
retrieval quality debuggable instead of mysterious.

---

## 18. Deployment and cost

**Deployment.** Docker Compose for development and small production: `api`, `worker`, `postgres`,
`frontend` (static build behind the API's reverse proxy). Alembic migrations run as a startup job.
This runs entirely on-premises if the documentation's confidentiality requires it — with a
self-hosted embedding model and reranker, the only egress is the Claude API call carrying the
retrieved passages, which can itself be reviewed or replaced via `LLMProvider`.

**Cost.** Indicative, at first-party API rates (Opus 5: $5/MTok in, $25/MTok out):

| Item | Estimate |
|---|---|
| Answer (≈12 passages ≈ 9K input, ≈700 output) | ≈ $0.06, less with caching |
| Ingest image description (Haiku 4.5) | ≈ $0.001 per image |
| Embeddings (self-hosted) | infra only |
| 500 documents × 200 pages, one-off ingest | dominated by OCR CPU time, not API spend |
| 200 answers/day | ≈ $12/day ≈ $350/month |

The dominant *recurring* cost is answering; the dominant *one-off* cost is ingestion CPU. If answer
volume grows, the first lever is prompt caching and evidence-set size, not a model downgrade.

---

## 19. Main risks

| Risk | Impact | Mitigation |
|---|---|---|
| **`english` FTS inverts operational states** | Retrieves evidence asserting the *opposite*; undetectable downstream | `simple` config + trigram leg; **verified on PG 16.13** and locked by a CI regression test (§9.1) |
| Hyphenated codes (`E-1052`) fragment even under `simple` | Exact-code search misses | Trigram leg covers it; verified (§9.1) |
| Confidential document reaches a cloud provider by default | Irreversible disclosure | Classification policy, default-deny, four enforcement points (§8.1.1) |
| Corpus disclosed to external providers | Disclosure cannot be undone by re-embedding | Provider is config, not code; gate before ingesting the *production* corpus (§8.1) |
| Poor PDF structure (no outline, inconsistent headings) | Weak sections → weak chunks → weak citations | Font-clustering fallback; needs real documents early |
| HNSW recall loss under release/ACL filters | Silently wrong or empty results | `iterative_scan`, `ef_search` floor, recall test (§3.4) |
| OCR corrupts exact strings | Wrong or missed answers on scanned docs | Per-page OCR, confidence propagation, trigram rescue, UI marker (§5) |
| Golden dataset never materialises | No way to detect regression; §33/§34 unmet | Tier-1 eval in CI from day one; request 30–50 real questions now |
| Wrong-release answers | Directly violates §9/§49-N | Pre-filter by release, explicit conflict detection, release accuracy as a CI metric |
| Weaker structure extraction from permissive libraries | Poor sections → poor citations | Measured on the real corpus at STEP 3; Docling is the escalation path (§4.1, §21) |
| Ordering across changed release numbering schemes | Wrong "current release" | `sort_override`, curator-confirmed (§3.1.1) |
| Scope breadth (51 sections) before core RAG is reliable | Everything half-built | Phase discipline per §37–39; the brief already says this and it is correct |

---

## 20. Points of disagreement with the specification

Consolidated, as §46 requires. Each is argued at the referenced section.

1. **§16 — `sections.page_id` and `chunks.page_id` are modelling errors.** Sections and chunks span
   pages. Use page ranges plus an explicit `cite_page`. (§3.1a/b)
2. **§16 — `release` as a plain string cannot be ordered** (`7.10 < 7.9`), yet §9/§15/§45 all depend
   on recency ordering. Releases must be a table with an explicit `sort_key`. (§3.1c)
3. **§11 — the flagship example does not work under default full-text search.**
   `to_tsvector('english', …)` deletes `NOT` as a stopword. The `simple` configuration plus a
   trigram leg is required. This is the highest-priority correction in the document. (§9.1)
4. **§14 — hallucination control cannot be prompt-only.** Add a pre-LLM confidence gate, citation-ID
   validation and verbatim quote verification. Instructions are not controls. (§12.1)
5. **§12 — a separate "evidence validation" LLM stage is not worth its latency and cost.** Validation
   should be deterministic (IDs, quotes, thresholds) around a single generation call, not a second
   model round-trip. (§12.1)
6. **§7 — the OCR decision belongs at page level, not document level**, and OCR text must be
   explicitly lower-trust for exact-phrase matching. (§5)
7. **§5/§6 — images need a generated description at ingest**, or "show the relevant screenshot"
   degrades into "show a screenshot from roughly the right page". (§7.2)
8. **§21 — "Claude as the primary LLM" leaves embeddings unspecified.** Anthropic has no embeddings
   API, so a second provider is mandatory, and sending a confidential corpus to it is a governance
   decision rather than an implementation detail. Resolved: hosted initially, local implemented
   against the same port, gated before the production corpus. (§8.1)
9. **§17 — object storage is not needed in the MVP.** Local content-addressed storage behind
   `StorageProvider` is sufficient; standing up MinIO now contradicts §40. (§3.5)
10. **§18 — a broker-based queue (Celery/Redis) is not justified** at this volume. A Postgres
    `SKIP LOCKED` queue is simpler, transactional with the state it manages, and removes a
    dependency. (§4.1)
11. **§19 — checksum alone is not idempotency.** "Same bytes" and "new release of the same document"
    are different operations and must be distinguished explicitly, with human confirmation of
    document identity. (§4.3)
12. **§30 — permissions must pre-filter retrieval, not post-filter results.** Post-filtering is both
    a correctness bug and an information side channel. (§9.3)
13. **§33 — the golden dataset cannot precede the corpus.** Ship the harness first, tier the metrics,
    and populate from real documents in STEP 4. Also: measure *refusal correctness* explicitly —
    §49-O is a testable property and is usually untested. (§17.1)
14. **§45 — authority is two axes (recency, type), not one ranked list.** Collapsing them cannot
    express "current quick reference vs. older full manual". (§11)
15. **§22 — React + Vite, not Next.js.** No SEO or SSR requirement; Next.js adds a runtime and a
    deployable for no benefit here. (§16)

I agree with the rest, and in particular with the priority order in §2
(*accuracy > traceability > usability > performance > polish*), the §37–39 phasing, and §48's
insistence that a running application is not evidence of a working system.

---

## 21. Open architectural decisions

Every decision that is not yet final, what would settle it, and when it must be settled. The test
applied to each is not "does it work?" but "**is it the best option, and what does it cost us in
one to two years?**"

| # | Decision | Current position | Binds at | Reversal cost later |
|---|---|---|---|---|
| D1 | **Initial embedding provider** | `voyage-3` (hosted) | First ingestion of the *production* corpus | **Low technically** (§3.6 online migration); **nil — impossible — for disclosure already made** |
| D2 | **Local embedding option** | `bge-m3`, same port, same 1024 dims | Whenever policy requires it | Low — config flip plus backfill |
| D2b | **Local answering model** | None — `strict_local` deployments need one (§8.1.1) | Only if a no-egress posture is required | Medium — quality must be re-evaluated |
| D3 | **PDF processing library** | `pypdfium2` + `pdfplumber` (permissive) | STEP 3 | Low — `DocumentProcessor` port; re-ingestion required, no schema change |
| D4 | **PyMuPDF as an optional adapter** | Not a default dependency; available for AGPL-accepting or commercially licensed deployments | Only if extraction quality proves insufficient | Low |
| D5 | **Structure extraction escalation** | Docling (MIT) if heading/section detection is weak on the real corpus | STEP 3, decided by measurement | Medium — heavier deployment |
| D6 | **Storage** | Local content-addressed filesystem | When multi-node or durability requirements appear | Low — `StorageProvider` port; S3 adapter ≈80 lines + a copy job |
| D7 | **LLM provider** | Claude Opus 5 | STEP 6 | Low in code; answer quality must be re-evaluated against the golden dataset |
| D8 | **Reranker** | Local `bge-reranker-v2-m3` | STEP 4 | Low — `Reranker` port; LLM reranker comparable via the eval suite |
| D9 | **Release ordering scheme** | `integer[]` + curator-confirmed `sort_override` | First release registered | Low — data fix, not a deploy |
| D10 | **Authority model weights** | Draft defaults in §11 | Needs your corpus and business input | Low — configuration |
| D11 | **Job queue** | Postgres `SKIP LOCKED` | STEP 1 | Medium — a broker migration is real work, but only if volume justifies it |
| D12 | **Chunk contextualisation** | Deferred to phase 2, gated on eval | After the golden dataset exists | Low — re-chunk and re-embed |
| D13 | **Auth mechanism** | OIDC/SSO preferred, local fallback | STEP 11 | Medium — depends on your identity infrastructure |

**Two-year view on the ones that matter.** D1 is the only decision on this list whose cost is
asymmetric in time: every other row is a port swap or a configuration change, whereas disclosed
text stays disclosed. D3 and D6 were both chosen to keep optionality cheap rather than to be
optimal today — the permissive licence and the local filesystem each avoid a commitment we would
have to unwind under pressure. D11 is the one I would most expect to revisit, and the revisit is
bounded: the queue is small, isolated and behind the service layer.

**Nothing on this list blocks STEP 1**, which is deliberate — the skeleton is the part that is
identical under every option above.

---

## 22. Project structure [§41]

```
.
├── backend/
│   ├── app/
│   │   ├── api/v1/            # routers; HTTP only, no business logic
│   │   ├── services/          # use cases; owns transaction boundaries
│   │   │   ├── ingest/        # pipeline stages (§4)
│   │   │   ├── retrieval/     # hybrid search, fusion, rerank (§9)
│   │   │   ├── answering/     # grounding, validation, refusal (§12)
│   │   │   └── export/        # pdf, email renderers (§13)
│   │   ├── domain/            # entities, authority policy, version resolution
│   │   ├── adapters/
│   │   │   ├── llm/           # claude.py
│   │   │   ├── embeddings/    # voyage.py, local.py
│   │   │   ├── docproc/       # pdfium.py, plumber_tables.py, (pymupdf.py optional)
│   │   │   ├── ocr/           # tesseract.py
│   │   │   ├── rerank/        # cross_encoder.py
│   │   │   └── storage/       # local_fs.py, (s3.py later)
│   │   ├── db/                # SQLAlchemy models, repositories
│   │   ├── config.py          # pydantic-settings; every D-decision surfaces here
│   │   └── main.py
│   ├── worker/                # queue consumer process
│   ├── migrations/            # alembic
│   └── tests/
│       ├── unit/
│       ├── integration/       # testcontainers postgres
│       └── fixtures/          # sample PDFs
├── evaluation/
│   ├── datasets/              # golden dataset (§17.1)
│   ├── harness/               # tier 1/2/3 runners
│   └── reports/
├── frontend/
│   └── src/{features,components,api,routes}/
├── docs/
│   ├── ARCHITECTURE.md        # this document
│   ├── API.md                 # generated + prose
│   └── decisions/             # ADRs for anything that changes §21
├── docker-compose.yml
└── Makefile
```

Two conventions worth fixing now: `api/` may not import from `adapters/` (it goes through
`services/`), and `domain/` imports nothing from the outer layers. These are enforced by a lint
rule in CI rather than by good intentions.

---

## 23. Implementation roadmap

| Step | Deliverable | Exit criterion |
|---|---|---|
| **0** | *This document, reviewed* — D1/D3 resolved (§21) | Sign-off ✅ |
| **1** | Skeleton: FastAPI, Alembic, Docker Compose, CI, ports | `docker compose up` green, migrations apply |
| **2** | Schema + FTS/trigram verification on real Postgres | `PNL NOT PROCESSED` provably retrievable (§9.1) |
| **3** | Ingestion: extract → structure → chunk → embed → index | 3 real PDFs (text, screenshots, scanned) ingest to READY |
| **4** | Hybrid retrieval + reranking + tier-1 eval harness | Recall@10 and page accuracy measured, in CI |
| **5** | Grounded answering: structured output, gate, validators | Refusal correct on unanswerable set |
| **6** | Chat UI + sources + pdf.js viewer with page jump | §49 A→J end-to-end on real documents |
| **7** | Image retrieval + in-answer display | §49-K; no unrelated screenshots in adversarial set |
| **8** | PDF + email export | Images present in export; email lint clean |
| **9** | Version awareness, conflict surfacing, document management UI | §49-N; conflict cases cite both releases |
| **10** | Tier-2/3 evals, adversarial review per §50 | Every §50 question answered with evidence |
| **11** | Auth, ACL, audit, observability, hardening | Security review passed |

Steps 1–5 constitute the §37 MVP. Steps 6–9 map to §38, and the remainder to §39.

---

## 24. STEP 1 — exact plan

Scope: **project skeleton only.** No ingestion, no retrieval, no LLM call, no UI beyond a
placeholder. The purpose is a repository where every subsequent step has somewhere to land and a
test harness that can prove it landed.

**Deliverables**

1. `docker-compose.yml` — `postgres` (16 + pgvector + pg_trgm), `api`, `worker`. No Redis.
2. Backend package per §22, with `pyproject.toml` (uv), Python 3.12.
3. `config.py` using pydantic-settings, with every §21 decision expressed as a setting
   (`EMBEDDING_PROVIDER`, `PDF_PROCESSOR`, `STORAGE_BACKEND`, `LLM_PROVIDER`, `RERANKER`).
   No provider is constructed at import time; all resolve through a factory.
4. **The ports from §2.3 defined, with exactly one stub implementation each** that raises
   `NotImplementedError`. This fixes the interfaces before anything depends on them.
4b. **`EmbeddingRouter` and the classification policy matrix (§8.1.1)**, with startup validation
   and unit tests — including a test asserting that a `confidential` document cannot be routed to
   a cloud provider under any configuration. The guard exists before the thing it guards.
5. Alembic initialised; one migration creating the extensions only. **Not the full schema** —
   that is STEP 2, after the FTS behaviour is verified against a real Postgres.
6. `GET /health` returning database and extension status, and `GET /api/v1/releases` returning
   an empty list — one trivially real path end-to-end.
7. Frontend scaffold: Vite + React + TS, one page calling `/health`. Nothing more.
8. Test harness: pytest, `testcontainers` for Postgres, one integration test asserting the
   extensions load and a migration applies to an empty database.
9. CI (GitHub Actions): lint (ruff), format check, type check (mypy), tests, and the
   import-boundary rule from §22.
10. `Makefile`: `up`, `test`, `lint`, `migrate`, `fmt`.

**Exit criteria**

- `docker compose up` gives a healthy API against a real Postgres with both extensions present.
- `make test` passes from clean checkout on CI.
- Switching `EMBEDDING_PROVIDER` between `voyage` and `local` changes which stub is constructed —
  proving the port wiring works before either is implemented.
- `EMBEDDING_POLICY_MODE=strict_local` with only a cloud provider configured **fails startup**.

**Explicitly not in STEP 1:** the database schema, PDF parsing, any external API call, any
dependency not required by the above. Dependencies are added at the step that first needs them.

**Estimated size:** ~600–900 lines, mostly configuration and scaffolding. This is deliberately
small: it is the step that is cheapest to get wrong and most expensive to have gotten wrong.

---

## 25. What I still need from you

**Nothing blocks STEP 1 or STEP 2.** These are needed for STEP 3 onwards to be meaningful rather
than merely green:

1. **Representative documents** (§48) — one text PDF, one screenshot-heavy, one with tables, one
   scanned, and the **same manual in two releases**. The last is the most valuable single input in
   this list: it exercises §9, §15 and §45 simultaneously, and nothing else can substitute for it.
2. **30–50 real questions with known answers** (§33), to seed the golden dataset. Needed before
   STEP 4's exit criterion means anything.
3. **Confirmation of the authority model** (§11, D10) — in particular whether operational
   procedures outrank manuals in your organisation. A business fact I cannot infer.
4. **Production-corpus embedding gate** (D1) — before real confidential documents are ingested,
   not before code is written. Flagged in the deployment checklist.
5. **Identity infrastructure** (D13) — whether an OIDC provider is available, needed at STEP 11.
