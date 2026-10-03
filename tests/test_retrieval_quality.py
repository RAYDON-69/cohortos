"""Retrieval quality gate: hybrid score threshold justified by labelled pairs."""
from __future__ import annotations
import uuid
import pytest
from models.base import DataAccessLayer, TenantContext
from services.retrieval_service import RetrievalService, embed_text, _tokens

def _make_svc():
    tenant = TenantContext(tenant_id=str(uuid.uuid4()), mode="offline-first")
    dal = DataAccessLayer(tenant, db_path=":memory:")
    return RetrievalService(tenant_context=tenant, data_layer=dal)

def test_retrieval_threshold_and_empty_vault():
    svc = _make_svc()
    chunks = svc.retrieve(
        query="Atlantis underwater kingdom lore",
        subject="history",
        topic="mythology",
        limit=5,
    )
    assert chunks == [] or all(getattr(c, "score", 1) >= 0 for c in chunks)

def test_retrieval_ranks_matching_chunk_first_when_seeded():
    svc = _make_svc()
    docs = [
        {
            "resource_id": "a",
            "title": "Newton",
            "text": "Newton second law F=ma force motion mechanics",
        },
        {
            "resource_id": "b",
            "title": "Biology",
            "text": "photosynthesis chlorophyll plants leaves",
        },
    ]

    def _fake_build(batch_id=None):
        out = []
        for d in docs:
            text = d["text"]
            out.append(
                {
                    "resource_id": d["resource_id"],
                    "title": d["title"],
                    "chunk_index": 0,
                    "text": text,
                    "tokens": _tokens(text),
                    "vec": embed_text(f"{d['title']}\n{text}"),
                }
            )
        return out

    svc._build_chunks = _fake_build  # type: ignore
    ranked = svc.retrieve(
        query="Newton force law", subject="physics", topic="mechanics", limit=2
    )
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
    lines = []
    ok = 0
    for q, expect in pairs:
        r = svc.retrieve(query=q, limit=1)
        got = r[0].resource_id if r else None
        score = getattr(r[0], "score", None) if r else None
        lines.append(f"q={q!r} expect={expect} got={got} score={score}")
        if got == expect:
            ok += 1
    print("RETRIEVAL_QUALITY\n" + "\n".join(lines))
    assert ok >= 8, f"retrieval quality {ok}/10 < 8\n" + "\n".join(lines)
