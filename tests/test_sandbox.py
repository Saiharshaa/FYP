import os
import textwrap

import pytest

from verifier.sandbox import DockerSandbox, SubprocessSandbox, load_config, make_sandbox

_docker = DockerSandbox()
DOCKER_UP = _docker.available()


def _backends():
    params = [pytest.param(SubprocessSandbox, id="subprocess", marks=[
        pytest.mark.linux,
        pytest.mark.skipif(os.name != "posix", reason="rlimit backend needs POSIX")])]
    params.append(pytest.param(DockerSandbox, id="docker", marks=[
        pytest.mark.docker,
        pytest.mark.skipif(not DOCKER_UP, reason="no Docker daemon")]))
    return params


@pytest.fixture(params=_backends(), scope="module")
def sandbox(request):
    return request.param()


def code(s: str) -> str:
    return textwrap.dedent(s).lstrip()


def test_normal_code_returns_output(sandbox):
    r = sandbox.run("print(sum(range(10)))\n", timeout_s=10, memory_mb=256)
    assert r == {**r, "stdout": "45\n", "exit_code": 0, "timed_out": False}


def test_exception_gives_nonzero_exit_and_stderr(sandbox):
    r = sandbox.run("raise ValueError('boom')\n", timeout_s=10, memory_mb=256)
    assert r["exit_code"] == 1 and not r["timed_out"]
    assert "ValueError: boom" in r["stderr"]


def test_infinite_loop_times_out(sandbox):
    r = sandbox.run("while True:\n    pass\n", timeout_s=1, memory_mb=256)
    assert r["timed_out"]
    assert r["exit_code"] != 0
    # subprocess: ~1 s. docker: 1 s after interpreter start, plus container start-up.
    assert r["duration_s"] < (3 if sandbox.name == "subprocess" else 8)


def test_memory_bomb_is_killed(sandbox):
    bomb = code("""
        chunks = []
        while True:
            chunks.append(bytearray(10 * 1024 * 1024))
        """)
    r = sandbox.run(bomb, timeout_s=20, memory_mb=128)
    assert not r["timed_out"], "must be stopped by the memory cap, not the clock"
    assert r["exit_code"] != 0
    # rlimit -> MemoryError (exit 1); cgroup OOM killer -> SIGKILL (137)
    assert "MemoryError" in r["stderr"] or r["exit_code"] == 137


@pytest.mark.parametrize("probe", [
    "import socket\nsocket.create_connection(('1.1.1.1', 53), timeout=5)\n",
    "import socket\nsocket.getaddrinfo('example.com', 80)\n",
    "import urllib.request\nurllib.request.urlopen('http://example.com', timeout=5)\n",
], ids=["tcp", "dns", "http"])
def test_network_call_fails(sandbox, probe):
    r = sandbox.run(probe, timeout_s=15, memory_mb=256)
    assert r["exit_code"] != 0 and not r["timed_out"]
    # e.g. OSError / ConnectionError / URLError / socket.gaierror
    assert "Traceback" in r["stderr"]


def test_output_is_capped(sandbox):
    sandbox.max_output_bytes = 1000
    try:
        r = sandbox.run("print('x' * 5000)\n", timeout_s=10, memory_mb=256)
    finally:
        sandbox.max_output_bytes = 1_000_000
    assert r["stdout"].endswith("[output truncated]")
    assert len(r["stdout"]) < 1100


@pytest.mark.linux
@pytest.mark.skipif(os.name != "posix", reason="rlimit backend needs POSIX")
def test_timeout_kills_child_processes(tmp_path):
    marker = tmp_path / "survived"
    orphan = code(f"""
        import subprocess, sys, time
        subprocess.Popen([sys.executable, "-c",
            "import time; time.sleep(2); open({str(marker)!r}, 'w').write('x')"])
        time.sleep(60)
        """)
    r = SubprocessSandbox().run(orphan, timeout_s=1, memory_mb=256)
    assert r["timed_out"]
    import time
    time.sleep(3)
    assert not marker.exists(), "child outlived the sandbox timeout"


def test_backend_chosen_by_config():
    assert isinstance(make_sandbox({"backend": "docker"}), DockerSandbox)
    sb = make_sandbox({"backend": "subprocess", "subprocess": {"network": "python-guard"}})
    assert isinstance(sb, SubprocessSandbox) and sb.network == "python-guard"
    with pytest.raises(ValueError, match="unknown sandbox backend"):
        make_sandbox({"backend": "vm"})


def test_default_config_loads():
    assert load_config()["sandbox"]["backend"] in ("docker", "subprocess")


def test_env_overrides_backend(monkeypatch):
    monkeypatch.setenv("VERIFIER_SANDBOX_BACKEND", "docker")
    assert isinstance(make_sandbox({"backend": "subprocess"}), DockerSandbox)
