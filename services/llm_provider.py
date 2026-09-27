"""
Pluggable LLM providers for CohortOS AI (SPEC §9.3).

- MockLLMProvider: deterministic, offline, used by all tests.
- GeminiProvider: stub that simulates free-tier behaviour and degrades on
  429 / offline / missing key — real network calls are injected later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import hashlib
import re


class LLMError(Exception):
    """Base LLM failure."""


class RateLimitError(LLMError):
    """Free-tier 429 / quota exhausted."""


class OfflineError(LLMError):
    """No network / provider unavailable."""


@dataclass
class LLMRequest:
    prompt: str
    system: str = ""
    tier: str = "cheap"  # cheap | premium
    max_tokens: int = 1024
    temperature: float = 0.2
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    text: str
    model: str = "mock"
    tier: str = "cheap"
    tokens_in: int = 0
    tokens_out: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Provider contract — all paths must be offline-safe when provider is offline."""

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Raise RateLimitError or OfflineError on degrade conditions."""

    @abstractmethod
    def is_available(self) -> bool:
        """False when offline or key missing."""

    def name(self) -> str:
        return self.__class__.__name__


class MockLLMProvider(LLMProvider):
    """
    Deterministic mock for tests and offline demos.

    Behaviour controlled via constructor flags and prompt content markers:
    - prompt contains '__MISMATCH__' → verification answers differ
    - prompt contains '__LOW_CONF__' → low-confidence style answer
    - force_rate_limit=True → always RateLimitError
    - force_offline=True → always OfflineError
    """

    def __init__(
        self,
        force_rate_limit: bool = False,
        force_offline: bool = False,
        default_confidence_hint: float = 0.9,
    ):
        self.force_rate_limit = force_rate_limit
        self.force_offline = force_offline
        self.default_confidence_hint = default_confidence_hint
        self.call_count = 0
        self.last_request: Optional[LLMRequest] = None

    def is_available(self) -> bool:
        return not self.force_offline

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        self.last_request = request
        if self.force_offline:
            raise OfflineError("Mock provider forced offline")
        if self.force_rate_limit:
            raise RateLimitError("Mock free-tier quota exceeded (429)")

        prompt = request.prompt or ""
        system = request.system or ""
        is_verify = "verify" in system.lower() or "re-derive" in system.lower() or "verification" in prompt.lower()

        if "__MISMATCH__" in prompt and is_verify:
            text = (
                "ANSWER: 42 (different derivation)\n"
                "HOW: Alternative path that disagrees with first pass.\n"
                "WHY: Intentional mismatch for self-verification test."
            )
        elif "__LOW_CONF__" in prompt:
            text = (
                "ANSWER: Uncertain — insufficient grounded sources.\n"
                "HOW: Could not derive a reliable step-by-step solution.\n"
                "WHY: Retrieved chunks do not cover the asked concept."
            )
        elif "classify" in system.lower() or "classify this question" in prompt.lower():
            # Simple keyword classification
            q = prompt.lower()
            qtype = "mcq" if any(x in q for x in ("mcq", "option", "a)", "b)", "choose")) else "written"
            subject = "physics" if "physics" in q or "force" in q or "motion" in q else "general"
            topic = "mechanics" if any(x in q for x in ("force", "newton", "motion", "velocity")) else "general"
            board = "hsc" if "hsc" in q else ("medical" if "medical" in q else "general")
            text = f"TYPE:{qtype}\nSUBJECT:{subject}\nTOPIC:{topic}\nBOARD:{board}"
        elif "analytics" in system.lower() or "misconception" in prompt.lower():
            text = (
                "SUGGESTION: 3 students share a rotational-dynamics misconception.\n"
                "RECAP: 15-min free-body + torque recap.\n"
                "MCQS: 15 targeted items on moment of inertia.\n"
                "IMPACT: high"
            )
        else:
            # Standard Answer / How / Why — stable across generate/verify prompts
            # so self-verification matches unless __MISMATCH__ is present.
            text = (
                "ANSWER: F = m a (Newton's second law).\n"
                "HOW: Step 1 identify knowns; Step 2 apply relevant law; "
                "Step 3 check units/signs.\n"
                "WHY: Grounded in retrieved coaching notes for this topic."
            )

        return LLMResponse(
            text=text,
            model="mock-v1",
            tier=request.tier,
            tokens_in=max(1, len(prompt) // 4),
            tokens_out=max(1, len(text) // 4),
            raw={"mock": True, "call": self.call_count},
        )


class GeminiProvider(LLMProvider):
    """
    Google Gemini provider (free-tier / BYOK).

    Uses google-generativeai when installed and a key is present.
    Degrades exactly as SPEC §9.3: missing key / offline → OfflineError,
    429 / quota → RateLimitError. Never raises raw SDK exceptions to callers.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        online: bool = True,
        force_rate_limit: bool = False,
        model_cheap: str = "gemini-1.5-flash",
        model_premium: str = "gemini-1.5-pro",
    ):
        import os
        self.api_key = (api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip() or None
        self.online = online
        self.force_rate_limit = force_rate_limit
        self.model_cheap = model_cheap
        self.model_premium = model_premium
        self.call_count = 0
        self._client = None
        self._sdk_available = False
        if self.api_key:
            try:
                import google.generativeai as genai  # type: ignore
                genai.configure(api_key=self.api_key)
                self._client = genai
                self._sdk_available = True
            except ImportError:
                self._sdk_available = False
            except Exception:
                self._sdk_available = False

    def is_available(self) -> bool:
        return bool(self.api_key) and self.online and not self.force_rate_limit and self._sdk_available

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        if not self.online:
            raise OfflineError("Gemini provider offline — queue or use cache")
        if not self.api_key:
            raise OfflineError("No Gemini API key configured")
        if self.force_rate_limit:
            raise RateLimitError("Gemini free-tier quota exceeded (429)")
        if not self._sdk_available or self._client is None:
            # SDK not installed: structured degrade (not a crash)
            raise OfflineError(
                "google-generativeai is not installed. "
                "pip install google-generativeai  — or use MockLLMProvider offline."
            )

        model_name = self.model_premium if request.tier == "premium" else self.model_cheap
        try:
            model = self._client.GenerativeModel(model_name)
            prompt_parts = []
            if request.system:
                prompt_parts.append(request.system)
            prompt_parts.append(request.prompt)
            result = model.generate_content(
                "\n\n".join(prompt_parts),
                generation_config={
                    "max_output_tokens": request.max_tokens,
                    "temperature": request.temperature,
                },
            )
            text = getattr(result, "text", None) or ""
            if not text and getattr(result, "candidates", None):
                # safety blocks etc.
                text = str(result.candidates[0]) if result.candidates else ""
            return LLMResponse(
                text=text or "[empty Gemini response]",
                model=model_name,
                tier=request.tier,
                tokens_in=len(request.prompt) // 4,
                tokens_out=len(text) // 4,
                raw={"provider": "gemini", "model": model_name},
            )
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "quota" in msg or "resource exhausted" in msg:
                raise RateLimitError(f"Gemini quota exceeded: {e}") from e
            if "offline" in msg or "network" in msg or "connect" in msg:
                raise OfflineError(f"Gemini network failure: {e}") from e
            # Unknown: treat as offline-safe degrade
            raise OfflineError(f"Gemini call failed: {e}") from e

def parse_answer_blocks(text: str) -> Dict[str, str]:
    """Extract ANSWER / HOW / WHY blocks from model text."""
    result = {"answer": "", "how": "", "why": ""}
    current = None
    lines = text.splitlines()
    buf: List[str] = []

    def flush():
        nonlocal buf, current
        if current and buf:
            result[current] = "\n".join(buf).strip()
        buf = []

    for line in lines:
        upper = line.strip().upper()
        if upper.startswith("ANSWER:") or upper.startswith("ANSWER "):
            flush()
            current = "answer"
            rest = line.split(":", 1)[-1].strip() if ":" in line else ""
            buf = [rest] if rest else []
        elif upper.startswith("HOW:") or upper.startswith("HOW "):
            flush()
            current = "how"
            rest = line.split(":", 1)[-1].strip() if ":" in line else ""
            buf = [rest] if rest else []
        elif upper.startswith("WHY:") or upper.startswith("WHY "):
            flush()
            current = "why"
            rest = line.split(":", 1)[-1].strip() if ":" in line else ""
            buf = [rest] if rest else []
        else:
            if current is not None:
                buf.append(line)
    flush()
    if not any(result.values()) and text.strip():
        result["answer"] = text.strip()
    return result


def parse_classification(text: str) -> Dict[str, str]:
    out = {"question_type": "written", "subject": "general", "topic": "general", "board": "general"}
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip().upper(), v.strip().lower()
        if k == "TYPE":
            out["question_type"] = v if v in ("mcq", "written", "cq") else "written"
        elif k == "SUBJECT":
            out["subject"] = v
        elif k == "TOPIC":
            out["topic"] = v
        elif k == "BOARD":
            out["board"] = v
    return out


class GroqProvider(LLMProvider):
    """Groq OpenAI-compatible chat completions API."""

    def __init__(self, api_key: str, model: str = "openai/gpt-oss-20b"):
        self.api_key = (api_key or "").strip()
        self.model = model

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise OfflineError("Groq API key not configured")
        import json
        import urllib.error
        import urllib.request

        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "CohortOS/0.11 (desk-assistant)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")[:400]
            if e.code == 429:
                raise RateLimitError(f"Groq rate limit: {err}") from e
            raise LLMError(f"Groq HTTP {e.code}: {err}") from e
        except OSError as e:
            raise OfflineError(f"Groq network error: {e}") from e
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text or "",
            model=str(data.get("model") or self.model),
            tier=request.tier,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            raw=data,
        )


