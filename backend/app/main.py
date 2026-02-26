"""
FastAPI application entry point.

Middleware applied (in order):
  1. Request-ID injection — generates/propagates X-Request-ID
  2. Structured log context — binds request_id to every log line in the request

Routers:
  /v1/auth         — token exchange (Apple stub in dev)
  /v1/sessions     — session CRUD
  /v1/sessions     — message send + SSE stream (same prefix, different paths)
  /v1/safety       — safety report submission
  /v1/entitlements — subscription entitlements snapshot
  /v1/credits      — credit redemption
  /v1/analytics    — analytics event ingestion
"""
import uuid
from contextlib import asynccontextmanager

import structlog
import structlog.contextvars
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.logger import configure_logging, log
from app.routers import analytics, auth, credits, entitlements, messages, safety, sessions

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("server.start")
    yield
    log.info("server.stop")


app = FastAPI(
    title="Bible Therapist API",
    version="0.1.0",
    description="Bible-grounded reflection chat — MVP backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten before production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_and_logging_middleware(request: Request, call_next) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    log.info("request.start", method=request.method, path=request.url.path)
    response: Response = await call_next(request)
    log.info("request.end", status_code=response.status_code)

    response.headers["X-Request-ID"] = request_id
    return response


# Routers
app.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/v1/sessions", tags=["sessions"])
app.include_router(messages.router, prefix="/v1/sessions", tags=["messages"])
app.include_router(safety.router, prefix="/v1/safety", tags=["safety"])
app.include_router(entitlements.router, prefix="/v1", tags=["entitlements"])
app.include_router(credits.router, prefix="/v1", tags=["credits"])
app.include_router(analytics.router, prefix="/v1", tags=["analytics"])


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"ok": True}
