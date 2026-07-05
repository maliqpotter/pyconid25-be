"""Tests that the web and worker tiers are physically separated."""

from unittest import IsolatedAsyncioTestCase


class TestWebProcessDoesNotStartScheduler(IsolatedAsyncioTestCase):
    def test_main_does_not_import_scheduler_or_worker(self):
        import ast
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        main_source = (repo_root / "main.py").read_text()
        tree = ast.parse(main_source)

        forbidden_imports = {"scheduler", "worker"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    self.assertNotIn(
                        top,
                        forbidden_imports,
                        f"main.py must not import '{top}' (would couple "
                        "the web tier to the scheduler). "
                        f"Found: from {node.module} import ...",
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    self.assertNotIn(
                        top,
                        forbidden_imports,
                        f"main.py must not import '{top}'.",
                    )

    def test_worker_module_runs_in_isolation(self):
        import importlib
        import sys

        if "worker.scheduler" in sys.modules:
            worker_scheduler = importlib.reload(sys.modules["worker.scheduler"])
        else:
            worker_scheduler = importlib.import_module("worker.scheduler")

        self.assertTrue(
            callable(getattr(worker_scheduler, "run", None)),
            "worker.scheduler must expose a run() entrypoint",
        )
        self.assertTrue(
            callable(getattr(worker_scheduler, "register_jobs", None)),
            "worker.scheduler must expose register_jobs()",
        )
