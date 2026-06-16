from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler

from core.log import logger
from models import Base, engine

_jobstore = SQLAlchemyJobStore(
    engine=engine,
    tablename="apscheduler_jobs",
    metadata=Base.metadata,
    tableschema="public",
)
scheduler = BackgroundScheduler(jobstores={"default": _jobstore})


def register_jobs() -> None:
    from repository.tasks import (
        task_end_abandoned_watch_sessions,
        task_sync_pending_payments,
    )
    from settings import (
        SCHEDULER_ABANDONED_SESSIONS_MIN,
        SCHEDULER_SYNC_PAYMENTS_MIN,
    )

    scheduler.add_job(
        task_end_abandoned_watch_sessions,
        "interval",
        minutes=SCHEDULER_ABANDONED_SESSIONS_MIN,
        id="cleanup_abandoned_watch_sessions",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        task_sync_pending_payments,
        "interval",
        minutes=SCHEDULER_SYNC_PAYMENTS_MIN,
        id="sync_pending_payments",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("Background scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler stopped")
