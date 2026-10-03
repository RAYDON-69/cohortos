# ADR-003: Vector store portability (Chroma time bomb)

**Status:** Accepted (P36)  
**Date:** 2026-10-02

## Context
pip-audit allowlist for chromadb expires 2026-11-01. Chroma is embedded PersistentClient only (no server), but CVEs still force allowlist debt.

## Decision
Introduce `VectorStore` ABC + `MemoryVectorStore` (token cosine) as a second adapter for tests and offline fallback. Production RagService may keep Chroma until migration; interface allows swapping.

## Migration effort (honest)
- Re-index all vault documents per tenant (one-time batch).
- Memory/sqlite-vec lacks ANN quality of Chroma embeddings — expect answer quality drop unless embeddings model is wired.
- FAISS adapter needs `faiss-cpu` binary wheel (~20MB) and embedding vectors persisted.
- Estimate: 2–4 engineering days for parity + reindex tool; 1 week including pilot validation.

## Consequences
- Canary still forces action by 2026-10-25.
- Do not delete Chroma until second backend proves RAG E2E.

## P37 update
sqlite-vec (SQLite + token cosine / FTS5) is now **DEFAULT_BACKEND**. Chroma is optional and not imported by default. Allowlist canary no longer blocks release when chroma is unused.

## P41 — chromadb out of production
Production `requirements.txt` no longer installs chromadb or llama-index-vector-stores-chroma.
Default remains sqlite-vec. Optional legacy: `requirements-legacy-chroma.txt`.
Allowlist canary for PYSEC-2026-311 is obsolete for the release path.
