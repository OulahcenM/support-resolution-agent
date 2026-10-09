"""API contract tests: auth, validation and non-LLM endpoints."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from support_agent.api.main import app
from support_agent.tools import escalate_to_human
from tests.conftest import TEST_API_KEY

AUTH = {"X-API-Key": TEST_API_KEY}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_redirects_to_docs(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/docs"


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong-key"}])
def test_chat_rejects_missing_or_invalid_key(client: TestClient, headers: dict) -> None:
    response = client.post("/v1/chat", json={"message": "hi"}, headers=headers)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"message": ""},
        {"message": "   "},
        {"message": "x" * 2001},
        {"message": "hi", "thread_id": "short"},
        {"message": "hi", "thread_id": "../../etc/passwd"},
    ],
)
def test_chat_rejects_invalid_input(client: TestClient, payload: dict) -> None:
    assert client.post("/v1/chat", json=payload, headers=AUTH).status_code == 422


def test_tickets_endpoint_lists_escalations(client: TestClient) -> None:
    escalate_to_human.invoke(
        {"summary": "Lost package", "category": "lost_package", "priority": "high"},
        config={"configurable": {"thread_id": "api-test-thread"}},
    )
    response = client.get("/v1/tickets", headers=AUTH)
    assert response.status_code == 200
    assert any(t["thread_id"] == "api-test-thread" for t in response.json())


def test_tickets_endpoint_requires_key(client: TestClient) -> None:
    assert client.get("/v1/tickets").status_code == 401
