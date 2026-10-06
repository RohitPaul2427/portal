"""Run all idempotent startup seeds/migrations once, then exit.

Use this as a deploy step instead of running migrations on every app boot:

    cd backend && python -m migrations.run_all

then start the API with RUN_STARTUP_MIGRATIONS=0.
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("LEAMSS_DISABLE_SCHEDULER", "1")


async def _main() -> None:
    import server  # noqa: WPS433  (imports routers + config)

    await server.run_startup_tasks(run_migrations=True)
    logging.getLogger("leamss.migrations").info("All startup migrations completed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_main())
