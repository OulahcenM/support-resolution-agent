"""Container startup and demo maintenance. Safe to run on every boot.

Run:  python -m support_agent.bootstrap
"""

import asyncio
import logging

from sqlalchemy import inspect

from support_agent.config import get_settings
from support_agent.db.seed import seed
from support_agent.db.session import get_engine
from support_agent.rag.ingest import ingest
from support_agent.rag.store import get_vector_store

logger = logging.getLogger(__name__)


def _database_is_empty() -> bool:
    return not inspect(get_engine()).has_table("orders")


def _index_is_empty() -> bool:
    return not get_vector_store().get(limit=1)["ids"]


def bootstrap() -> None:
    settings = get_settings()
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)

    if settings.demo_mode or _database_is_empty():
        seed()
        logger.info("Demo store data seeded")
    if _index_is_empty():
        count = ingest()
        logger.info("Knowledge base indexed (%d chunks)", count)


async def demo_reset_loop(interval_hours: float) -> None:
    """Periodically reseed so relative dates stay realistic and demo actions are undone."""
    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            await asyncio.to_thread(seed)
            logger.info("Demo data reset")
        except Exception:
            logger.exception("Demo data reset failed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    bootstrap()
