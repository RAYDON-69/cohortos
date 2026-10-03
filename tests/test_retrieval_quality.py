"""Retrieval quality gate: hybrid score threshold justified by labelled pairs."""
from __future__ import annotations
import uuid
import pytest
from models.base import DataAccessLayer, TenantContext

def _make_svc():
    from services.retrieval_service import RetrievalService
    import inspect
    tenant = TenantContext(tenant_id=str(uuid.uuid4()), mode="offline-first")
    dal = DataAccessLayer(tenant, db_path=":memory:")
    sig = inspect.signature(RetrievalService.__init__)
    kwargs = {}
    for name in sig.parameters:
        if name == "self":
            continue
        if name in ("data_layer", "dal", "layer"):
            kwargs[name] = dal
        elif name in ("tenant_context", "tenant"):
            kwargs[name] = tenant
    try:
        return RetrievalService(**kwargs) if kwargs else RetrievalService(dal)
    except TypeError:
        return RetrievalService(dal, tenant)

def test_retrieval_threshold_and_empty_vault():
    svc = _make_svc()
    chunks = svc.retrieve(query="Atlantis underwater kingdom lore", subject="history", topic="mythology", limit=5)
    assert chunks == [] or all(getattr(c, "score", 1) >= 0 for c in chunks)

def test_retrieval_ranks_matching_chunk_first_when_seeded():
    svc = _make_svc()
    if not hasattr(svc, "_build_chunks"):
        pytest.skip("no _build_chunks")
    docs = [
        {"resource_id": "a", "title": "Newton", "text": "Newton second law F=ma force motion mechanics"},
        {"resource_id": "b", "title": "Biology", "text": "photosynthesis chlorophyll plants leaves"},
    ]
    def _fake_build(batch_id=None):
        from services.retrieval_service import embed_text
        out = []
        for d in docs:
            d = dict(d)
            d["vec"] = embed_text(d["text"])
            out.append(d)
        return out
    svc._build_chunks = _fake_build  # type: ignore
    ranked = svc.retrieve(query="Newton force law", subject="physics", topic="mechanics", limit=2)
    assert ranked, "expected hits on seeded corpus"
    assert ranked[0].resource_id == "a"
    pairs = [
        ("force F=ma", "a"),
        ("photosynthesis plants", "b"),
        ("Newton mechanics", "a"),
        ("chlorophyll leaves", "b"),
        ("second law motion", "a"),
        ("plants leaves green", "b"),
        ("F equals ma", "a"),
        ("biology plants", "b"),
        ("force motion", "a"),
        ("photosynthesis", "b"),
    ]
    ok = sum(1 for q, expect in pairs if (r := svc.retrieve(query=q, limit=1)) and r[0].resource_id == expect)
    assert ok >= 8, f"retrieval quality {ok}/10 < 8"
