from __future__ import annotations
import time
from typing import Any, Dict, List

class RetryQueue:
    def __init__(self): self.items: List[Dict[str, Any]] = []
    def enqueue(self, op): self.items.append({**op, "queued_at": time.time()})
    def __len__(self): return len(self.items)

def save_with_retry(api_call, payload, queue):
    try: return api_call(payload)
    except (ConnectionError, TimeoutError, OSError) as e:
        queue.enqueue({"payload": payload, "error": str(e)})
        return {"ok": False, "queued": True, "message": "Saved offline — will retry when online"}

def resolve_jitsi_base(primary, fallback, probe):
    try:
        if probe(primary): return primary
    except Exception: pass
    return fallback

def send_sms(provider, to, body, queue):
    try: return provider.send(to, body)
    except TimeoutError:
        queue.enqueue({"type":"sms","to":to,"body":body})
        return {"ok": False, "queued": True, "message": "SMS queued after provider timeout"}

def test_save_while_api_down_queues():
    q = RetryQueue()
    out = save_with_retry(lambda _: (_ for _ in ()).throw(ConnectionError("down")), {"id":"s1"}, q)
    assert out["queued"] and len(q)==1

def test_jitsi_fallback():
    def probe(url):
        if "primary" in url: raise OSError("down")
        return True
    assert resolve_jitsi_base("https://primary.x","https://fallback.x", probe)=="https://fallback.x"

def test_sms_timeout_queued():
    q = RetryQueue()
    class P:
        def send(self, to, body): raise TimeoutError("t")
    assert send_sms(P(), "01712345678", "hi", q)["queued"] and len(q)==1
