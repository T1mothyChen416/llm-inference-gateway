import json

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway.config import Settings
from gateway.main import create_app

COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
}
SSE = b'data: {"choices":[{"delta":{"content":"h"}}]}\n\ndata: {"choices":[{"delta":{"content":"i"}}]}\n\ndata: [DONE]\n\n'


def fake_upstream(request: httpx.Request) -> httpx.Response:
    assert request.url.path.endswith("/chat/completions")
    body = json.loads(request.content)
    if body.get("model") == "unreachable":
        raise httpx.ConnectError("connection refused", request=request)
    if body.get("model") == "slow":
        raise httpx.ReadTimeout("timed out", request=request)
    if body.get("model") == "broken":
        return httpx.Response(503, text="backend unavailable")
    if body.get("stream"):
        return httpx.Response(200, content=SSE, headers={"content-type": "text/event-stream"})
    return httpx.Response(200, json=COMPLETION)


@pytest.fixture
def client():
    app = create_app(Settings(api_keys="k1,k2"), transport=httpx.MockTransport(fake_upstream))
    with TestClient(app) as c:
        yield c


AUTH = {"Authorization": "Bearer k1"}
MSG = {"model": "llama3.2", "messages": [{"role": "user", "content": "hello"}]}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "k1"}])
def test_rejects_bad_keys(client, headers):
    assert client.post("/v1/chat/completions", json=MSG, headers=headers).status_code == 401


def test_non_streaming_passthrough(client):
    r = client.post("/v1/chat/completions", json=MSG, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["usage"]["total_tokens"] == 4


def test_streaming_passthrough(client):
    with client.stream("POST", "/v1/chat/completions", json={**MSG, "stream": True}, headers=AUTH) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert b"".join(r.iter_bytes()) == SSE


def test_upstream_error_is_surfaced(client):
    r = client.post("/v1/chat/completions", json={**MSG, "model": "broken"}, headers=AUTH)
    assert r.status_code == 503


def test_streaming_upstream_error_is_surfaced(client):
    r = client.post("/v1/chat/completions", json={**MSG, "model": "broken", "stream": True}, headers=AUTH)
    assert r.status_code == 503
    assert "backend unavailable" in r.json()["error"]


@pytest.mark.parametrize("model,status", [("unreachable", 502), ("slow", 504)])
@pytest.mark.parametrize("stream", [False, True])
def test_unreachable_upstream_maps_to_gateway_error(client, model, status, stream):
    r = client.post("/v1/chat/completions", json={**MSG, "model": model, "stream": stream}, headers=AUTH)
    assert r.status_code == status
