# LLM Inference Gateway

An OpenAI-compatible gateway that sits in front of LLM backends (Ollama locally, vLLM or a hosted API). The goal is to make LLM traffic safe to share between many clients: authenticated, rate-limited, held to a token budget even under concurrent requests, resilient to a failing backend, and measured.

> **Status:** Milestone 1 in progress. `/health`, API-key auth and `/v1/chat/completions` passthrough (streaming and non-streaming) work and are covered by tests against a fake upstream. Nothing below Milestone 1 is built yet, and no performance numbers exist yet. Numbers will appear here only after they're measured, with the command and environment that produced them.

## Run it

```bash
uv sync
uv run pytest
ollama serve                      # in another terminal; then `ollama pull llama3.2`
uv run uvicorn gateway.main:app --reload --app-dir src
curl localhost:8000/v1/chat/completions -H "Authorization: Bearer dev-key" \
  -d '{"model":"llama3.2","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

`docker compose up --build` runs the gateway with Redis and Postgres (unused until Milestone 2).

## Milestones

1. **Passthrough (week 1).** OpenAI-compatible `/v1/chat/completions`, SSE streaming relay, API keys, upstream errors surfaced. Next: move keys to Postgres, record per-request usage (prompt/completion tokens, latency).
2. **Correct under concurrency (week 2).**
   - Per-key token-bucket rate limit in Redis (atomic Lua script).
   - Per-key token **budget that can't be overspent** when many requests race. This is the central correctness property. Reserve an estimate before forwarding, settle actual usage after, release on failure.
   - Concurrency cap with backpressure (429 / 503 + `Retry-After`) instead of an unbounded queue.
   - Idempotency keys; retry and fallback to a second backend on 5xx/timeouts.
   - Tests that fire N concurrent requests at a small budget and assert it is never exceeded.
3. **Measured (week 3).**
   - Prometheus metrics: TTFT, tokens/sec, request latency, 429/error rates.
   - Exact-match response cache; compare hit vs miss latency.
   - Load test (k6 or Locust) at several concurrency levels; report p50/p99 with the config and raw output committed in `loadtest/`.
   - Write-up: design, failure modes, trade-offs, what the bottleneck turned out to be.

Stretch: route by model/backend load, compare against vLLM continuous batching on a rented GPU, prefix-aware routing.

## Layout

- `src/gateway/main.py`: app factory, auth, proxy routes
- `src/gateway/config.py`: settings from `GATEWAY_*` env vars
- `tests/`: pytest against an `httpx.MockTransport` fake upstream
- `loadtest/`: load-test scripts and results (Milestone 3)
