# Documentation Intelligence AI

A multimodal, evidence-grounded knowledge assistant over versioned internal documentation.
Users ask questions in natural language; the system answers **only** from the indexed
documentation, cites the exact document, release and page, shows the original screenshots,
and refuses when the evidence is insufficient.

## Status

**Design phase.** No implementation yet.

The technical design is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and is awaiting review.
It covers architecture, database schema, ingestion, OCR, chunking, embeddings, hybrid retrieval,
reranking, grounding enforcement, citations, viewer, exports, security, evaluation, observability,
cost, risks and the implementation roadmap — plus an explicit list of points where it departs from
the original specification, and the decisions needed before implementation starts.

Start there.
