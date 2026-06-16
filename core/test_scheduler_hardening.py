"""Tests for the scheduler hardening (jobstore, overlap, failure counter, healthcheck)."""

from unittest import IsolatedAsyncioTestCase
import importlib

from sqlalchemy import text

from models import engine


class TestSchedulerJobStore(IsolatedAsyncioTestCase):
    def test_apscheduler_jobs_table_exists_in_public_schema(self):
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT table_schema, table_name FROM information_schema.tables "
                    "WHERE table_name = 'apscheduler_jobs'"
                )
            ).first()
        self.assertIsNotNone(row, "apscheduler_jobs table must exist")
        self.assertEqual(row.table_schema, "public")

    def test_register_jobs_persists_into_jobstore(self):
        from core.scheduler import (
            register_jobs,
            start_scheduler,
            stop_scheduler,
        )

        with engine.begin() as conn:
            conn.execute(text("DELETE FROM apscheduler_jobs"))

        register_jobs()
        start_scheduler()
        try:
            with engine.connect() as conn:
                stored_ids = [
                    row[0]
                    for row in conn.execute(
                        text("SELECT id FROM apscheduler_jobs ORDER BY id")
                    )
                ]
        finally:
            stop_scheduler()

        self.assertIn("cleanup_abandoned_watch_sessions", stored_ids)
        self.assertIn("sync_pending_payments", stored_ids)


class TestJobOverlapSafety(IsolatedAsyncioTestCase):
    def test_both_jobs_have_overlap_guards(self):
        from core.scheduler import register_jobs, scheduler

        register_jobs()
        jobs = {j.id: j for j in scheduler.get_jobs()}

        for job_id in ("cleanup_abandoned_watch_sessions", "sync_pending_payments"):
            self.assertIn(job_id, jobs)
            job = jobs[job_id]
            self.assertEqual(
                job.max_instances,
                1,
                f"{job_id} must not allow overlapping runs",
            )
            self.assertTrue(
                job.coalesce,
                f"{job_id} must coalesce missed runs",
            )


class TestTaskFailureMetric(IsolatedAsyncioTestCase):
    def test_record_task_failure_does_not_raise(self):
        from core.telemetry import record_task_failure

        record_task_failure("any_task")
        record_task_failure("any_task")
        record_task_failure("other_task")


class TestWorkerHealthcheck(IsolatedAsyncioTestCase):
    def test_health_endpoint_reports_scheduler_state(self):
        from fastapi.testclient import TestClient

        from core.scheduler import (
            register_jobs,
            start_scheduler,
            stop_scheduler,
        )
        from worker.scheduler import _build_health_app

        app = _build_health_app()
        client = TestClient(app)

        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["role"], "worker")

        register_jobs()
        start_scheduler()
        try:
            r = client.get("/health")
            body = r.json()
            self.assertEqual(body["status"], "ok")
            self.assertTrue(body["scheduler_running"])
            self.assertIn("sync_pending_payments", body["jobs"])
        finally:
            stop_scheduler()

    def test_worker_package_exposes_run_entrypoint(self):
        import inspect
        import sys

        if "worker.scheduler" in sys.modules:
            importlib.reload(sys.modules["worker.scheduler"])
        from worker.scheduler import run

        self.assertTrue(callable(run))
        sig = inspect.signature(run)
        self.assertIn("host", sig.parameters)
        self.assertIn("port", sig.parameters)


class TestSQLAlchemyJobStoreWiring(IsolatedAsyncioTestCase):
    def test_scheduler_uses_sqlalchemy_jobstore(self):
        from core.scheduler import scheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

        store = scheduler._jobstores.get("default")  # type: ignore[attr-defined]
        self.assertIsInstance(
            store,
            SQLAlchemyJobStore,
            "Default jobstore must be SQLAlchemyJobStore for persistence",
        )
