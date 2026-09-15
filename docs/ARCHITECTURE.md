# Documentation Intelligence AI — Technical Design

Status: **proposal, awaiting review.** No implementation has started (per §47 STEP 1–2 of the
brief). This document is the artifact to review before any code is written.

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
PyMuPDF / Tesseract (fallback) / Claude Opus 5 for answering / React + Vite + pdf.js.
No Redis, no Celery, no separate vector DB, no object store in the MVP. Rationale throughout.

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

```python
class LLMProvider(Protocol):
    async def answer(self, prompt: GroundedPrompt) -> StructuredAnswer: ...

class EmbeddingProvider(Protocol):
    dimensions: int
    model_id: str
    async def embed_documents(self, texts: list[str]) -> list[Vector]: ...
    async def embed_query(self, text: str) -> Vector: ...

class Reranker(Protocol):
    async def rerank(self, query: str, candidates: list[Candidate]) -> list[Scored]: ...

class DocumentProcessor(Protocol):        # one per source format
    def supports(self, mime: str) -> bool
    def process(self, path: Path) -> ExtractedDocument: ...

class OcrEngine(Protocol):
    def ocr_page(self, image: PageImage) -> OcrResult: ...   # text + per-word confidence

class StorageProvider(Protocol):
    def put(self, key: str, data: BinaryIO) -> StorageRef: ...
    def open(self, ref: StorageRef) -> BinaryIO: ...
    def signed_url(self, ref: StorageRef, ttl: timedelta) -> str: ...

class AnswerRenderer(Protocol):           # PDF, email, future formats
    def render(self, answer: StructuredAnswer) -> bytes: ...
```

`EmbeddingProvider.model_id` and `.dimensions` are part of the interface deliberately: embeddings
are only comparable within a single model, so the model identity must be persisted alongside every
vector (§3.6).

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
explicit and editable, so releases become a **first-class table with an integer `sort_key`**.
This also gives release-level metadata (GA date, supported/EOL status) a home and makes §10
(release comparison) expressible as a join rather than string parsing.

I also add `embedding_model` to `chunks` (§3.6), `permissions` primitives (§14), and an
`image_phash` for cross-release screenshot diffing (§10).

### 3.2 Core DDL (proposal)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── Product releases: ordered, first-class ────────────────────────────────
CREATE TABLE releases (
    id              bigserial PRIMARY KEY,
    label           text NOT NULL UNIQUE,        -- '7.4'
    sort_key        integer NOT NULL UNIQUE,     -- 7040  (assigned, not parsed)
    ga_date         date,
    eol_date        date,
    is_current      boolean NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now()
);
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
    embedding_model     text NOT NULL,
    embedding           vector(1024),
    tsv                 tsvector,                  -- see §9.1 for the configuration
    UNIQUE (document_version_id, chunk_index)
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
    phash               bit(64),                   -- §10 cross-release comparison
    embedding_model     text,
    embedding           vector(1024)               -- of caption+description+surrounding
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
CREATE INDEX chunks_embed_idx    ON chunks USING hnsw (embedding vector_cosine_ops)
                                 WITH (m = 16, ef_construction = 64);
CREATE INDEX chunks_dv_idx       ON chunks (document_version_id);
CREATE INDEX images_embed_idx    ON images USING hnsw (embedding vector_cosine_ops);
CREATE INDEX dv_doc_release_idx  ON document_versions (document_id, release_id);
CREATE INDEX jobs_claim_idx      ON ingestion_jobs (state, id) WHERE state <> 'ready';
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

### 3.6 Embedding model identity

`chunks.embedding_model` exists because vectors from different models are not comparable. When the
embedding model changes, the correct behaviour is to re-embed the corpus into a new column or table
and cut over atomically — not to mix. Recording the model makes a partial re-embed detectable rather
than silently wrong. The same applies to `images.embedding_model`.

---

## 4. Document processing pipeline [§18]

```
upload → validate → checksum → duplicate check → register version
   → extract structure → extract text (per page) → OCR decision (per page)
   → extract images → extract tables → detect sections → chunk
   → embed (batched) → index → validate → READY
```

