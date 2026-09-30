#!/usr/bin/env bash
# Local CPU model server for the pilot (WSL2): llama.cpp's OpenAI-compatible
# server in Docker, serving Qwen2.5-Coder-1.5B-Instruct (GGUF q4_k_m).
#
#   scripts/serve_local_llm.sh download   # fetch GGUF, verify sha256 against HF
#   scripts/serve_local_llm.sh start      # run container on 127.0.0.1:$PORT
#   scripts/serve_local_llm.sh smoke      # determinism + usage + throughput check
#   scripts/serve_local_llm.sh stop
#
# Then:  export VERIFIER_BASE_URL=http://127.0.0.1:8080/v1
#        export VERIFIER_MODEL=qwen2.5-coder-1.5b-instruct-q4km
#
# Determinism: --parallel 1 (one slot, no cross-request batching) and the
# client sends cache_prompt=false (configs/pilot_local.toml); each request
# carries its own seed.
set -euo pipefail

REPO="Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF"
FILE="qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
ALIAS="qwen2.5-coder-1.5b-instruct-q4km"
# Pinned by digest (resolved from :server on 2026-09-30; image is ~1.2 GB).
IMAGE="${LLAMA_IMAGE:-ghcr.io/ggml-org/llama.cpp@sha256:f9115c95639e60abc09d4ea83b26fd4d56c66aa1174594393335a514da00c283}"
# GGUF sha256 is verified against the HF API at download time; on 2026-09-30:
# cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046
MODELS="${MODELS_DIR:-$HOME/models}"
PORT="${PORT:-8080}"
THREADS="${THREADS:-8}"
NAME="fyp-llm"

expected_sha() {
  curl -fsSL "https://huggingface.co/api/models/$REPO/tree/main" | python3 -c '
import json, sys
f = sys.argv[1]
for e in json.load(sys.stdin):
    if e.get("path") == f:
        print(e["lfs"]["oid"]); break
else:
    sys.exit("file not listed by HF API")' "$FILE"
}

case "${1:-}" in
  download)
    mkdir -p "$MODELS"
    want=$(expected_sha)
    if [ ! -f "$MODELS/$FILE" ]; then
      curl -fL --retry 3 -o "$MODELS/$FILE.part" \
        "https://huggingface.co/$REPO/resolve/main/$FILE"
      mv "$MODELS/$FILE.part" "$MODELS/$FILE"
    fi
    got=$(sha256sum "$MODELS/$FILE" | cut -d' ' -f1)
    if [ "$got" != "$want" ]; then
      echo "sha256 mismatch: got $got, HF says $want" >&2; exit 1
    fi
    echo "ok $FILE sha256=$got"
    ;;
  start)
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    docker run -d --name "$NAME" -p "127.0.0.1:$PORT:8080" \
      -v "$MODELS:/models:ro" "$IMAGE" \
      -m "/models/$FILE" --alias "$ALIAS" --host 0.0.0.0 --port 8080 \
      --parallel 1 --jinja -c 4096 --threads "$THREADS"
    for _ in $(seq 60); do
      curl -fs "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && { echo "up on :$PORT"; exit 0; }
      sleep 2
    done
    echo "server did not become healthy; see: docker logs $NAME" >&2; exit 1
    ;;
  smoke)
    BASE="http://127.0.0.1:$PORT/v1"
    req() {
      curl -fs "$BASE/chat/completions" -H 'Content-Type: application/json' -d "{
        \"model\": \"$ALIAS\", \"seed\": 7, \"temperature\": 0.8, \"max_tokens\": 128,
        \"cache_prompt\": false,
        \"messages\": [{\"role\": \"user\", \"content\": \"Write a Python function that reverses a string.\"}]}"
    }
    a=$(req); b=$(req)
    python3 - "$a" "$b" <<'EOF'
import json, sys
a, b = (json.loads(x) for x in sys.argv[1:3])
ta, tb = a["choices"][0]["message"]["content"], b["choices"][0]["message"]["content"]
u, t = a["usage"], a.get("timings", {})
print("deterministic (same seed twice):", ta == tb)
print("usage:", u)
if t:
    print(f"prompt {t.get('prompt_per_second', 0):.0f} tok/s, generation {t.get('predicted_per_second', 0):.1f} tok/s")
sys.exit(0 if ta == tb and u.get("completion_tokens") else 1)
EOF
    ;;
  stop)
    docker rm -f "$NAME"
    ;;
  *)
    sed -n '2,13p' "$0"; exit 2
    ;;
esac
