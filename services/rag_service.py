"""
Centre Vault RAG — LlamaIndex + Chroma persistent store (Phase 21).

Vector store: ChromaDB PersistentClient under COHORTOS_RAG_DIR/{tenant}/chroma.

Pipeline (preferred):
  llama-index-core VectorStoreIndex
  + ChromaVectorStore (llama-index-vector-stores-chroma)
  + CohortOSEmbedding (wraps services.embedding_service.embed_text)

Fallback when LlamaIndex / Chroma packages are missing:
  direct chromadb collection API, then JSON index on disk.

Conversation memory is persisted per centre (SQLite ai_chat_turns or JSONL).
"""
from __future__ import annotations

import json
import os
import tempfile
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.base import TenantContext, DataAccessLayer


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class CohortOSEmbedding:
    """LlamaIndex BaseEmbedding adapter over CohortOS ONNX/hash embed_text."""

    def __init__(self):
        from services.embedding_service import embed_text, DIM

        self._embed = embed_text
        self.dim = DIM
        self.model_name = "cohortos-minilm"

    # --- LlamaIndex BaseEmbedding interface (duck-typed) ---
    def _get_query_embedding(self, query: str) -> List[float]:
        return list(self._embed(query or ""))

    def _get_text_embedding(self, text: str) -> List[float]:
        return list(self._embed(text or ""))

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [self._get_text_embedding(t) for t in texts]

    def get_text_embedding(self, text: str) -> List[float]:
        return self._get_text_embedding(text)

    def get_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        return self._get_text_embedding(text)



def clean_thinking_content(text: str) -> str:
    """Open Notebook pattern (graphs/ask.py): strip model thinking blocks."""
    import re
    if not text:
        return ""
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.I)
    text = re.sub(r"<thinking>[\s\S]*?</thinking>", "", text, flags=re.I)
    return text.strip()