class NvidiaNimProvider(LLMProvider):
    """NVIDIA NIM / integrate.api.nvidia.com OpenAI-compatible chat API."""

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemma-3-4b-it",
        base_url: str = "https://integrate.api.nvidia.com/v1",
    ):
        self.api_key = (api_key or "").strip()
        self.model = model
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise OfflineError("NVIDIA NIM API key not configured")
        import json
        import urllib.error
        import urllib.request

        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "CohortOS/0.11 (desk-assistant)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")[:400]
            if e.code == 429:
                raise RateLimitError(f"NIM rate limit: {err}") from e
            raise LLMError(f"NIM HTTP {e.code}: {err}") from e
        except OSError as e:
            raise OfflineError(f"NIM network error: {e}") from e
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text or "",
            model=str(data.get("model") or self.model),
            tier=request.tier,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            raw=data,
        )




class OpenAIProvider(LLMProvider):
    """Official OpenAI Platform API (api.openai.com) — requires developer API key."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = (api_key or "").strip()
        self.model = model

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise OfflineError("OpenAI API key not configured")
        import json, urllib.request, urllib.error
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "CohortOS/0.12",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")[:400]
            if e.code == 429:
                raise RateLimitError(f"OpenAI rate limit: {err}") from e
            raise LLMError(f"OpenAI HTTP {e.code}: {err}") from e
        except OSError as e:
            raise OfflineError(f"OpenAI network error: {e}") from e
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text or "",
            model=str(data.get("model") or self.model),
            tier=request.tier,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            raw=data,
        )


class AnthropicProvider(LLMProvider):
    """Official Anthropic API (api.anthropic.com) — requires console API key."""

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-latest"):
        self.api_key = (api_key or "").strip()
        self.model = model

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise OfflineError("Anthropic API key not configured")
        import json, urllib.request, urllib.error
        body = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system:
            body["system"] = request.system
        data_b = json.dumps(body).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=data_b,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
                "User-Agent": "CohortOS/0.12",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")[:400]
            if e.code == 429:
                raise RateLimitError(f"Anthropic rate limit: {err}") from e
            raise LLMError(f"Anthropic HTTP {e.code}: {err}") from e
        except OSError as e:
            raise OfflineError(f"Anthropic network error: {e}") from e
        parts = data.get("content") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text or "",
            model=str(data.get("model") or self.model),
            tier=request.tier,
            tokens_in=int(usage.get("input_tokens") or 0),
            tokens_out=int(usage.get("output_tokens") or 0),
            raw=data,
        )


class GeminiAPIProvider(LLMProvider):
    """Google AI Studio / Gemini API key (generativelanguage.googleapis.com) — not consumer login."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = (api_key or "").strip()
        self.model = model

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise OfflineError("Gemini API key not configured")
        import json, urllib.request, urllib.error
        prompt = request.prompt
        if request.system:
            prompt = f"{request.system}\n\n{prompt}"
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }).encode()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "CohortOS/0.12"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")[:400]
            if e.code == 429:
                raise RateLimitError(f"Gemini rate limit: {err}") from e
            raise LLMError(f"Gemini HTTP {e.code}: {err}") from e
        except OSError as e:
            raise OfflineError(f"Gemini network error: {e}") from e
        cands = data.get("candidates") or []
        text = ""
        if cands:
            parts = (cands[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        return LLMResponse(text=text or "", model=self.model, tier=request.tier, raw=data)


class DeepSeekProvider(LLMProvider):
    """DeepSeek OpenAI-compatible API (api.deepseek.com) — cheap long-context BYO key."""

    def __init__(self, api_key: str, model: str = "deepseek-chat", base_url: str = "https://api.deepseek.com"):
        self.api_key = (api_key or "").strip()
        self.model = model or "deepseek-chat"
        self.base_url = (base_url or "https://api.deepseek.com").rstrip("/")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self.api_key:
            raise OfflineError("DeepSeek API key not configured")
        import json, urllib.request, urllib.error
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "CohortOS/0.13",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")[:400]
            if e.code == 429:
                raise RateLimitError(f"DeepSeek rate limit: {err}") from e
            raise LLMError(f"DeepSeek HTTP {e.code}: {err}") from e
        except OSError as e:
            raise OfflineError(f"DeepSeek network error: {e}") from e
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text or "",
            model=str(data.get("model") or self.model),
            tier=request.tier,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            raw=data,
        )


class LlamaCppProvider(LLMProvider):
    """
    Local GGUF via llama-cpp-python (LFM2.5-1.2B-Instruct default;
    swap model via kwargs model_id / COHORTOS_LOCAL_MODEL_ID → Qwen2.5-1.5B-Instruct-FC).
    """

    def __init__(self, model_id: str = "lfm2.5-1.2b-instruct", **kwargs):
        self.model_id = model_id or "lfm2.5-1.2b-instruct"
        self.max_tokens = int(kwargs.get("max_tokens") or 512)

    def complete(self, request: LLMRequest) -> LLMResponse:
        from services.local_model import local_complete, local_available
        if not local_available():
            raise OfflineError("llama-cpp-python not installed")
        system = ""
        prompt = request.prompt or ""
        # LLMRequest may carry system on different attrs — keep prompt-only
        if getattr(request, "system", None):
            system = str(request.system or "")
        try:
            text = local_complete(
                prompt,
                model_id=self.model_id,
                system=system,
                max_tokens=self.max_tokens,
                temperature=float(getattr(request, "temperature", None) or 0.2),
            )
        except FileNotFoundError as e:
            raise OfflineError(str(e)) from e
        except Exception as e:
            raise LLMError(f"local GGUF failed: {e}") from e
        return LLMResponse(
            text=text or "",
            model=self.model_id,
            tier=request.tier,
            tokens_in=0,
            tokens_out=0,
            raw={"provider": "llama-cpp", "model_id": self.model_id},
        )


def build_llm_provider(provider: str, api_key: str, **kwargs) -> LLMProvider:
    p = (provider or "").strip().lower()
    if p in ("groq",):
        return GroqProvider(api_key, model=kwargs.get("model") or "openai/gpt-oss-20b")
    if p in ("nim", "nvidia", "nvidia_nim", "nvidia-nim"):
        return NvidiaNimProvider(
            api_key,
            model=kwargs.get("model") or "google/gemma-3-4b-it",
            base_url=kwargs.get("base_url") or "https://integrate.api.nvidia.com/v1",
        )
    if p in ("deepseek", "deepseek-chat", "deepseek_v3", "deepseek-v4-flash"):
        model = kwargs.get("model")
        if not model:
            model = "deepseek-chat" if "flash" not in p else "deepseek-chat"
        return DeepSeekProvider(api_key, model=model, base_url=kwargs.get("base_url") or "https://api.deepseek.com")
    if p in ("openai", "chatgpt"):
        return OpenAIProvider(api_key, model=kwargs.get("model") or "gpt-4o-mini")
    if p in ("anthropic", "claude"):
        return AnthropicProvider(api_key, model=kwargs.get("model") or "claude-3-5-haiku-latest")
    if p in ("gemini", "google", "google_gemini"):
        return GeminiAPIProvider(api_key, model=kwargs.get("model") or "gemini-2.0-flash")
    if p in ("llama-cpp", "llamacpp", "gguf", "lfm2.5", "lfm2.5-1.2b-instruct"):
        mid = kwargs.get("model_id") or kwargs.get("model") or "lfm2.5-1.2b-instruct"
        return LlamaCppProvider(model_id=str(mid))
    if p in ("qwen2.5-fc", "qwen2.5-1.5b-instruct-fc", "qwen-local"):
        return LlamaCppProvider(model_id="qwen2.5-1.5b-instruct-fc")
    if p in ("local",):
        # Config-driven local model (default LFM2.5; override local_model_id)
        mid = kwargs.get("model_id") or kwargs.get("local_model_id") or "lfm2.5-1.2b-instruct"
        return LlamaCppProvider(model_id=str(mid))
    if p in ("mock", ""):
        return MockLLMProvider()
    return MockLLMProvider()