**Library: PyMuPDF (fitz).** It gives text with per-span coordinates and font sizes (needed for
heading detection and evidence highlighting), embedded image extraction with bounding boxes, page
rasterisation for OCR, and the table finder — from one dependency. `pdfplumber` is better at ruled
tables and can be added behind `DocumentProcessor` if the corpus needs it.

Note the licence: PyMuPDF is AGPL-3.0 or commercial. For an internal, non-distributed deployment
this is fine, but **you should confirm this is acceptable to your legal/procurement position before
STEP 4.** If it is not, `pypdfium2` (BSD) plus `pdfplumber` is the fallback, at the cost of weaker
structure extraction.

### 4.1 Job execution — no Celery, no Redis

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

### 4.2 Atomic re-ingestion

Re-processing an existing version must never leave the corpus half-indexed. The job builds all new
rows, validates them (§4.4), and only then flips `document_versions.state` to `ready` in one
transaction, marking the prior generation `superseded`. Retrieval filters on `state = 'ready'`, so a
partially-built version is invisible rather than partially visible.

### 4.3 Idempotency [§19]

Two distinct cases, which the brief conflates:

- **Byte-identical re-upload** — `checksum_sha256` collides. Return the existing version, do not
  re-ingest, record the upload attempt in the audit log. Idempotent.
- **New release of the same document** — different bytes, same `document_id`, new `release_id`.
  This is a *new version*, not a duplicate. The uploader supplies (or the system infers, subject to
  confirmation) the document identity and release; the `(document_id, release_id, version_label)`
  unique constraint prevents accidental doubles.

Auto-inferring document identity from filename is unreliable and will eventually merge two unrelated
manuals. The upload UI should propose an inferred match and **require confirmation** [§29].

### 4.4 Indexing validation

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

Embedded raster images via PyMuPDF with bounding boxes. Filter noise by size, aspect ratio and
repetition across pages (headers/logos appear on every page and are discarded). Captions are
detected from text runs immediately below/above the bbox matching `Figure|Fig\.|Screenshot|Diagram`
patterns; when absent, `surrounding_text` is the ±N characters of page text nearest the bbox.
Each image is written to storage with a thumbnail, and keeps
`document_version_id + page_number + section_id + bbox` — the §5 association requirement.

Vector-drawn diagrams are not embedded rasters. Where a page region is predominantly vector graphics,
that region is rasterised as a "diagram" image so the §6 guarantee (show the *original*) holds for
drawn diagrams too, not just screenshots.

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

### 8.1 The provider question — needs your decision

**Anthropic does not offer an embeddings API.** Claude is the answering model [§21]; the embedding
model must come from elsewhere. This has a governance consequence the brief should confront directly,
because §30 says the documentation may be confidential: *embedding a corpus through a third-party
API sends the entire corpus to that third party.* For internal operational manuals this is often
acceptable under an enterprise agreement; sometimes it is categorically not.

Two viable paths:

| | Hosted (e.g. Voyage `voyage-3`) | Self-hosted (`BAAI/bge-m3`) |
|---|---|---|
| Retrieval quality | Higher out of the box | Strong; competitive |
| Corpus leaves network | **Yes** | **No** |
| Ops burden | None | GPU or slow CPU inference |
| Cost | Per-token, small | Fixed infra |
| Multilingual | Good | Excellent |

**Recommendation:** default to self-hosted `bge-m3` (1024-dim, matching the DDL above) *if* the
documentation is confidential, because a data-governance problem discovered after indexing 5,000
documents is extremely expensive to undo. If your legal position permits a hosted provider, take it
for the better quality. Either way the `EmbeddingProvider` port keeps this reversible, and the
`embedding_model` column keeps a migration honest.

**This is the one decision I need from you before STEP 4.**

### 8.2 Mechanics

Batch (64–128 chunks per call), retry with backoff, persist incrementally so a failure resumes
rather than restarts. Queries and documents use the model's respective prefixes where the model
defines them. Embedding dimension is asserted against the column at startup.

---