def expand_search_terms(question: str) -> List[str]:
    """
    Open Notebook ask strategy pattern (graphs/ask.py Strategy.searches):
    fan out 1–3 concrete search terms from the user question instead of
    a single raw query. Keeps terms non-empty (their filter on blank terms).
    """
    q = (question or "").strip()
    if not q:
        return []
    terms = [q]
    # Pull quoted phrases
    import re
    for m in re.finditer(r"[\"']([^\"']{3,80})[\"']", q):
        terms.append(m.group(1).strip())
    # Significant tokens as secondary term
    toks = [t for t in re.findall(r"[A-Za-z0-9_\u0980-\u09ff]{4,}", q) if t.lower() not in {
        "what", "which", "where", "when", "this", "that", "with", "from", "your", "have", "tell", "about"
    }]
    if toks:
        terms.append(" ".join(toks[:6]))
    # Dedupe preserving order
    seen = set()
    out = []
    for t in terms:
        k = t.lower()
        if k not in seen and t.strip():
            seen.add(k)
            out.append(t.strip())
    return out[:3]

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
            or str(Path(tempfile.gettempdir()) / "cohortos-rag")
        )
        self.persist_dir = base / "chroma" / tid
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._embedder = CohortOSEmbedding()
        self._collection = None
        self._llama_index = None
        self._backend = "none"
        self._init_backend()

    def _init_backend(self) -> None:
        # 1) Prefer LlamaIndex + ChromaVectorStore
        try:
            import chromadb
            from chromadb.config import Settings

            client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )
            collection = client.get_or_create_collection(
                name="vault",
                metadata={"hnsw:space": "cosine"},
            )
            self._collection = collection

            try:
                from llama_index.core import VectorStoreIndex, StorageContext, Settings as LISettings
                from llama_index.core.schema import TextNode
                from llama_index.vector_stores.chroma import ChromaVectorStore

                vector_store = ChromaVectorStore(chroma_collection=collection)
                storage_context = StorageContext.from_defaults(vector_store=vector_store)
                # Embeddings: inject CohortOS embedder via Settings when BaseEmbedding subclass works;
                # otherwise we still use collection.query with our vectors in retrieve().
                try:
                    from llama_index.core.embeddings import BaseEmbedding

                    class _LIEmbed(BaseEmbedding):
                        def __init__(self, inner: CohortOSEmbedding):
                            super().__init__()
                            self._inner = inner

                        def _get_query_embedding(self, query: str) -> List[float]:
                            return self._inner.get_query_embedding(query)

                        def _get_text_embedding(self, text: str) -> List[float]:
                            return self._inner.get_text_embedding(text)

                        def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
                            return self._inner._get_text_embeddings(texts)

                        async def _aget_query_embedding(self, query: str) -> List[float]:
                            return self._get_query_embedding(query)

                        async def _aget_text_embedding(self, text: str) -> List[float]:
                            return self._get_text_embedding(text)

                    LISettings.embed_model = _LIEmbed(self._embedder)
                    self._llama_index = VectorStoreIndex.from_vector_store(
                        vector_store,
                        storage_context=storage_context,
                        embed_model=LISettings.embed_model,
                    )
                    self._backend = "llama-index+chroma"
                    self._TextNode = TextNode
                    return
                except Exception:
                    # Chroma ok, LlamaIndex partial
                    self._backend = "chroma"
                    return
            except Exception:
                self._backend = "chroma"
                return
        except Exception:
            self._collection = None
            self._backend = "json-fallback"

    def backend_name(self) -> str:
        return self._backend

    def _resource_text(self, res: Dict[str, Any]) -> str:
        parts = [
            str(res.get("title") or ""),
            str(res.get("topic") or ""),
            str(res.get("subject") or ""),
            str(res.get("description") or ""),
        ]
        for key in ("body", "notes", "text", "content"):
            if res.get(key):
                parts.append(str(res.get(key)))
        path = str(res.get("file_path") or "")
        if path:
            parts.append(Path(path).name)
            try:
                root = os.environ.get("COHORTOS_STORAGE_ROOT") or str(Path(tempfile.gettempdir()) / "cohortos-storage")
                for c in (Path(path), Path(root) / path, Path(root) / Path(path).name):
                    if c.is_file() and c.stat().st_size < 5_000_000:
                        raw = c.read_bytes()
                        if str(path).lower().endswith(".pdf") or "pdf" in str(res.get("mime_type") or "").lower():
                            try:
                                from pypdf import PdfReader
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

    def reindex_vault(self) -> Dict[str, Any]:
        resources = self._list_resources()
        docs = 0
        if self._collection is not None:
            try:
                existing = self._collection.get()
                ids = existing.get("ids") or []
                if ids:
                    self._collection.delete(ids=ids)
            except Exception:
                pass
            for res in resources:
                text = self._resource_text(res)
                if not text:
                    continue
                rid = str(res.get("id") or uuid.uuid4())
                for i, ch in enumerate(_chunk(text, 900, 120)):
                    cid = f"{rid}:{i}"
                    try:
                        emb = self._embedder.get_text_embedding(ch)
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
            # Refresh LlamaIndex handle after rebuild
            if self._backend.startswith("llama-index"):
                try:
                    from llama_index.core import VectorStoreIndex, StorageContext
                    from llama_index.vector_stores.chroma import ChromaVectorStore

                    vs = ChromaVectorStore(chroma_collection=self._collection)
                    self._llama_index = VectorStoreIndex.from_vector_store(
                        vs,
                        storage_context=StorageContext.from_defaults(vector_store=vs),
                        embed_model=getattr(self, "_li_embed", None) or self._embedder,
                    )
                except Exception:
                    pass
        else:
            docs = self._reindex_fallback(resources)
        return {"indexed_chunks": docs, "backend": self.backend_name(), "resources": len(resources)}

    def _reindex_fallback(self, resources: List[Dict[str, Any]]) -> int:
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
                        "vec": list(self._embedder.get_text_embedding(ch)),
                    }
                )
        path = self.persist_dir / "fallback_index.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows), encoding="utf-8")
        return len(rows)

    def index_resource(self, res: Dict[str, Any]) -> int:
        if not res:
            return 0
        return int(self.reindex_vault().get("indexed_chunks") or 0)

    def retrieve(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        out: List[Dict[str, Any]] = []

        # Prefer LlamaIndex retriever when index is live
        if self._llama_index is not None:
            try:
                retriever = self._llama_index.as_retriever(similarity_top_k=max(1, limit))
                nodes = retriever.retrieve(q)
                for n in nodes:
                    meta = dict(getattr(n, "metadata", None) or {})
                    text = getattr(n, "text", None) or getattr(n, "node", None)
                    if hasattr(text, "text"):
                        text = text.text
                    score = float(getattr(n, "score", None) or 0.0)
                    out.append(
                        {
                            "resource_id": meta.get("resource_id"),
                            "title": meta.get("title") or "",
                            "excerpt": str(text or "")[:500],
                            "score": score,
                        }
                    )
                if out:
                    return out
            except Exception:
                pass

        if self._collection is not None:
            try:
                qemb = list(self._embedder.get_query_embedding(q))
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

        from services.embedding_service import cosine

        path = self.persist_dir / "fallback_index.json"
        if path.is_file():
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
                qv = self._embedder.get_query_embedding(q)
                ranked = [(cosine(qv, r.get("vec") or []), r) for r in rows]
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

    def append_turn(self, role: str, content: str, session_id: str = "default") -> None:
        row = {
            "id": str(uuid.uuid4()),
            "session_id": session_id or "default",
            "role": role,
            "content": (content or "")[:8000],
            "created_at": _now(),
        }
        try:
            _nid = self.data_layer.create("ai_chat_turns", row)
            row["id"] = str(_nid)
        except Exception:
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


    def answer(
        self,
        question: str,
        session_id: str = "default",
        llm_complete=None,
    ) -> Dict[str, Any]:
        """
        Multi-query retrieve (Open Notebook ask Strategy.searches) +
        inline [n] citations (citations.md / provide_answer ids) +
        optional local/cloud synthesis.
        """
        q = (question or "").strip()
        terms = expand_search_terms(q) or ([q] if q else [])
        # Warm index once
        self.reindex_vault()
        # Merge hits across terms (Open Notebook fans out provide_answer per term)
        by_key: Dict[str, Dict[str, Any]] = {}
        for term in terms:
            for h in self.retrieve(term, limit=4):
                key = str(h.get("resource_id") or "") + "|" + (h.get("excerpt") or "")[:80]
                prev = by_key.get(key)
                if not prev or float(h.get("score") or 0) > float(prev.get("score") or 0):
                    by_key[key] = h
        hits = sorted(by_key.values(), key=lambda x: float(x.get("score") or 0), reverse=True)[:5]

        history = self.recent_turns(session_id=session_id, limit=8)
        hist_txt = "\n".join(f"{h.get('role')}: {h.get('content')}" for h in history)

        # Citation list: [1] title — excerpt (Open Notebook reference list pattern)
        citations = []
        context_blocks = []
        for i, h in enumerate(hits, 1):
            title = h.get("title") or "document"
            excerpt = (h.get("excerpt") or "").strip()
            citations.append(
                {
                    "n": i,
                    "resource_id": h.get("resource_id"),
                    "title": title,
                    "excerpt": excerpt[:400],
                    "score": h.get("score"),
                }
            )
            context_blocks.append(f"[{i}] {title}: {excerpt}")
        context = "\n\n".join(context_blocks) if context_blocks else "(no vault matches)"

        prompt = (
            "You are CohortOS desk assistant. Answer using ONLY the vault context. "
            "Cite sources inline as [1], [2] matching the context numbers. "
            "If context is empty, say you could not find it in the centre vault.\n\n"
            f"Prior turns:\n{hist_txt or '(none)'}\n\n"
            f"Vault context:\n{context}\n\n"
            f"Question: {q}\nAnswer:"
        )

        answer = ""
        used_llm = False
        if callable(llm_complete) and hits:
            try:
                raw = str(llm_complete(prompt) or "").strip()
                answer = clean_thinking_content(raw)
                # Open Notebook: drop empty after stripping thinking
                if not answer.strip():
                    answer = ""
                used_llm = bool(answer)
            except Exception:
                answer = ""

        if not answer:
            if hits:
                # Extractive with inline citations (always verifiable)
                parts = []
                for c in citations[:3]:
                    parts.append(f"[{c['n']}] {c['title']}: {c['excerpt'][:240]}")
                answer = (
                    f"From your centre vault: {parts[0]}"
                    + ((" " + " ".join(parts[1:])) if len(parts) > 1 else "")
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
            "citations": citations,
            "backend": self.backend_name(),
            "used_llm": used_llm,
            "memory_turns": len(history) + 2,
            "search_terms": terms,
        }

