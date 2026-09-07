from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import pdfcompare_mcp as server


class McpResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_remains_available_during_slow_cancellation(self) -> None:
        cancel = server.mcp._tool_manager.get_tool("cancel_pdf_comparison")
        status = server.mcp._tool_manager.get_tool("get_pdf_comparison_status")
        assert cancel is not None and status is not None

        def slow_load(_job_id: str) -> dict:
            time.sleep(0.5)
            return {"state": "completed"}

        with patch.object(server, "load_status", slow_load), patch.object(server, "list_statuses", return_value=[]):
            task = asyncio.create_task(cancel.fn("fake"))
            await asyncio.sleep(0.05)
            started = time.monotonic()
            result = await status.fn()
            self.assertLess(time.monotonic() - started, 0.25)
            self.assertTrue(result["ok"])
            await task

    async def test_native_tool_dispatch_uses_a_separate_process(self) -> None:
        tool = server.mcp._tool_manager.get_tool("preview_pdf_comparison")
        assert tool is not None
        result = await tool.fn("missing-old.pdf", "missing-new.pdf", "tmp", "test-invalid-input")
        self.assertFalse(result["ok"])


@unittest.skipUnless(sys.platform.startswith("linux"), "Real POSIX process groups require Linux")
class PosixCancellationTests(unittest.TestCase):
    def test_group_termination_stops_a_child_that_ignores_sigterm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "child.pid"
            child_code = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"
            parent_code = (
                "import subprocess,sys,time,pathlib; "
                f"p=subprocess.Popen([sys.executable,'-c',{child_code!r}]); "
                f"pathlib.Path({str(marker)!r}).write_text(str(p.pid)); time.sleep(60)"
            )
            process = subprocess.Popen([sys.executable, "-c", parent_code], start_new_session=True)
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(marker.exists())
                time.sleep(0.1)
                with patch.object(server, "process_matches_worker_job", return_value=True):
                    self.assertTrue(server.terminate_worker_tree(process.pid, "test"))
                process.wait(timeout=2)
                self.assertFalse(server.linux_group_running(process.pid))
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, 9)  # type: ignore[attr-defined]
                    process.wait(timeout=2)
