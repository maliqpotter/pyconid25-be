"""Background scheduler entrypoint. Run via `python -m worker`."""

from __future__ import annotations

import signal
import threading

from fastapi import FastAPI
from uvicorn import Config, Server

from core.log import logger
from core.scheduler import (
    register_jobs,
    scheduler,
    start_scheduler,
    stop_scheduler,
)
from settings import (
    SCHEDULER_ABANDONED_SESSIONS_MIN,
    SCHEDULER_SYNC_PAYMENTS_MIN,
)


def _build_health_app() -> FastAPI:
    app = FastAPI(
        title="pyconid25-be worker",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health")
    def health():
        return {
            "status": "ok" if scheduler.running else "degraded",
            "role": "worker",
            "scheduler_running": scheduler.running,
            "jobs": [j.id for j in scheduler.get_jobs()],
        }

    return app


def run(host: str = "0.0.0.0", port: int = 8001) -> None:
    health_app = _build_health_app()
    shutdown_event = threading.Event()

    def _shutdown(signum: int, _frame) -> None:
        logger.info("Received signal %s, shutting down worker", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    register_jobs()
    start_scheduler()
    logger.info(
        "Scheduler running (abandoned_sessions=%sm, sync_payments=%sm)",
        SCHEDULER_ABANDONED_SESSIONS_MIN,
        SCHEDULER_SYNC_PAYMENTS_MIN,
    )

    config = Config(
        health_app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True, name="uvicorn")
    server_thread.start()
    logger.info("Worker healthcheck listening on %s:%s", host, port)

    try:
        shutdown_event.wait()
    finally:
        logger.info("Stopping healthcheck server and scheduler")
        server.should_exit = True
        server_thread.join(timeout=5)
        stop_scheduler()
