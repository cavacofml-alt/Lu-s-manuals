# Documentation Intelligence AI

A multimodal, evidence-grounded knowledge assistant over versioned internal documentation.
Users ask questions in natural language; the system answers **only** from the indexed
documentation, cites the exact document, release and page, shows the original screenshots,
and refuses when the evidence is insufficient.

## Status

**Direction changed.** The organisation has chosen to improve Microsoft Copilot's answers
over the manuals already in SharePoint, rather than build this application. The plan for
that is [`docs/SHAREPOINT.md`](docs/SHAREPOINT.md) and requires no code.

What was built here — STEP 1: the skeleton, the data egress policy and its test suite — is
left intact and unfinished at that point. `docs/ARCHITECTURE.md` remains the fullest
statement of what version-aware, page-exact, evidence-grounded retrieval would require, and
`docs/SHAREPOINT.md` §3 records which of those requirements the Copilot route cannot meet.
Both are worth reading before anyone revisits the decision.

The technical design is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and is awaiting review.
It covers architecture, database schema, ingestion, OCR, chunking, embeddings, hybrid retrieval,
reranking, grounding enforcement, citations, viewer, exports, security, evaluation, observability,
cost, risks and the implementation roadmap — plus an explicit list of points where it departs from
the original specification, and the decisions needed before implementation starts.

Start there.