## 9. Hybrid retrieval [§11, §12]

### 9.1 The stopword problem — the most important detail in this document

The brief's own example, **`PNL NOT PROCESSED`**, breaks under the obvious implementation.

`to_tsvector('english', 'PNL NOT PROCESSED')` yields roughly `'pnl':1 'process':3`. The English
configuration **discards `NOT` as a stopword** and stems `PROCESSED` → `process`. A phrase search for
`NOT PROCESSED` therefore cannot distinguish it from `PROCESSED`, and a status value whose entire
meaning is the negation becomes unsearchable. The same applies to `IS NOT`, `NO`, `OFF`, and
single-letter codes. This is not a hypothetical edge case — it is the brief's flagship example.

**Design consequence: three retrieval legs, not two.**

1. **Semantic** — pgvector cosine over `chunks.embedding`.
2. **Lexical** — Postgres FTS using the **`simple`** configuration (no stemming, no stopword
   removal) over a normalised copy of the text, preserving `NOT`, codes and acronyms exactly.
   Phrase queries use `phraseto_tsquery('simple', ...)`.
3. **Fuzzy exact** — `pg_trgm` similarity, which catches OCR-damaged and near-miss technical strings
   that leg 2 misses by one character.

A quoted phrase in the user's query (`"PNL NOT PROCESSED"`) or a detected all-caps technical token
escalates leg 2 to a strict phrase requirement and boosts its weight. An unstemmed `simple` index
costs some recall on ordinary prose, which legs 1 and 3 recover; the reverse trade — losing exact
technical strings — is not recoverable.

*This behaviour must be verified empirically on the actual Postgres instance during STEP 3 before
the schema is frozen.*

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
| Exact technical strings unsearchable (stopwords, stemming) | Flagship queries fail | `simple` FTS config + trigram leg; verified in STEP 3 (§9.1) |
| Embedding provider vs. confidentiality | Corpus leaves the network irreversibly | Decide **before** STEP 4; self-hosted default (§8.1) |
| Poor PDF structure (no outline, inconsistent headings) | Weak sections → weak chunks → weak citations | Font-clustering fallback; needs real documents early |
| HNSW recall loss under release/ACL filters | Silently wrong or empty results | `iterative_scan`, `ef_search` floor, recall test (§3.4) |
| OCR corrupts exact strings | Wrong or missed answers on scanned docs | Per-page OCR, confidence propagation, trigram rescue, UI marker (§5) |
| Golden dataset never materialises | No way to detect regression; §33/§34 unmet | Tier-1 eval in CI from day one; request 30–50 real questions now |
| Wrong-release answers | Directly violates §9/§49-N | Pre-filter by release, explicit conflict detection, release accuracy as a CI metric |
| PyMuPDF AGPL licensing | Legal exposure | Confirm before STEP 4; `pypdfium2` fallback (§4) |
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
8. **§21 — "Claude as the primary LLM" leaves embeddings unspecified**, and embedding a confidential
   corpus through a third-party API is a governance decision, not an implementation detail. It needs
   an explicit answer before ingestion. (§8.1)
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

## 21. Implementation roadmap

| Step | Deliverable | Exit criterion |
|---|---|---|
| **0** | *This document, reviewed* + two decisions (embedding provider; PyMuPDF licence) | Sign-off |
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

## 22. What I need from you before STEP 3

1. **Embedding provider decision** (§8.1) — may the documentation be sent to a third-party embedding
   API, or must embeddings be self-hosted? This is irreversible in practice once a corpus is indexed.
2. **Representative documents** (§48) — ideally: one text PDF, one screenshot-heavy, one with tables,
   one scanned, and the *same manual in two releases*. The last one is the most valuable, because it
   exercises §9, §15 and §45 simultaneously.
3. **30–50 real questions with known answers** (§33), to seed the golden dataset.
4. **Confirmation of the authority model** (§11) — particularly the relative standing of operational
   procedures versus manuals in your organisation.
5. **PyMuPDF licence position** (§4).

Items 1 and 5 block STEP 3. Items 2–4 block meaningful validation of STEPs 4–6.
