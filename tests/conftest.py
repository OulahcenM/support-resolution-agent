"""Test configuration: isolated databases, tracing off, optional LLM evals.

Environment is set at import time, BEFORE any support_agent module reads settings.
"""

import os
import tempfile
from pathlib import Path

import pytest
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)  # real OpenAI key for evals, if present

_TMP_DIR = Path(tempfile.mkdtemp(prefix="support-agent-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP_DIR / 'store.db').as_posix()}"
os.environ["CHECKPOINT_DB_PATH"] = str(_TMP_DIR / "checkpoints.db")
os.environ["API_KEY"] = "test-api-key"
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-used")  # CI has no real key

TEST_API_KEY = "test-api-key"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-evals", action="store_true", default=False, help="Run LLM end-to-end evals"
    )


def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("--run-evals"):
        os.environ["LANGSMITH_PROJECT"] = "support-resolution-agent-evals"
    else:
        os.environ["LANGSMITH_TRACING"] = "false"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-evals"):
        return
    skip_eval = pytest.mark.skip(reason="LLM eval — run with --run-evals")
    for item in items:
        if "eval" in item.keywords:
            item.add_marker(skip_eval)


@pytest.fixture(autouse=True)
def seeded_db() -> None:
    """Fresh, deterministic store data for every test."""
    from support_agent.db.seed import seed

    seed()
