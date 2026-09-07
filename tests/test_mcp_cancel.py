"""What `cancel_pdf_comparison` may and may not kill.

Two findings meet here.

RECHECK-003: the PID was checked once, before the wait, and then only for
existence. Windows hands a PID out again within seconds, so a worker that exited
between two polls could get a *stranger* killed by the `taskkill /T /F` at the
deadline. The identity is now re-checked on every poll (process creation time)
and once more, in full (creation time + command line), immediately before any
signal.

The residual risk in PDF-003: `grace_sec` used to be a deadline for *finishing*,
so a worker doing something long but perfectly healthy — one A0 sheet at 600 DPI
outlasts any fixed grace — was force-killed for being slow, which is exactly what
aborts a re-render transaction halfway. It is now a limit on *silence*: a worker
that keeps its heartbeat going is left alone.
"""

from __future__ import annotations

import importlib
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import mock

import pytest

JOB_ID = "20260714_120000_abcd1234"
# What the identity check actually looks for: the worker script and this job's id.
WORKER_COMMAND = (
    rf"C:\py.exe D:\GitHub\PDFCompare\scripts\pdfcompare_worker.py "
    rf"--request D:\GitHub\PDFCompare\.pdfcompare_mcp\jobs\{JOB_ID}\request.json"
)
FOREIGN_COMMAND = r"C:\Windows\system32\notepad.exe"

WORKER_PID = 4242
# What Popen hands back in a venv: the python.exe launcher, not the worker.
LAUNCHER_PID = 4241
WORKER_CREATE_TIME = 133_000_000_000_000_000
FOREIGN_CREATE_TIME = 133_999_999_999_999_999


class FakeWorker:
    """A worker process the cancel loop can poll, on a wall-clock script.

    `exit_after` is when the worker itself dies; `pid_taken_after` is when some
    unrelated process is handed the same PID.
    """

    def __init__(
        self,
        job_dir: Path,
        *,
        exit_after: float | None = None,
        pid_taken_after: float | None = None,
        heartbeat: bool = True,
        ack_after: float | None = None,
        writes_cancelled_status: bool = True,
    ) -> None:
        self.job_dir = job_dir
        self.started = time.time()
        self.exit_after = exit_after
        self.pid_taken_after = pid_taken_after
        self.heartbeat = heartbeat
        self.ack_after = ack_after
        self.writes_cancelled_status = writes_cancelled_status

    # --- the process's own timeline ---

    def elapsed(self) -> float:
        return time.time() - self.started

    def worker_gone(self) -> bool:
        return self.exit_after is not None and self.elapsed() >= self.exit_after

    def pid_taken_over(self) -> bool:
        return (
            self.worker_gone()
            and self.pid_taken_after is not None
            and self.elapsed() >= self.pid_taken_after
        )

    # --- what the OS would tell us about that PID ---

    def pid_exists(self, pid: int) -> bool:
        if pid != WORKER_PID:
            return False
        self._tick()
        return (not self.worker_gone()) or self.pid_taken_over()

    def create_time(self, pid: int) -> int | None:
        if not self.pid_exists(pid):
            return None
        return FOREIGN_CREATE_TIME if self.worker_gone() else WORKER_CREATE_TIME

    def command_line(self, pid: int) -> str:
        if not self.pid_exists(pid):
            return ""
        return FOREIGN_COMMAND if self.worker_gone() else WORKER_COMMAND

    # --- what the worker writes while it lives ---

    def _tick(self) -> None:
        if self.worker_gone():
            if self.writes_cancelled_status:
                self._patch_status({"state": "cancelled", "message": "Задача остановлена пользователем"})
            return
        if self.heartbeat:
            (self.job_dir / "heartbeat").write_text("beat", encoding="utf-8")
        if self.ack_after is not None and self.elapsed() >= self.ack_after:
            self._patch_status({"cancel_acknowledged_at": "2026-07-14T12:00:00"})

    def _patch_status(self, patch: dict[str, Any]) -> None:
        path = self.job_dir / "status.json"
        status = json.loads(path.read_text(encoding="utf-8"))
        if all(status.get(key) == value for key, value in patch.items()):
            return
        status.update(patch)
        path.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")


