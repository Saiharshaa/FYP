"""Model clients behind one call: generate(prompt, temperature, seed, max_tokens).

Backends:
  * MockClient        deterministic, offline; for tests and dry runs.
  * OpenAICompatible  POST {base}/chat/completions. Works with a vLLM server
                      (`vllm serve ...` on TC1) and most hosted APIs.

Connection settings come only from the environment, never from code or config
files that might be committed:
  VERIFIER_BASE_URL   e.g. http://gpu-node:8000/v1
  VERIFIER_MODEL      model name as the server knows it
  VERIFIER_API_KEY    optional for local vLLM; sent as a Bearer token if set
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import httpx


@dataclass(frozen=True)
class Generation:
    text: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    model: str
    finish_reason: str | None = None  # "length" means max_tokens truncated it


class ModelClient(Protocol):
    model: str

    def generate(self, prompt: str, temperature: float, seed: int,
                 max_tokens: int) -> Generation: ...


class MockClient:
    """Returns responder(prompt, seed) — by default a stable hash-derived string —
    with whitespace-token counts. Same inputs always give the same output."""

    def __init__(self, responder: Callable[[str, int], str] | None = None,
                 model: str = "mock"):
        self.model = model
        self.responder = responder or self._default
        self.calls = 0

    @staticmethod
    def _default(prompt: str, seed: int) -> str:
        h = hashlib.sha256(f"{seed}:{prompt}".encode()).hexdigest()[:8]
        return f"mock response {h}"

    def generate(self, prompt: str, temperature: float, seed: int,
                 max_tokens: int) -> Generation:
        t0 = time.perf_counter()
        self.calls += 1
        words = self.responder(prompt, seed).split(" ")
        truncated = len(words) > max_tokens
        text = " ".join(words[:max_tokens])
        return Generation(text, len(prompt.split()), min(len(words), max_tokens),
                          time.perf_counter() - t0, self.model,
                          "length" if truncated else "stop")


class ClientError(RuntimeError):
    pass


class OpenAICompatibleClient:
    RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}

    CORE_FIELDS = {"model", "messages", "temperature", "seed", "max_tokens"}

    def __init__(self, timeout_s: float = 300.0, max_retries: int = 4,
                 extra_body: dict | None = None,
                 transport: httpx.BaseTransport | None = None):
        # extra_body: server-specific request fields, e.g. llama.cpp's
        # cache_prompt=false (needed for seed determinism). Never secrets.
        clash = self.CORE_FIELDS & set(extra_body or {})
        if clash:
            raise ClientError(f"extra_body may not override {sorted(clash)}")
        self.extra_body = dict(extra_body or {})
        base = os.environ.get("VERIFIER_BASE_URL")
        model = os.environ.get("VERIFIER_MODEL")
        if not base or not model:
            raise ClientError("set VERIFIER_BASE_URL and VERIFIER_MODEL in the environment")
        self.model = model
        self.base_url = base.rstrip("/")
        self.max_retries = max_retries
        key = os.environ.get("VERIFIER_API_KEY")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self._http = httpx.Client(base_url=self.base_url, headers=headers,
                                  timeout=timeout_s, transport=transport)

    def __repr__(self) -> str:  # never expose the key
        return f"OpenAICompatibleClient(base_url={self.base_url!r}, model={self.model!r})"

    def generate(self, prompt: str, temperature: float, seed: int,
                 max_tokens: int) -> Generation:
        body = {**self.extra_body, "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature, "seed": seed, "max_tokens": max_tokens}
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = self._http.post("/chat/completions", json=body)
            except httpx.TransportError as e:
                if attempt == self.max_retries:
                    raise ClientError(f"request failed: {e}") from e
            else:
                latency = time.perf_counter() - t0
                if resp.status_code == 200:
                    return self._parse(resp.json(), latency)
                if resp.status_code not in self.RETRY_STATUS or attempt == self.max_retries:
                    raise ClientError(f"HTTP {resp.status_code}: {resp.text[:500]}")
            time.sleep(min(2 ** attempt, 30))
        raise AssertionError("unreachable")

    def _parse(self, data: dict, latency: float) -> Generation:
        try:
            choice = data["choices"][0]
            usage = data["usage"]
            return Generation(
                text=choice["message"]["content"] or "",
                input_tokens=int(usage["prompt_tokens"]),
                output_tokens=int(usage["completion_tokens"]),
                latency_s=latency,
                model=data.get("model", self.model),
                finish_reason=choice.get("finish_reason"),
            )
        except (KeyError, IndexError, TypeError) as e:
            # Missing usage would silently zero the cost metrics; fail loudly.
            raise ClientError(f"unexpected response shape ({e!r}): {str(data)[:500]}") from e

    def close(self) -> None:
        self._http.close()


def make_client(backend: str, **kwargs) -> ModelClient:
    if backend == "mock":
        return MockClient(**kwargs)
    if backend == "openai":
        return OpenAICompatibleClient(**kwargs)
    raise ValueError(f"unknown model backend {backend!r}; choose 'mock' or 'openai'")
