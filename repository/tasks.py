from repository.stream_watch import end_abandoned_sessions
from models import db as db_factory
from core.log import logger

def task_end_abandoned_watch_sessions():
    """
    Periodic task to clean up 'abandoned' watch sessions
    where users disconnected without properly ending their session.
    """
    db = db_factory()
    try:
        count = end_abandoned_sessions(db, timeout_minutes=5)
        if count > 0:
            logger.info(f"Cleaned up {count} abandoned watch sessions.")
    except Exception as e:
        logger.error(f"Error executing task_end_abandoned_watch_sessions: {e}")
    finally:
        db.close()
