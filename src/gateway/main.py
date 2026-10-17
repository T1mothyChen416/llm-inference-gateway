from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from gateway.config import Settings


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """Build the app. `transport` lets tests swap in a fake upstream."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        headers = {"Authorization": f"Bearer {settings.upstream_api_key}"} if settings.upstream_api_key else {}
        app.state.upstream = httpx.AsyncClient(
            base_url=settings.upstream_base_url,
            headers=headers,
            timeout=settings.upstream_timeout_s,
            transport=transport,
        )
        yield
        await app.state.upstream.aclose()

    app = FastAPI(title="LLM Inference Gateway", lifespan=lifespan)
    valid_keys = settings.key_set()

    @app.exception_handler(httpx.TransportError)
    async def upstream_unreachable(request: Request, exc: httpx.TransportError) -> JSONResponse:
        # TODO(milestone 2): retry / fall back to a second backend before giving up.
        status = 504 if isinstance(exc, httpx.TimeoutException) else 502
        return JSONResponse(status_code=status, content={"error": f"upstream unavailable: {type(exc).__name__}"})

    def require_key(authorization: str = Header(default="")) -> str:
        scheme, _, key = authorization.partition(" ")
        if scheme.lower() != "bearer" or key not in valid_keys:
            raise HTTPException(status_code=401, detail="invalid API key")
        return key

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request, api_key: str = Depends(require_key)):
        body = await request.json()
        upstream: httpx.AsyncClient = request.app.state.upstream

        # TODO(milestone 2): rate limit + token quota check for api_key before forwarding.
        # TODO(milestone 2): record usage after the response (prompt/completion tokens).

        if body.get("stream"):
            req = upstream.build_request("POST", "/chat/completions", json=body)
            resp = await upstream.send(req, stream=True)
            if resp.status_code != 200:
                content = await resp.aread()
                await resp.aclose()
                return JSONResponse(status_code=resp.status_code, content={"error": content.decode(errors="replace")})

            async def relay() -> AsyncIterator[bytes]:
                try:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
                finally:
                    await resp.aclose()

            return StreamingResponse(relay(), media_type="text/event-stream")

        resp = await upstream.post("/chat/completions", json=body)
        if resp.status_code != 200:
            return JSONResponse(status_code=resp.status_code, content={"error": resp.text})
        return JSONResponse(content=resp.json())

    return app


app = create_app()
