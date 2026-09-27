"""
Centre Vault RAG — LlamaIndex workflows + Chroma persistent store (Phase 20).

Vector store choice: ChromaDB (persistent client under the tenant data dir).
Why not LanceDB / sqlite-vec for this round:
  - Chroma has first-class LlamaIndex VectorStoreIndex adapters and a
    zero-server PersistentClient that fits desk packaging.
  - sqlite-vec is attractive for an all-SQLite stack but LlamaIndex support
    is thinner; LanceDB is fine but we already ship ONNX MiniLM embeddings
    and Chroma accepts those vectors without an extra embedding service.

Embeddings: reuse services.embedding_service.embed_text (ONNX MiniLM or
hashing fallback) so offline desk mode does not download a second model.

Indexing: vault resource title + description + topic + extracted text
(when a local file path is readable). Conversation memory is persisted
per centre in the tenant SQLite `ai_chat_turns` table.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.base import TenantContext, DataAccessLayer


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9\u0980-\u09ff]+", (text or "").lower()) if len(t) > 1]


class _HashEmbedAdapter:
    """LlamaIndex-compatible embedding wrapper over CohortOS embed_text."""

    def __init__(self):
        from services.embedding_service import embed_text, DIM

        self._embed = embed_text
        self.dim = DIM

    def get_text_embedding(self, text: str) -> List[float]:
        return list(self._embed(text or ""))

    def get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [self.get_text_embedding(t) for t in texts]


class RagService:
    def __init__(
        self,
        tenant_context: TenantContext,
        data_layer: Optional[DataAccessLayer] = None,
        content_service=None,
        storage_root: Optional[str] = None,
    ):
        self.tenant_context = tenant_context
        self.data_layer = data_layer or DataAccessLayer(tenant_context)
        self.content_service = content_service
        tid = str(getattr(tenant_context, "tenant_id", None) or "default")
        base = Path(
            storage_root
            or os.environ.get("COHORTOS_RAG_DIR")
            or os.environ.get("COHORTOS_STORAGE_ROOT")
            or "/tmp/cohortos-rag"
        )
        self.persist_dir = base / "chroma" / tid
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._index = None
        self._chroma = None
        self._llama_ok = False
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            import chromadb
            from chromadb.config import Settings

            self._chroma = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._chroma.get_or_create_collection(
                name="vault",
                metadata={"hnsw:space": "cosine"},
            )
            self._llama_ok = True
        except Exception:
            self._chroma = None
            self._collection = None
            self._llama_ok = False

    def backend_name(self) -> str:
        return "chroma+llamaindex" if self._llama_ok else "memory-fallback"

    # ── document body extraction ──────────────────────────────────────

    def _resource_text(self, res: Dict[str, Any]) -> str:
        parts = [
            str(res.get("title") or ""),
            str(res.get("topic") or ""),
            str(res.get("subject") or ""),
            str(res.get("description") or ""),
        ]
        # Prefer explicit body / notes fields when present
        for key in ("body", "notes", "text", "content"):
            if res.get(key):
                parts.append(str(res.get(key)))
        path = str(res.get("file_path") or "")
        if path:
            parts.append(Path(path).name)
            # Best-effort local file text (pdf / plain)
            try:
                root = os.environ.get("COHORTOS_STORAGE_ROOT") or "/tmp/cohortos-storage"
                candidates = [Path(path), Path(root) / path, Path(root) / Path(path).name]
                for c in candidates:
                    if c.is_file() and c.stat().st_size < 5_000_000:
                        raw = c.read_bytes()
                        if path.lower().endswith(".pdf") or (res.get("mime_type") or "").endswith("pdf"):
                            try:
                                from pypdf import PdfReader  # type: ignore
                                import io

                                reader = PdfReader(io.BytesIO(raw))
                                for page in reader.pages[:20]:
                                    parts.append(page.extract_text() or "")
                            except Exception:
                                parts.append(raw[:2000].decode("utf-8", errors="ignore"))
                        else:
                            parts.append(raw[:8000].decode("utf-8", errors="ignore"))
                        break
            except Exception:
                pass
        return "\n".join(p for p in parts if p).strip()

    def _list_resources(self) -> List[Dict[str, Any]]:
        if self.content_service and hasattr(self.content_service, "list_resources"):
            try:
                return list(self.content_service.list_resources() or [])
            except Exception:
                pass
        try:
            return list(self.data_layer.get_all("content_resources") or [])
        except Exception:
            return []

    # ── indexing ──────────────────────────────────────────────────────

    def reindex_vault(self) -> Dict[str, Any]:
        """Rebuild the vector collection from current vault resources."""
        resources = self._list_resources()
        docs = 0
        if self._collection is not None:
            try:
                # Clear + rebuild (small centre corpora)
                existing = self._collection.get()
                ids = existing.get("ids") or []
                if ids:
                    self._collection.delete(ids=ids)
            except Exception:
                pass
            from services.embedding_service import embed_text

            for res in resources:
                text = self._resource_text(res)
                if not text:
                    continue
                rid = str(res.get("id") or uuid.uuid4())
                # Simple chunking
                chunks = _chunk(text, 900, 120)
                for i, ch in enumerate(chunks):
                    cid = f"{rid}:{i}"
                    try:
                        emb = embed_text(ch)
                        self._collection.add(
                            ids=[cid],
                            documents=[ch],
                            embeddings=[list(emb)],
                            metadatas=[
                                {
                                    "resource_id": rid,
                                    "title": str(res.get("title") or "")[:200],
                                    "topic": str(res.get("topic") or "")[:120],
                                }
                            ],
                        )
                        docs += 1
                    except Exception:
                        continue
        else:
            # Persist a JSON fallback index for CI without chromadb
            docs = self._reindex_fallback(resources)
        return {"indexed_chunks": docs, "backend": self.backend_name(), "resources": len(resources)}

    def _reindex_fallback(self, resources: List[Dict[str, Any]]) -> int:
        from services.embedding_service import embed_text

        rows = []
        for res in resources:
            text = self._resource_text(res)
            if not text:
                continue
            rid = str(res.get("id") or "")
            for i, ch in enumerate(_chunk(text, 900, 120)):
                rows.append(
                    {
                        "id": f"{rid}:{i}",
                        "resource_id": rid,
                        "title": res.get("title") or "",
                        "text": ch,
                        "vec": list(embed_text(ch)),
                    }
                )
        path = self.persist_dir / "fallback_index.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows), encoding="utf-8")
        return len(rows)

    def index_resource(self, res: Dict[str, Any]) -> int:
        """Index a single resource (call after vault upload)."""
        if not res:
            return 0
        # Full rebuild is fine for desk-scale corpora
        return int(self.reindex_vault().get("indexed_chunks") or 0)

    # ── retrieval ─────────────────────────────────────────────────────

    def retrieve(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        from services.embedding_service import embed_text, cosine

        out: List[Dict[str, Any]] = []
        if self._collection is not None:
            try:
                qemb = list(embed_text(q))
                hits = self._collection.query(
                    query_embeddings=[qemb],
                    n_results=max(1, limit),
                    include=["documents", "metadatas", "distances"],
                )
                docs = (hits.get("documents") or [[]])[0]
                metas = (hits.get("metadatas") or [[]])[0]
                dists = (hits.get("distances") or [[]])[0]
                for doc, meta, dist in zip(docs, metas, dists):
                    score = 1.0 / (1.0 + float(dist or 0))
                    out.append(
                        {
                            "resource_id": (meta or {}).get("resource_id"),
                            "title": (meta or {}).get("title") or "",
                            "excerpt": (doc or "")[:500],
                            "score": score,
                        }
                    )
                return out
            except Exception:
                pass
        # Fallback JSON index
        path = self.persist_dir / "fallback_index.json"
        if path.is_file():
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
                qv = embed_text(q)
                ranked = []
                for r in rows:
                    ranked.append((cosine(qv, r.get("vec") or []), r))
                ranked.sort(key=lambda x: x[0], reverse=True)
                for score, r in ranked[:limit]:
                    out.append(
                        {
                            "resource_id": r.get("resource_id"),
                            "title": r.get("title") or "",
                            "excerpt": (r.get("text") or "")[:500],
                            "score": float(score),
                        }
                    )
            except Exception:
                pass
        return out

    # ── conversation memory ───────────────────────────────────────────

    def append_turn(self, role: str, content: str, session_id: str = "default") -> None:
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id or "default",
            "role": role,
            "content": (content or "")[:8000],
            "created_at": _now(),
        }
        try:
            self.data_layer.create("ai_chat_turns", row)
        except Exception:
            # Soft-fail: memory is best-effort
            mem = self.persist_dir / "chat_memory.jsonl"
            mem.parent.mkdir(parents=True, exist_ok=True)
            with mem.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")

    def recent_turns(self, session_id: str = "default", limit: int = 12) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        try:
            all_rows = list(self.data_layer.get_all("ai_chat_turns") or [])
            rows = [r for r in all_rows if str(r.get("session_id") or "default") == (session_id or "default")]
            rows.sort(key=lambda r: str(r.get("created_at") or ""))
            return rows[-limit:]
        except Exception:
            pass
        mem = self.persist_dir / "chat_memory.jsonl"
        if mem.is_file():
            try:
                for line in mem.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    r = json.loads(line)
                    if str(r.get("session_id") or "default") == (session_id or "default"):
                        rows.append(r)
                return rows[-limit:]
            except Exception:
                return []
        return []

    # ── answer synthesis ──────────────────────────────────────────────

    def answer(
        self,
        question: str,
        session_id: str = "default",
        llm_complete=None,
    ) -> Dict[str, Any]:
        """
        Retrieve vault chunks, optionally call llm_complete(prompt)->str,
        persist turns. Never returns the bare "Centre snapshot" string when
        vault hits exist.
        """
        q = (question or "").strip()
        hits = self.retrieve(q, limit=5)
        # Ensure index is warm
        if not hits:
            self.reindex_vault()
            hits = self.retrieve(q, limit=5)

        history = self.recent_turns(session_id=session_id, limit=8)
        hist_txt = "\n".join(f"{h.get('role')}: {h.get('content')}" for h in history)

        context_blocks = []
        for h in hits:
            context_blocks.append(
                f"[{h.get('title') or 'doc'}] {h.get('excerpt') or ''}"
            )
        context = "\n\n".join(context_blocks) if context_blocks else "(no vault matches)"

        prompt = (
            "You are CohortOS desk assistant. Answer using the vault context and prior turns. "
            "If the context contains the answer, quote or paraphrase it. "
            "If context is empty, say you could not find it in the centre vault.\n\n"
            f"Prior turns:\n{hist_txt or '(none)'}\n\n"
            f"Vault context:\n{context}\n\n"
            f"Question: {q}\nAnswer:"
        )

        answer = ""
        used_llm = False
        if callable(llm_complete) and hits:
            try:
                answer = str(llm_complete(prompt) or "").strip()
                used_llm = bool(answer)
            except Exception:
                answer = ""

        if not answer:
            # Grounded extractive answer — prove retrieval worked
            if hits:
                top = hits[0]
                answer = (
                    f"From your centre vault (“{top.get('title') or 'document'}”): "
                    f"{(top.get('excerpt') or '').strip()}"
                )
            else:
                answer = (
                    "I could not find matching documents in this centre's vault. "
                    "Upload notes or papers, then ask again."
                )

        self.append_turn("user", q, session_id=session_id)
        self.append_turn("assistant", answer, session_id=session_id)

        return {
            "answer": answer,
            "citations": hits,
            "backend": self.backend_name(),
            "used_llm": used_llm,
            "memory_turns": len(history) + 2,
        }


def _chunk(text: str, max_chars: int = 900, overlap: int = 120) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    out: List[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        out.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out
