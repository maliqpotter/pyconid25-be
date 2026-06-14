from repository.stream_watch import end_abandoned_sessions
from repository.payment import update_payment
from core.mayar_service import MayarService
from settings import MAYAR_API_KEY, MAYAR_BASE_URL
from models.Payment import PaymentStatus
from models import db as db_factory
from core.log import logger
import asyncio


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


async def async_sync_pending_payments():
    db = db_factory()
    mayar_service = MayarService(api_key=MAYAR_API_KEY, base_url=MAYAR_BASE_URL)
    try:
        from sqlalchemy import select
        from models.Payment import Payment

        stmt = select(Payment).where(Payment.status == PaymentStatus.UNPAID.value)
        unpaid_payments = db.execute(stmt).scalars().all()

        sync_count = 0
        for payment in unpaid_payments:
            if not payment.mayar_id:
                continue

            try:
                mayar_status_response = await mayar_service.get_payment_status(
                    payment_id=payment.mayar_id
                )
                data = mayar_status_response.get("data", {})
                transaction_status = data.get("status", "").lower()

                status_mapping = {
                    "unpaid": PaymentStatus.UNPAID,
                    "paid": PaymentStatus.PAID,
                    "closed": PaymentStatus.CLOSED,
                }

                new_status = status_mapping.get(
                    transaction_status, PaymentStatus.UNPAID
                )

                if new_status != payment.status:
                    update_payment(
                        db=db, payment=payment, status=new_status, is_commit=False
                    )
                    sync_count += 1
            except Exception as e:
                logger.error(f"Failed checking mayar status for {payment.id}: {e}")

        if sync_count > 0:
            db.commit()
            logger.info(f"Synced {sync_count} pending payment statuses from Mayar.")
    except Exception as e:
        logger.error(f"Error executing task_sync_pending_payments: {e}")
    finally:
        db.close()


def task_sync_pending_payments():
    """
    Periodic task to check UNPAID payments directly to Mayar API
    and update their statuses if closed or paid.
    """
    asyncio.run(async_sync_pending_payments())
