from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from system_explorer.cli import main
from system_explorer.scanner import ScanTimeBudgetExceeded, scan
from system_explorer.store import Store


class ScanRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "state" / "evidence.db"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _config(self, roots: list[Path]) -> dict[str, object]:
        return {
            "_base": str(self.root),
            "roots": [
                {
                    "id": path.name,
                    "path": str(path),
                    "max_depth": 4,
                    "include": ["*.md"],
                    "exclude_dirs": [],
                }
                for path in roots
            ],
            "privacy": {"sensitivity": "test"},
            "control_documents": [],
        }

    def test_scan_emits_per_root_progress_and_completion(self) -> None:
        roots = [self.root / "root-a", self.root / "root-b"]
        for index, root in enumerate(roots, start=1):
            root.mkdir()
            (root / f"file-{index}.md").write_text("# Test\n", encoding="utf-8")
        events: list[dict[str, object]] = []

        with Store(self.db) as store:
            stats = scan(
                self._config(roots),
                store,
                progress=events.append,
                progress_interval_seconds=0,
            )
            self.assertEqual(store.integrity_check(), "ok")

        event_names = [str(event["event"]) for event in events]
        self.assertEqual(event_names.count("root_started"), 2)
        self.assertEqual(event_names.count("root_completed"), 2)
        self.assertEqual(event_names[-1], "scan_completed")
        self.assertEqual(stats["files"], 2)
        completed = [
            event["root"]["id"]
            for event in events
            if event["event"] == "root_completed"
        ]
        self.assertEqual(completed, ["root-a", "root-b"])

    def test_time_budget_rolls_back_current_root_and_leaves_database_clean(self) -> None:
        first = self.root / "root-a"
        second = self.root / "root-b"
        first.mkdir()
        second.mkdir()
        (first / "first.md").write_text("# First\n", encoding="utf-8")
        (second / "one.md").write_text("# One\n", encoding="utf-8")
        (second / "two.md").write_text("# Two\n", encoding="utf-8")
        now = [0.0]
        events: list[dict[str, object]] = []

        from system_explorer import scanner

        original_scan_file = scanner._scan_file

        def advance_after_first_second_root_file(*args: object, **kwargs: object) -> None:
            path = args[0]
            original_scan_file(*args, **kwargs)
            if isinstance(path, Path) and path.parent == second:
                now[0] = 11.0

        with (
            self.assertRaises(ScanTimeBudgetExceeded),
            Store(self.db) as store,
            patch.object(
                scanner,
                "_scan_file",
                side_effect=advance_after_first_second_root_file,
            ),
        ):
            scan(
                self._config([first, second]),
                store,
                time_budget_seconds=10,
                progress=events.append,
                progress_interval_seconds=0,
                _clock=lambda: now[0],
            )

        db = sqlite3.connect(self.db)
        try:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            scopes = {
                row[0]
                for row in db.execute(
                    "SELECT scope FROM nodes WHERE scope IS NOT NULL"
                ).fetchall()
            }
        finally:
            db.close()
        self.assertTrue(any(str(first) in scope for scope in scopes))
        self.assertFalse(any(str(second) in scope for scope in scopes))
        self.assertFalse(Path(f"{self.db}-journal").exists())
        self.assertIn("root_rolled_back", [event["event"] for event in events])
        self.assertIn("scan_timed_out", [event["event"] for event in events])
        self.assertNotIn("scan_completed", [event["event"] for event in events])

    def test_keyboard_interrupt_rolls_back_current_root_without_hot_journal(self) -> None:
        root = self.root / "root-a"
        root.mkdir()
        (root / "one.md").write_text("# One\n", encoding="utf-8")
        events: list[dict[str, object]] = []

        with (
            self.assertRaises(KeyboardInterrupt),
            Store(self.db) as store,
            patch(
                "system_explorer.scanner._scan_file",
                side_effect=KeyboardInterrupt,
            ),
        ):
            scan(
                self._config([root]),
                store,
                progress=events.append,
                progress_interval_seconds=0,
            )

        db = sqlite3.connect(self.db)
        try:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 0)
        finally:
            db.close()
        self.assertFalse(Path(f"{self.db}-journal").exists())
        self.assertIn("root_rolled_back", [event["event"] for event in events])

    def test_interrupt_after_commit_does_not_claim_rollback(self) -> None:
        root = self.root / "root-a"
        root.mkdir()
        (root / "one.md").write_text("# One\n", encoding="utf-8")
        events: list[dict[str, object]] = []

        with self.assertRaises(KeyboardInterrupt), Store(self.db) as store:
            real_commit = store.commit

            def commit_then_interrupt() -> None:
                real_commit()
                raise KeyboardInterrupt

            with patch.object(store, "commit", side_effect=commit_then_interrupt):
                scan(
                    self._config([root]),
                    store,
                    progress=events.append,
                    progress_interval_seconds=0,
                )

        db = sqlite3.connect(self.db)
        try:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertGreater(db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 0)
        finally:
            db.close()
        event_names = [event["event"] for event in events]
        self.assertIn("root_commit_state_uncertain", event_names)
        self.assertNotIn("root_rolled_back", event_names)

    def test_committed_post_root_phase_is_not_reported_as_rolled_back(self) -> None:
        now = [0.0]
        events: list[dict[str, object]] = []
        config = self._config([])
        config["_config_path"] = str(self.root / "config.json")

        def committed_infrastructure(
            config: dict[str, object], store: Store
        ) -> dict[str, int]:
            store.add_node("registry", "committed")
            store.commit()
            now[0] = 11.0
            return {"registries": 1, "databases": 0, "tables": 0}

        with (
            self.assertRaises(ScanTimeBudgetExceeded),
            Store(self.db) as store,
            patch(
                "system_explorer.scanner.register_declared_infrastructure",
                side_effect=committed_infrastructure,
            ),
        ):
            scan(
                config,
                store,
                time_budget_seconds=10,
                progress=events.append,
                progress_interval_seconds=0,
                _clock=lambda: now[0],
            )

        db = sqlite3.connect(self.db)
        try:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM nodes WHERE node_type='registry'"
                ).fetchone()[0],
                1,
            )
        finally:
            db.close()
        event_names = [event["event"] for event in events]
        self.assertIn("phase_completed", event_names)
        self.assertIn("scan_timed_out", event_names)
        self.assertNotIn("phase_rolled_back", event_names)

    def test_post_root_error_after_commit_reports_uncertain_state(self) -> None:
        events: list[dict[str, object]] = []
        config = self._config([])
        config["_config_path"] = str(self.root / "config.json")

        def commit_then_interrupt(
            config: dict[str, object], store: Store
        ) -> dict[str, int]:
            store.add_node("registry", "committed")
            store.commit()
            raise KeyboardInterrupt

        with (
            self.assertRaises(KeyboardInterrupt),
            Store(self.db) as store,
            patch(
                "system_explorer.scanner.register_declared_infrastructure",
                side_effect=commit_then_interrupt,
            ),
        ):
            scan(
                config,
                store,
                progress=events.append,
                progress_interval_seconds=0,
            )

        db = sqlite3.connect(self.db)
        try:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM nodes WHERE node_type='registry'"
                ).fetchone()[0],
                1,
            )
        finally:
            db.close()
        event_names = [event["event"] for event in events]
        self.assertIn("phase_commit_state_uncertain", event_names)
        self.assertNotIn("phase_rolled_back", event_names)

    def test_post_root_partial_commit_rolls_back_tail_and_reports_uncertain(
        self,
    ) -> None:
        events: list[dict[str, object]] = []
        config = self._config([])
        config["_config_path"] = str(self.root / "config.json")

        def partial_commit_then_interrupt(
            config: dict[str, object], store: Store
        ) -> dict[str, int]:
            store.add_node("registry", "persisted")
            store.commit()
            store.add_node("registry", "rolled-back-tail")
            raise KeyboardInterrupt

        with (
            self.assertRaises(KeyboardInterrupt),
            Store(self.db) as store,
            patch(
                "system_explorer.scanner.register_declared_infrastructure",
                side_effect=partial_commit_then_interrupt,
            ),
        ):
            scan(
                config,
                store,
                progress=events.append,
                progress_interval_seconds=0,
            )

        db = sqlite3.connect(self.db)
        try:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            names = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM nodes WHERE node_type='registry'"
                ).fetchall()
            }
        finally:
            db.close()
        self.assertIn("persisted", names)
        self.assertNotIn("rolled-back-tail", names)
        event_names = [event["event"] for event in events]
        self.assertIn("phase_commit_state_uncertain", event_names)
        self.assertNotIn("phase_rolled_back", event_names)

    def test_cli_writes_progress_to_stderr_and_result_to_stdout(self) -> None:
        source = self.root / "source"
        source.mkdir()
        (source / "README.md").write_text("# Source\n", encoding="utf-8")
        config_path = self.root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": str(self.db),
                    "roots": [
                        {
                            "id": "source",
                            "path": str(source),
                            "include": ["*.md"],
                            "exclude_dirs": [],
                        }
                    ],
                    "privacy": {"sensitivity": "test"},
                }
            ),
            encoding="utf-8",
        )
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                [
                    "scan",
                    "--config",
                    str(config_path),
                    "--time-budget-seconds",
                    "30",
                    "--progress",
                    "jsonl",
                    "--progress-interval-seconds",
                    "0",
                ]
            )

        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        progress = [
            json.loads(line)
            for line in stderr.getvalue().splitlines()
            if line.strip()
        ]
        self.assertEqual(result["files"], 1)
        self.assertEqual(progress[-1]["event"], "scan_completed")
        self.assertTrue(
            all(
                event["schema"] == "system-explorer.scan-progress.v1"
                for event in progress
            )
        )

    def test_cli_interrupt_returns_130_without_success_payload(self) -> None:
        config_path = self.root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": str(self.db),
                    "roots": [],
                }
            ),
            encoding="utf-8",
        )
        stdout = StringIO()
        stderr = StringIO()

        with (
            patch("system_explorer.cli.scan", side_effect=KeyboardInterrupt),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = main(["scan", "--config", str(config_path)])

        self.assertEqual(code, 130)
        self.assertEqual(stdout.getvalue(), "")
        error = json.loads(stderr.getvalue())
        self.assertEqual(error["event"], "scan_interrupted")
        self.assertFalse(Path(f"{self.db}-journal").exists())

    def test_cli_timeout_keeps_stderr_valid_jsonl(self) -> None:
        source = self.root / "source"
        source.mkdir()
        (source / "README.md").write_text("# Source\n", encoding="utf-8")
        config_path = self.root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": str(self.db),
                    "roots": [{"id": "source", "path": str(source)}],
                }
            ),
            encoding="utf-8",
        )
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                [
                    "scan",
                    "--config",
                    str(config_path),
                    "--time-budget-seconds",
                    "0.000000001",
                    "--progress",
                    "jsonl",
                ]
            )

        events = [json.loads(line) for line in stderr.getvalue().splitlines()]
        self.assertEqual(code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("scan_timed_out", [event["event"] for event in events])
        self.assertEqual(events[-1]["event"], "scan_failed")

    def test_cli_rejects_non_finite_runtime_values(self) -> None:
        config_path = self.root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema": "system-explorer.config.v1",
                    "database": str(self.db),
                    "roots": [],
                }
            ),
            encoding="utf-8",
        )

        for flag, value in (
            ("--time-budget-seconds", "nan"),
            ("--time-budget-seconds", "inf"),
            ("--progress-interval-seconds", "nan"),
        ):
            with self.subTest(flag=flag, value=value):
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(
                        [
                            "scan",
                            "--config",
                            str(config_path),
                            flag,
                            value,
                        ]
                    )
                self.assertEqual(code, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(
                    json.loads(stderr.getvalue())["event"],
                    "scan_failed",
                )


if __name__ == "__main__":
    unittest.main()
