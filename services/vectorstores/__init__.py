from services.vectorstores.base import VectorStore
from services.vectorstores.memory_store import MemoryVectorStore
from services.vectorstores.sqlite_vec_store import SqliteVecStore

DEFAULT_BACKEND = "sqlite-vec"

def get_vector_store(backend=None, **kwargs) -> VectorStore:
    backend = backend or DEFAULT_BACKEND
    if backend in ("sqlite-vec", "sqlite", "default", "faiss", "chroma"):
        return SqliteVecStore(**kwargs)
    if backend == "memory":
        return MemoryVectorStore(**kwargs)
    raise ValueError(f"unknown vector backend: {backend}")