class CancelTests(unittest.TestCase):
    def setUp(self) -> None:
        pytest.importorskip("mcp")
        self.mcp = importlib.import_module("scripts.pdfcompare_mcp")
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

        jobs_root = self.root / "jobs"
        patch = mock.patch.object(self.mcp, "JOBS_ROOT", jobs_root)
        patch.start()
        self.addCleanup(patch.stop)

        self.job_id = JOB_ID
        self.job = jobs_root / self.job_id
        self.job.mkdir(parents=True)
        (self.job / "status.json").write_text(
            json.dumps(
                {
                    "job_id": self.job_id,
                    "state": "running",
                    "pid": WORKER_PID,
                    "operation": "rerender",
                    "out_dir": str(self.root / "runs"),
                    "run_dir": str(self.root / "runs" / "report"),
                }
            ),
            encoding="utf-8",
        )
        # The worker records this about *itself* at startup. It has to: in a
        # virtualenv the PID the server gets back from Popen belongs to the
        # python.exe launcher, and the interpreter that actually runs the worker has
        # a different one — pinning the spawned PID pins the wrong process.
        (self.job / "worker.json").write_text(
            json.dumps({"pid": WORKER_PID, "create_time": WORKER_CREATE_TIME}), encoding="utf-8"
        )

        self.killed: list[list[str]] = []

    def cancel(self, worker: FakeWorker, **kwargs: float) -> dict[str, Any]:
        def fake_run(command: list[str], **_: object) -> object:
            self.killed.append(list(command))
            worker.exit_after = 0.0
            return mock.Mock(returncode=0)

        identity = importlib.import_module("scripts.process_identity")
        with (
            # The server calls these directly...
            mock.patch.object(self.mcp, "pid_exists", worker.pid_exists),
            mock.patch.object(self.mcp, "process_create_time", worker.create_time),
            mock.patch.object(self.mcp, "get_process_command_line", worker.command_line),
            # ...and same_process() reaches them through their own module.
            mock.patch.object(identity, "pid_exists", worker.pid_exists),
            mock.patch.object(identity, "process_create_time", worker.create_time),
            mock.patch.object(self.mcp.subprocess, "run", fake_run),
            mock.patch.object(self.mcp.os, "kill", lambda pid, sig: self.killed.append(["kill", str(pid)])),
        ):
            return self.mcp.cancel_pdf_comparison(self.job_id, **kwargs)  # type: ignore[arg-type]

    def test_a_worker_that_exits_cooperatively_is_never_killed(self) -> None:
        worker = FakeWorker(self.job, exit_after=0.6)

        result = self.cancel(worker, grace_sec=5.0)

        self.assertTrue(result["ok"], result.get("error"))
        self.assertFalse(result["forced"])
        self.assertEqual(result["cancel_reason"], "exited")
        self.assertEqual(self.killed, [], "a cooperative worker must not be signalled")
        self.assertTrue((self.job / "cancel").exists(), "the cancel marker was never dropped")
        self.assertEqual(result["job"]["state"], "cancelled")

    def test_a_slow_but_beating_worker_is_not_killed_for_being_slow(self) -> None:
        # The residual PDF-003 risk: a real 600 DPI re-render cancel took ~18 s
        # against a 20 s grace. Elapsed time is not evidence of a hang; silence is.
        worker = FakeWorker(self.job, exit_after=1.2, heartbeat=True, ack_after=0.2)

        result = self.cancel(worker, grace_sec=0.4)

        self.assertFalse(result["forced"], "a worker that is still heartbeating was force-killed")
        self.assertEqual(self.killed, [])
        self.assertTrue(result["cancel_acknowledged"], "the worker's rollback was never acknowledged")
        self.assertGreater(result["waited_sec"], 0.4, "the wait stopped at the grace, not at the exit")

    def test_a_worker_that_stops_responding_is_force_killed(self) -> None:
        # Alive, but writing nothing at all: a genuine hang, and the one case where
        # an inconsistent report beats an unkillable job.
        worker = FakeWorker(self.job, exit_after=None, heartbeat=False, writes_cancelled_status=False)

        result = self.cancel(worker, grace_sec=0.5, max_wait_sec=30.0)

        self.assertTrue(result["forced"])
        self.assertEqual(result["cancel_reason"], "unresponsive")
        self.assertEqual(len(self.killed), 1)
        self.assertIn(str(WORKER_PID), self.killed[0])
        self.assertIn("/F", self.killed[0])
        self.assertIn("промежуточном состоянии", result["job"]["message"])
        self.assertTrue(result["job"]["forced"])

    def test_wait_timeout_keeps_live_rollback_pending(self) -> None:
        worker = FakeWorker(self.job, exit_after=None, heartbeat=True, ack_after=0.0)
        result = self.cancel(worker, grace_sec=1.0, max_wait_sec=0.2)
        self.assertTrue(result["pending"])
        self.assertFalse(result["forced"])
        self.assertEqual(self.killed, [])
        self.assertEqual(result["job"]["state"], "running")

    def test_a_reused_pid_is_not_killed(self) -> None:
        # The worker exits and Windows immediately hands its number to something
        # else. The old code polled only pid_exists(), so it kept waiting and then
        # killed whatever now owned the PID.
        worker = FakeWorker(
            self.job,
            exit_after=0.4,
            pid_taken_after=0.4,
            heartbeat=False,
            writes_cancelled_status=False,
        )

        result = self.cancel(worker, grace_sec=0.5, max_wait_sec=30.0)

        self.assertEqual(self.killed, [], "a process that is not our worker was signalled")
        self.assertFalse(result["forced"])
        self.assertTrue(result["pid_reused"])
        self.assertEqual(result["cancel_reason"], "exited")
        self.assertIn("PID успел занять другой процесс", result["job"]["message"])

    def test_a_foreign_process_is_not_killed_at_the_deadline(self) -> None:
        # A job started before worker.json existed has no creation time on record,
        # so the cheap poll cannot tell the PID has changed hands and the loop runs
        # all the way to the kill branch. Only the full check there — the command
        # line — catches that the process is now a stranger's.
        (self.job / "worker.json").unlink()
        worker = FakeWorker(
            self.job,
            exit_after=0.3,
            pid_taken_after=0.3,
            heartbeat=False,
            writes_cancelled_status=False,
        )

        result = self.cancel(worker, grace_sec=0.5, max_wait_sec=5.0)

        self.assertEqual(self.killed, [], "taskkill was issued against a foreign process")
        self.assertFalse(result["forced"])
        self.assertTrue(result["pid_reused"])
        self.assertEqual(result["cancel_reason"], "exited")

    def test_a_launcher_pid_left_in_the_status_does_not_break_the_cancel(self) -> None:
        # The race: the worker writes its real PID into status.json within
        # milliseconds, and the server's own post-Popen write used to stamp the venv
        # launcher's PID back over it. A cancel a moment later then compared the
        # launcher against worker.json and refused with job_pid_foreign. What the
        # worker said about *itself* wins.
        status = json.loads((self.job / "status.json").read_text(encoding="utf-8"))
        status["pid"] = LAUNCHER_PID  # the value the server used to publish
        status["launcher_pid"] = LAUNCHER_PID
        (self.job / "status.json").write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
        worker = FakeWorker(self.job, exit_after=0.6)

        result = self.cancel(worker, grace_sec=5.0)

        self.assertTrue(result["ok"], result.get("error"))
        self.assertFalse(result["forced"])
        self.assertEqual(self.killed, [])
        self.assertEqual(result["job"]["state"], "cancelled")

    def test_a_job_whose_pid_is_already_a_stranger_is_refused_up_front(self) -> None:
        worker = FakeWorker(self.job, exit_after=0.0, pid_taken_after=0.0, heartbeat=False)

        result = self.cancel(worker, grace_sec=1.0)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_key"], "job_pid_foreign")
        self.assertEqual(self.killed, [])

    def test_a_finished_job_cannot_be_cancelled(self) -> None:
        (self.job / "status.json").write_text(
            json.dumps({"job_id": self.job_id, "state": "completed", "pid": WORKER_PID}), encoding="utf-8"
        )
        worker = FakeWorker(self.job, heartbeat=False)

        result = self.cancel(worker)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_key"], "job_not_running")
        self.assertEqual(self.killed, [])


    def test_a_busy_machine_does_not_make_the_cancel_refuse_to_work(self) -> None:
        # Reading a command line spawns a PowerShell, and a cancel arrives exactly
        # when every core is busy rendering. A real 600 DPI smoke had that lookup
        # time out, come back empty, and the cancel refuse with "not our worker" —
        # leaving the job running and staging on disk. The creation time is pinned
        # at spawn and needs no subprocess, so it must be enough on its own.
        worker = FakeWorker(self.job, exit_after=0.6)

        with mock.patch.object(self.mcp, "get_process_command_line", lambda pid: ""):
            result = self.cancel(worker, grace_sec=5.0)

        self.assertTrue(result["ok"], result.get("error"))
        self.assertFalse(result["forced"])
        self.assertEqual(self.killed, [])
        self.assertEqual(result["job"]["state"], "cancelled")


class WorkerIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        pytest.importorskip("mcp")
        self.mcp = importlib.import_module("scripts.pdfcompare_mcp")

    def test_the_current_process_has_a_creation_time(self) -> None:
        import os

        create_time = self.mcp.process_create_time(os.getpid())
        self.assertIsNotNone(create_time, "no creation time: PID reuse cannot be detected")
        self.assertGreater(int(create_time or 0), 0)
        # Stable: it is a property of the process, not of the moment it is read.
        self.assertEqual(create_time, self.mcp.process_create_time(os.getpid()))

    def test_a_dead_pid_has_none(self) -> None:
        self.assertIsNone(self.mcp.process_create_time(0))
        self.assertIsNone(self.mcp.process_create_time(-1))


if __name__ == "__main__":
    unittest.main()
