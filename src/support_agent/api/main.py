"""FastAPI application exposing the support agent.

Run locally:  uv run uvicorn support_agent.api.main:app --reload --port 8000
"""

import logging
import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from openai import APIError

from support_agent.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    HistoryMessage,
    HistoryResponse,
    ThreadId,
    TicketOut,
)
from support_agent.config import get_settings
from support_agent.graph.builder import get_graph
from support_agent.service import get_history, list_tickets, run_turn

logger = logging.getLogger("support_agent.api")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(provided: str | None = Security(api_key_header)) -> None:
    expected = get_settings().api_key
    if expected is None or not expected.get_secret_value():
        return  # Auth disabled (local development only)
    if provided is None or not secrets.compare_digest(
        provided, expected.get_secret_value()
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    get_graph()  # Warm up: compile the graph and open the checkpointer once
    logger.info("Support agent API ready")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Support Resolution Agent API",
        description="AI customer support agent that resolves orders, returns and refunds.",
        version="1.0.0",
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
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "The AI service is temporarily unavailable. Please retry shortly."
            },
        )

    protected = [Depends(require_api_key)]

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", model=settings.openai_model)

    @app.post(
        "/v1/chat", response_model=ChatResponse, dependencies=protected, tags=["chat"]
    )
    def chat(body: ChatRequest) -> ChatResponse:
        thread_id = body.thread_id or uuid.uuid4().hex
        result = run_turn(body.message, thread_id)
        logger.info(
            "thread=%s intent=%s tools=%s", thread_id, result.intent, result.tools_used
        )
        return ChatResponse(
            thread_id=thread_id,
            reply=result.reply,
            intent=result.intent,
            sentiment=result.sentiment,
            tools_used=result.tools_used,
        )

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
        "/v1/tickets",
        response_model=list[TicketOut],
        dependencies=protected,
        tags=["tickets"],
    )
    def tickets(limit: int = Query(default=50, ge=1, le=200)) -> list[TicketOut]:
        return [TicketOut.model_validate(t) for t in list_tickets(limit)]

    return app


app = create_app()
