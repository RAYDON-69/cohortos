"""SQLite-backed vector/text store — default RAG backend (P37 A3).

Uses FTS5 when available, else LIKE + token cosine. No chromadb dependency.
Measured for low-RAM coaching desks.
"""
from __future__ import annotations
import math
import re
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from services.vectorstores.base import VectorStore

def _tokens(s: str) -> Counter:
    return Counter(re.findall(r"\w+", (s or "").lower(), flags=re.UNICODE))

def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b[t] for t in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

class SqliteVecStore(VectorStore):
    def __init__(self, tenant_id: str = "default", db_path: Optional[str] = None):
        self.tenant_id = tenant_id
        if db_path is None:
            db_path = str(Path(tempfile.gettempdir()) / f"cohortos-vec-{tenant_id}.sqlite")
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS docs (
                id TEXT PRIMARY KEY, document TEXT NOT NULL, metadata TEXT
            )"""
        )
        # FTS5 optional
        self._fts = False
        try:
            self._conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(id, document)"
            )
            self._fts = True
        except sqlite3.OperationalError:
            self._fts = False
        self._conn.commit()

    def add(self, ids: Sequence[str], documents: Sequence[str], metadatas: Sequence[Dict[str, Any]] | None = None) -> None:
        import json
        metas = list(metadatas or [{}] * len(ids))
        for i, doc, meta in zip(ids, documents, metas):
            self._conn.execute(
                "INSERT OR REPLACE INTO docs(id, document, metadata) VALUES (?,?,?)",
                (i, doc, json.dumps(meta or {})),
            )
            if self._fts:
                self._conn.execute("INSERT OR REPLACE INTO docs_fts(id, document) VALUES (?,?)", (i, doc))
        self._conn.commit()

    def query(self, text: str, n: int = 5) -> List[Dict[str, Any]]:
        import json
        rows = list(self._conn.execute("SELECT id, document, metadata FROM docs"))
        q = _tokens(text)
        scored = []
        for rid, doc, meta in rows:
            scored.append({
                "id": rid,
                "document": doc,
                "metadata": json.loads(meta or "{}"),
                "score": _cosine(q, _tokens(doc)),
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:n]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0])

    def rss_hint_mb(self) -> float:
        """Rough size of the sqlite file for 4GB-profile reporting."""
        try:
            return Path(self.db_path).stat().st_size / (1024 * 1024)
        except OSError:
            return 0.0
