"""Thin VectorStore interface so Chroma is not a hard dependency (P36 C4)."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence

class VectorStore(ABC):
    @abstractmethod
    def add(self, ids: Sequence[str], documents: Sequence[str], metadatas: Sequence[Dict[str, Any]] | None = None) -> None: ...
    @abstractmethod
    def query(self, text: str, n: int = 5) -> List[Dict[str, Any]]: ...
    @abstractmethod
    def count(self) -> int: ...
