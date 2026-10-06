import os
import pytest

class FakeLLM:
    def complete(self, prompt: str) -> str:
        return f"echo:{prompt[:40]}"

def test_fake_llm_always_runs():
    assert FakeLLM().complete("hi").startswith("echo:")

@pytest.mark.live
def test_live_groq():
    pytest.skip("live: reserved for workflow_dispatch")

@pytest.mark.live
def test_live_nim():
    pytest.skip("live: reserved for workflow_dispatch")
