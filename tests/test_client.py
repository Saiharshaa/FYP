import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from verifier.harness import client as C

REPO = Path(__file__).resolve().parents[1]


def ok_payload(text="hello", pt=12, ct=3):
    return {"model": "served-model",
            "choices": [{"message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": pt, "completion_tokens": ct}}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("VERIFIER_BASE_URL", "http://vllm.test:8000/v1/")
    monkeypatch.setenv("VERIFIER_MODEL", "qwen-coder-7b")
    monkeypatch.setenv("VERIFIER_API_KEY", "sk-secret-123")
    monkeypatch.setattr(C.time, "sleep", lambda s: None)


def make(handler, **kw):
    return C.OpenAICompatibleClient(transport=httpx.MockTransport(handler), **kw)


def test_mock_is_deterministic_and_seed_sensitive():
    m = C.MockClient()
    a, b = m.generate("p", 0.7, 1, 100), m.generate("p", 0.7, 1, 100)
    assert a.text == b.text and a.text != m.generate("p", 0.7, 2, 100).text
    assert a.input_tokens == 1 and a.output_tokens == 3 and a.latency_s >= 0


def test_mock_respects_max_tokens():
    g = C.MockClient(lambda p, s: "a b c d e").generate("p", 0, 0, 2)
    assert g.text == "a b" and g.output_tokens == 2 and g.finish_reason == "length"


def test_openai_request_and_parse(env):
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=ok_payload())

    g = make(handler).generate("Is this correct?", temperature=0.2, seed=7, max_tokens=64)
    assert seen["url"] == "http://vllm.test:8000/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-secret-123"
    assert seen["body"] == {"model": "qwen-coder-7b",
                            "messages": [{"role": "user", "content": "Is this correct?"}],
                            "temperature": 0.2, "seed": 7, "max_tokens": 64}
    assert (g.text, g.input_tokens, g.output_tokens, g.finish_reason) == ("hello", 12, 3, "stop")
    assert g.latency_s >= 0


def test_extra_body_is_sent(env):
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=ok_payload())

    make(handler, extra_body={"cache_prompt": False}).generate("p", 0.5, 3, 8)
    assert seen["body"]["cache_prompt"] is False
    assert seen["body"]["seed"] == 3 and seen["body"]["model"] == "qwen-coder-7b"


def test_extra_body_cannot_override_core_fields(env):
    with pytest.raises(C.ClientError, match="may not override"):
        make(lambda r: httpx.Response(200, json=ok_payload()), extra_body={"seed": 1})


def test_make_client_passes_config_options(env):
    c = C.make_client("openai", extra_body={"cache_prompt": False})
    assert c.extra_body == {"cache_prompt": False}


def test_no_auth_header_without_key(env, monkeypatch):
    monkeypatch.delenv("VERIFIER_API_KEY")
    seen = {}

    def handler(req):
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json=ok_payload())

    make(handler).generate("p", 0, 0, 8)
    assert seen["auth"] is None


def test_missing_env_raises(monkeypatch):
    for k in ("VERIFIER_BASE_URL", "VERIFIER_MODEL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(C.ClientError, match="VERIFIER_BASE_URL"):
        C.OpenAICompatibleClient()


def test_retries_transient_errors(env):
    replies = iter([httpx.Response(503), httpx.Response(429), httpx.Response(200, json=ok_payload())])
    assert make(lambda req: next(replies)).generate("p", 0, 0, 8).text == "hello"


def test_gives_up_after_max_retries(env):
    with pytest.raises(C.ClientError, match="HTTP 503"):
        make(lambda req: httpx.Response(503), max_retries=2).generate("p", 0, 0, 8)


def test_client_error_not_retried(env):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(400, text="bad request")

    with pytest.raises(C.ClientError, match="HTTP 400"):
        make(handler).generate("p", 0, 0, 8)
    assert len(calls) == 1


def test_missing_usage_fails_loudly(env):
    payload = ok_payload()
    del payload["usage"]
    with pytest.raises(C.ClientError, match="unexpected response shape"):
        make(lambda req: httpx.Response(200, json=payload)).generate("p", 0, 0, 8)


def test_repr_hides_key(env):
    assert "sk-secret" not in repr(make(lambda r: httpx.Response(200, json=ok_payload())))


@pytest.mark.skipif(not shutil.which("git") or not (REPO / ".git").exists(),
                    reason="needs the git checkout")
def test_env_file_is_gitignored():
    for name in (".env", ".env.local"):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=REPO)
        assert r.returncode == 0, f"{name} is not gitignored"
    r = subprocess.run(["git", "check-ignore", "-q", ".env.example"], cwd=REPO)
    assert r.returncode == 1, ".env.example should stay tracked"
