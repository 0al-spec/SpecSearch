from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from .embeddings import EmbeddingError
from .models import SearchRequest, StrictModel


class VerifyRequest(StrictModel):
    record_id: str = Field(min_length=1, max_length=128)
    snapshot: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


def create_app(service):
    app = FastAPI(title="SpecSearch", version="0.1.0")
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        from starlette.responses import JSONResponse

        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.headers.get('host')}"
        if origin and origin != expected:
            return JSONResponse({"detail": "cross_origin_denied"}, status_code=403)
        if request.method == "POST":
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "json_required"}, status_code=415)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 16_384:
                    return JSONResponse({"detail": "body_too_large"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/v1/status")
    def status():
        return service.status()

    @app.post("/v1/search")
    def search(body: SearchRequest):
        try:
            return service.search(body)
        except LookupError:
            raise HTTPException(503, "index_not_built") from None
        except EmbeddingError:
            raise HTTPException(503, "vector_search_unavailable") from None
        except ValueError:
            raise HTTPException(422, "invalid_query") from None

    @app.get("/v1/packages/{record_id}")
    def package(record_id: str, snapshot: str | None = None):
        try:
            return service.store.package(record_id, snapshot).public()
        except (LookupError, ValueError):
            raise HTTPException(404, "package_not_found") from None

    @app.post("/v1/verify")
    def verify(body: VerifyRequest):
        try:
            return service.verify(body.record_id, body.snapshot)
        except LookupError:
            raise HTTPException(404, "package_not_found") from None

    static = Path(__file__).parent / "static"
    if static.exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="ui")
    return app
