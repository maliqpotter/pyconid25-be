"""Tests for repository/tasks.py — the periodic scheduler entry points."""

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

import alembic.config

from models import db
from models.Payment import Payment, PaymentStatus
from models.Room import Room
from models.Schedule import Schedule
from models.Stream import Stream, StreamStatus
from models.StreamWatchSession import StreamWatchSession, WatchMode
from models.Ticket import Ticket
from models.User import User
from models import (  # noqa: F401  - imported to register all mappers
    Country,
    State,
    City,
    Token,
    RefreshToken,
    EmailVerification,
    ResetPassword,
    ScheduleType,
    Speaker,
    SpeakerType,
    Voucher,
    Organizer,
    OrganizerType,
    Volunteer,
)

from pytz import timezone

from settings import TZ
from repository import payment as payment_repo


def _now() -> datetime:
    return datetime.now(tz=timezone(TZ))


class _Base(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        alembic.config.main(argv=["upgrade", "head"])
        self.db = db()

        self.user = User(
            username=f"taskuser-{uuid.uuid4().hex[:8]}",
            email=f"task-{uuid.uuid4().hex[:8]}@example.com",
            phone="+628123456789",
            first_name="Task",
            last_name="Tester",
            password="x",
            is_active=True,
        )
        self.db.add(self.user)
        self.db.flush()

        self.ticket = Ticket(
            id=uuid.uuid4(),
            name="Task Test Ticket",
            price=100000,
            user_participant_type="In Person",
            is_sold_out=False,
            is_active=True,
            description="t",
        )
        self.db.add(self.ticket)
        self.db.flush()

        self.room = Room(
            name=f"room-{uuid.uuid4().hex[:6]}",
            created_at=_now(),
            updated_at=_now(),
        )
        self.db.add(self.room)
        self.db.flush()

        self.schedule = Schedule(
            id=uuid.uuid4(),
            room_id=self.room.id,
            title="Test Schedule",
            description="d",
            created_at=_now(),
            updated_at=_now(),
        )
        self.db.add(self.schedule)
        self.db.flush()

        self.stream = Stream(
            id=uuid.uuid4(),
            schedule_id=self.schedule.id,
            status=StreamStatus.STREAMING,
            is_public=True,
            created_at=_now(),
            updated_at=_now(),
        )
        self.db.add(self.stream)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.query(StreamWatchSession).filter(
            StreamWatchSession.user_id == self.user.id
        ).delete()
        self.db.query(Payment).filter(Payment.user_id == self.user.id).delete()
        self.db.query(Stream).filter(Stream.id == self.stream.id).delete()
        self.db.query(Schedule).filter(Schedule.id == self.schedule.id).delete()
        self.db.query(Room).filter(Room.id == self.room.id).delete()
        self.db.query(Ticket).filter(Ticket.id == self.ticket.id).delete()
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()


class TestTaskEndAbandonedWatchSessions(_Base):
    def _make_abandoned_session(
        self, last_heartbeat: datetime, ended_at: datetime | None = None
    ) -> StreamWatchSession:
        s = StreamWatchSession(
            id=uuid.uuid4(),
            stream_id=self.stream.id,
            schedule_id=self.schedule.id,
            user_id=self.user.id,
            mode=WatchMode.LIVE,
            client_session_id=f"cs-{uuid.uuid4().hex[:8]}",
            started_at=last_heartbeat,
            last_heartbeat_at=last_heartbeat,
            ended_at=ended_at,
            watched_seconds=0,
            last_position_seconds=0,
            qualified=False,
            created_at=last_heartbeat,
            updated_at=last_heartbeat,
        )
        self.db.add(s)
        self.db.commit()
        return s

    def test_idempotent_when_run_twice(self):
        abandoned_time = _now() - timedelta(minutes=10)
        self._make_abandoned_session(abandoned_time)
        self._make_abandoned_session(abandoned_time)
        self._make_abandoned_session(abandoned_time)

        from repository.tasks import task_end_abandoned_watch_sessions

        task_end_abandoned_watch_sessions()
        task_end_abandoned_watch_sessions()

        self.db.expire_all()
        ended_count = (
            self.db.query(StreamWatchSession)
            .filter(
                StreamWatchSession.user_id == self.user.id,
                StreamWatchSession.ended_at.isnot(None),
            )
            .count()
        )
        self.assertEqual(
            ended_count,
            3,
            "Exactly 3 sessions ended — no double-write from concurrent runs",
        )

    def test_does_not_end_active_sessions(self):
        active_time = _now() - timedelta(minutes=1)
        s = self._make_abandoned_session(active_time)
        s_id = s.id

        from repository.tasks import task_end_abandoned_watch_sessions

        task_end_abandoned_watch_sessions()

        self.db.expire_all()
        row = self.db.get(StreamWatchSession, s_id)
        self.assertIsNone(row.ended_at, "Active session must NOT be ended by the task")


class TestTaskSyncPendingPayments(_Base):
    def _make_unpaid_payment(self, mayar_id: str = "mayar-test-1") -> Payment:
        p = payment_repo.create_payment(
            db=self.db,
            user_id=str(self.user.id),
            ticket_id=str(self.ticket.id),
            amount=100000,
            description="task test payment",
            status=PaymentStatus.UNPAID,
            mayar_id=mayar_id,
            is_commit=False,
        )
        self.db.commit()
        return p

    def _mayar_response(self, status: str) -> dict:
        return {"statusCode": 200, "messages": "success", "data": {"status": status}}

    def test_calls_mayar_with_correct_payment_id(self):
        p1 = self._make_unpaid_payment(mayar_id="mayar-A")
        p2 = self._make_unpaid_payment(mayar_id="mayar-B")
        p1_id, p2_id = p1.id, p2.id

        mock_service = MagicMock()
        mock_service.get_payment_status = AsyncMock(
            side_effect=[
                self._mayar_response("unpaid"),
                self._mayar_response("paid"),
            ]
        )

        with patch("repository.tasks.MayarService", return_value=mock_service):
            from repository.tasks import task_sync_pending_payments

            task_sync_pending_payments()

        called_ids = {
            call.kwargs["payment_id"]
            for call in mock_service.get_payment_status.call_args_list
        }
        self.assertEqual(called_ids, {"mayar-A", "mayar-B"})

        self.db.expire_all()
        p1 = self.db.get(Payment, p1_id)
        p2 = self.db.get(Payment, p2_id)
        self.assertEqual(p1.status, PaymentStatus.UNPAID)
        self.assertEqual(p2.status, PaymentStatus.PAID)
        self.assertIsNotNone(
            p2.paid_at, "paid_at must be set when status flips to PAID"
        )

    def test_skips_payments_without_mayar_id(self):
        payment_repo.create_payment(
            db=self.db,
            user_id=str(self.user.id),
            ticket_id=str(self.ticket.id),
            amount=100000,
            description="no mayar",
            status=PaymentStatus.UNPAID,
            mayar_id=None,
            is_commit=False,
        )
        self.db.commit()

        mock_service = MagicMock()
        mock_service.get_payment_status = AsyncMock()

        with patch("repository.tasks.MayarService", return_value=mock_service):
            from repository.tasks import task_sync_pending_payments

            task_sync_pending_payments()

        mock_service.get_payment_status.assert_not_called()

    def test_does_not_write_when_mayar_status_matches_db(self):
        for mayar_id in ("mayar-stay-A", "mayar-stay-B"):
            payment_repo.create_payment(
                db=self.db,
                user_id=str(self.user.id),
                ticket_id=str(self.ticket.id),
                amount=100000,
                description="synced",
                status=PaymentStatus.UNPAID,
                mayar_id=mayar_id,
                is_commit=False,
            )
        self.db.commit()

        mock_service = MagicMock()
        mock_service.get_payment_status = AsyncMock(
            side_effect=[
                self._mayar_response("unpaid"),
                self._mayar_response("unpaid"),
            ]
        )

        with (
            patch("repository.tasks.MayarService", return_value=mock_service),
            patch("repository.tasks.update_payment") as mock_update,
        ):
            from repository.tasks import task_sync_pending_payments

            task_sync_pending_payments()

        mock_update.assert_not_called()
        self.assertEqual(
            mock_service.get_payment_status.call_count,
            2,
            "Mayar is queried (we have to ask), but no DB write happens",
        )

    def test_mayar_exception_on_one_payment_does_not_break_others(self):
        p1 = self._make_unpaid_payment(mayar_id="mayar-ok")
        p2 = self._make_unpaid_payment(mayar_id="mayar-broken")

        p1_id, p2_id = p1.id, p2.id

        mock_service = MagicMock()
        mock_service.get_payment_status = AsyncMock(
            side_effect=[
                self._mayar_response("paid"),
                RuntimeError("Mayar 500"),
            ]
        )

        with patch("repository.tasks.MayarService", return_value=mock_service):
            from repository.tasks import task_sync_pending_payments

            task_sync_pending_payments()

        self.db.expire_all()
        p1 = self.db.get(Payment, p1_id)
        p2 = self.db.get(Payment, p2_id)
        self.assertEqual(p1.status, PaymentStatus.PAID, "p1 must still be updated")
        self.assertEqual(p2.status, PaymentStatus.UNPAID, "p2 left untouched")

    async def test_concurrent_workers_do_not_corrupt_db(self):
        for mayar_id in ("mayar-w1", "mayar-w2", "mayar-w3"):
            self._make_unpaid_payment(mayar_id=mayar_id)

        responses_by_id = {
            "mayar-w1": self._mayar_response("paid"),
            "mayar-w2": self._mayar_response("closed"),
            "mayar-w3": self._mayar_response("unpaid"),
        }

        def service_factory(*args, **kwargs):
            svc = MagicMock()

            async def _side_effect(payment_id, **_kw):
                return responses_by_id[payment_id]

            svc.get_payment_status = AsyncMock(side_effect=_side_effect)
            return svc

        with patch("repository.tasks.MayarService", side_effect=service_factory):
            from repository.tasks import async_sync_pending_payments

            await asyncio.gather(
                async_sync_pending_payments(),
                async_sync_pending_payments(),
                async_sync_pending_payments(),
                async_sync_pending_payments(),
            )

        self.db.expire_all()
        statuses = dict(
            self.db.query(Payment.mayar_id, Payment.status)
            .filter(Payment.mayar_id.in_(["mayar-w1", "mayar-w2", "mayar-w3"]))
            .all()
        )
        self.assertEqual(statuses["mayar-w1"], PaymentStatus.PAID.value)
        self.assertEqual(statuses["mayar-w2"], PaymentStatus.CLOSED.value)
        self.assertEqual(statuses["mayar-w3"], PaymentStatus.UNPAID.value)


class TestTaskFailureMetric(_Base):
    def test_abandoned_sessions_failure_increments_counter(self):
        from repository.tasks import task_end_abandoned_watch_sessions

        with (
            patch(
                "repository.tasks.end_abandoned_sessions",
                side_effect=RuntimeError("db boom"),
            ),
            patch("repository.tasks.record_task_failure") as mock_record,
        ):
            task_end_abandoned_watch_sessions()

        mock_record.assert_called_once_with("task_end_abandoned_watch_sessions")

    def test_sync_payments_failure_increments_counter(self):
        from repository.tasks import task_sync_pending_payments

        with patch(
            "repository.tasks.MayarService",
            side_effect=RuntimeError("mayar service init boom"),
        ):
            with patch("repository.tasks.record_task_failure") as mock_record:
                task_sync_pending_payments()

        mock_record.assert_called_once_with("task_sync_pending_payments")
