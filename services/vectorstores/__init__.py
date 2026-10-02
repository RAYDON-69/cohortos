from services.vectorstores.base import VectorStore
from services.vectorstores.memory_store import MemoryVectorStore

def get_vector_store(backend: str = "memory", **kwargs) -> VectorStore:
    # sqlite-vec / faiss adapters share memory implementation until native deps ship
    if backend in ("memory", "sqlite-vec", "faiss", "chroma"):
        return MemoryVectorStore(**kwargs)
    raise ValueError(f"unknown vector backend: {backend}")
