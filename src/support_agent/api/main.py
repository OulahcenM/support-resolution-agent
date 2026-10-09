"""FastAPI application exposing the support agent.

Run locally:  uv run uvicorn support_agent.api.main:app --reload --port 8000
"""

import asyncio
import json
import logging
import secrets
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from openai import APIError

from support_agent.api.rate_limit import SlidingWindowRateLimiter, public_rate_limit_dependency
from support_agent.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    HistoryMessage,
    HistoryResponse,
    ThreadId,
    TicketOut,
)
from support_agent.bootstrap import demo_reset_loop
from support_agent.config import get_settings
from support_agent.graph.builder import get_graph
from support_agent.service import get_history, list_tickets, run_turn, stream_turn

logger = logging.getLogger("support_agent.api")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

LLM_UNAVAILABLE = "The AI service is temporarily unavailable. Please retry shortly."
SECONDS_PER_DAY = 86_400


def require_api_key(provided: str | None = Security(api_key_header)) -> None:
    expected = get_settings().api_key
    if expected is None or not expected.get_secret_value():
        return  # Auth disabled (local development only)
    if provided is None or not secrets.compare_digest(provided, expected.get_secret_value()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    get_graph()  # Warm up: compile the graph and open the checkpointer once

    reset_task = None
    if settings.demo_mode:
        reset_task = asyncio.create_task(demo_reset_loop(settings.demo_reset_hours))
        logger.info("Demo mode on: data resets every %s hours", settings.demo_reset_hours)

    logger.info("Support agent API ready")
    yield

    if reset_task:
        reset_task.cancel()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _event_stream(message: str, thread_id: str, channel: str) -> StreamingResponse:
    """Server-Sent Events: `token` events while writing, then one `done` (or `error`) event."""

    def events() -> Iterator[str]:
        try:
            for event in stream_turn(message, thread_id):
                if event["type"] == "done":
                    logger.info(
                        "channel=%s thread=%s intent=%s tools=%s",
                        channel,
                        thread_id,
                        event["intent"],
                        event["tools_used"],
                    )
                yield _sse(event)
        except APIError as exc:
            logger.error("LLM provider error: %s", exc)
            yield _sse({"type": "error", "detail": LLM_UNAVAILABLE})
        except Exception:
            logger.exception("Streaming turn failed (thread=%s)", thread_id)
            yield _sse({"type": "error", "detail": "Something went wrong. Please try again."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Support Resolution Agent API",
        description="AI customer support agent that resolves orders, returns and refunds.",
        version="1.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

    @app.exception_handler(APIError)
    async def handle_llm_error(_: Request, exc: APIError) -> JSONResponse:
        logger.error("LLM provider error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": LLM_UNAVAILABLE}
        )

    protected = [Depends(require_api_key)]
    public_limited = [
        Depends(
            public_rate_limit_dependency(
                per_ip=SlidingWindowRateLimiter(
                    settings.public_rate_limit, settings.public_rate_window_seconds
                ),
                global_cap=SlidingWindowRateLimiter(settings.public_daily_cap, SECONDS_PER_DAY),
            )
        )
    ]

    # --- System -----------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/demo/")

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", model=settings.openai_model)

    # --- Private API (server-to-server, agent console) ------------------------------

    @app.post("/v1/chat", response_model=ChatResponse, dependencies=protected, tags=["chat"])
    def chat(body: ChatRequest) -> ChatResponse:
        thread_id = body.thread_id or uuid.uuid4().hex
        result = run_turn(body.message, thread_id)
        logger.info(
            "channel=api thread=%s intent=%s tools=%s", thread_id, result.intent, result.tools_used
        )
        return ChatResponse(**asdict(result))

    @app.post("/v1/chat/stream", dependencies=protected, tags=["chat"])
    def chat_stream(body: ChatRequest) -> StreamingResponse:
        return _event_stream(body.message, body.thread_id or uuid.uuid4().hex, channel="api")

    @app.get(
        "/v1/threads/{thread_id}/messages",
        response_model=HistoryResponse,
        dependencies=protected,
        tags=["chat"],
    )
    def thread_messages(thread_id: ThreadId) -> HistoryResponse:
        return HistoryResponse(
            thread_id=thread_id,
            messages=[HistoryMessage(**m) for m in get_history(thread_id)],
        )

    @app.get(
        "/v1/tickets", response_model=list[TicketOut], dependencies=protected, tags=["tickets"]
    )
    def tickets(limit: int = Query(default=50, ge=1, le=200)) -> list[TicketOut]:
        return [TicketOut.model_validate(t) for t in list_tickets(limit)]

    # --- Public API (browser widget: no key, rate limited) --------------------------

    @app.post("/public/v1/chat/stream", dependencies=public_limited, tags=["public"])
    def public_chat_stream(body: ChatRequest) -> StreamingResponse:
        if not settings.public_chat_enabled:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return _event_stream(body.message, body.thread_id or uuid.uuid4().hex, channel="widget")

    # --- Static: embeddable widget + demo store --------------------------------------

    widget_dir, demo_dir = settings.web_dir / "widget", settings.web_dir / "demo"
    if widget_dir.is_dir():
        app.mount("/widget", StaticFiles(directory=widget_dir), name="widget")
    if demo_dir.is_dir():
        app.mount("/demo", StaticFiles(directory=demo_dir, html=True), name="demo")

    return app


app = create_app()
