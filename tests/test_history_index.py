"""Unit tests for the shared GUI+MCP comparison history (pdfcompare_core.history_index)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from pdfcompare_core import history_index


class HistoryIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.ui_path = self.root / "state.json"
        self.mcp_path = self.root / "mcp_history.json"
        for target, value in (
            ("STATE_DIR", self.root),
            ("UI_STATE_PATH", self.ui_path),
            ("MCP_HISTORY_PATH", self.mcp_path),
        ):
            patch = mock.patch.object(history_index, target, value)
            patch.start()
            self.addCleanup(patch.stop)

    def _write_ui(self, records: list[dict]) -> None:
        self.ui_path.write_text(json.dumps({"history": records}, ensure_ascii=False), encoding="utf-8")

    def _write_mcp(self, records: list[dict]) -> None:
        self.mcp_path.write_text(json.dumps({"history": records}, ensure_ascii=False), encoding="utf-8")

    def test_missing_files_yield_empty(self) -> None:
        self.assertEqual(history_index.read_ui_records(), [])
        self.assertEqual(history_index.read_mcp_records(), [])
        self.assertEqual(history_index.list_records(), [])

    def test_merge_sorted_newest_first_and_numbered(self) -> None:
        self._write_ui(
            [
                {"ts": "2026-07-15 10:00:00", "result": "ok", "old_pdf": "a.pdf", "new_pdf": "b.pdf"},
                {"ts": "2026-07-15 14:00:00", "result": "cancelled", "old_pdf": "c.pdf", "new_pdf": "d.pdf"},
            ]
        )
        self._write_mcp(
            [
                {"ts": "2026-07-15 12:00:00", "result": "completed", "job_id": "J1", "old_pdf": "e.pdf", "new_pdf": "f.pdf"},
            ]
        )
        rows = history_index.list_records()
        self.assertEqual([r["date"] for r in rows], ["2026-07-15 14:00:00", "2026-07-15 12:00:00", "2026-07-15 10:00:00"])
        self.assertEqual([r["index"] for r in rows], [1, 2, 3])
        self.assertEqual([r["source"] for r in rows], ["ui", "mcp", "ui"])

    def test_index_is_stable_regardless_of_limit(self) -> None:
        self._write_mcp(
            [
                {"ts": f"2026-07-15 12:00:0{n}", "result": "completed", "job_id": f"J{n}"}
                for n in range(5)
            ]
        )
        full = history_index.list_records(limit=0)
        limited = history_index.list_records(limit=2)
        self.assertEqual(len(limited), 2)
        self.assertEqual([r["index"] for r in limited], [1, 2])
        # The same records occupy the same positions whether limited or not.
        self.assertEqual([r["id"] for r in limited], [r["id"] for r in full[:2]])

    def test_source_filter(self) -> None:
        self._write_ui([{"ts": "2026-07-15 10:00:00", "result": "ok"}])
        self._write_mcp([{"ts": "2026-07-15 12:00:00", "result": "completed", "job_id": "J1"}])
        self.assertEqual([r["source"] for r in history_index.list_records(source="ui")], ["ui"])
        self.assertEqual([r["source"] for r in history_index.list_records(source="mcp")], ["mcp"])

    def test_result_aliasing(self) -> None:
        self._write_mcp(
            [
                {"ts": "2026-07-15 12:00:03", "result": "completed", "job_id": "J1"},
                {"ts": "2026-07-15 12:00:02", "result": "error", "job_id": "J2"},
                {"ts": "2026-07-15 12:00:01", "result": "cancelled", "job_id": "J3"},
            ]
        )
        results = {r["id"]: r["result"] for r in history_index.list_records()}
        self.assertEqual(results["mcp:J1"], "done")
        self.assertEqual(results["mcp:J2"], "failed")
        self.assertEqual(results["mcp:J3"], "cancelled")

    def test_stable_id_mcp_uses_job_id(self) -> None:
        self._write_mcp([{"ts": "2026-07-15 12:00:00", "result": "completed", "job_id": "20260715_120000_abcd1234"}])
        (row,) = history_index.list_records()
        self.assertEqual(row["id"], "mcp:20260715_120000_abcd1234")

    def test_stable_id_ui_is_deterministic(self) -> None:
        self._write_ui([{"ts": "2026-07-15 10:00:00", "result": "ok", "old_pdf": "a.pdf", "new_pdf": "b.pdf"}])
        first = history_index.list_records()[0]["id"]
        second = history_index.list_records()[0]["id"]
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("ui:"))

    def test_replay_ui_bbox_merge_off(self) -> None:
        self._write_ui(
            [
                {
                    "ts": "2026-07-15 10:00:00",
                    "result": "ok",
                    "dpi": "300",
                    "stroke_tol": "1.5",
                    "diff_strictness": "strict",
                    "exclude_regions": "0,0,10,10",
                    "bbox_merge": "off",
                    "bbox_merge_gap": "5",
                    "bbox_merge_max_ratio": "16",
                    "keep_debug": "on",
                    "ignore_line_weight": "on",
                }
            ]
        )
        replay = history_index.list_records()[0]["replay"]
        self.assertEqual(replay["dpi"], 300)
        self.assertEqual(replay["stroke_tol"], 1.5)
        self.assertEqual(replay["diff_strictness"], "strict")
        self.assertEqual(replay["exclude_regions"], "0,0,10,10")
        self.assertEqual(replay["bbox_merge_gap_mm"], 0.0)  # merge off → gap 0 regardless of stored value
        self.assertEqual(replay["bbox_merge_max_area_ratio"], 16.0)
        self.assertIs(replay["keep_debug_images"], True)
        self.assertIs(replay["ignore_line_weight"], True)

    def test_replay_ui_bbox_merge_on(self) -> None:
        self._write_ui(
            [{"ts": "2026-07-15 10:00:00", "result": "ok", "bbox_merge": "on", "bbox_merge_gap": "7"}]
        )
        replay = history_index.list_records()[0]["replay"]
        self.assertEqual(replay["bbox_merge_gap_mm"], 7.0)

    def test_replay_mcp_direct_mapping(self) -> None:
        self._write_mcp(
            [
                {
                    "ts": "2026-07-15 12:00:00",
                    "result": "completed",
                    "job_id": "J1",
                    "dpi": 400,
                    "stroke_tol": 2.5,
                    "diff_strictness": "loose",
                    "exclude_regions": [{"x": 0, "y": 0, "w": 5, "h": 5}],
                    "bbox_merge_gap_mm": 3.0,
                    "bbox_merge_max_area_ratio": 12.0,
                    "keep_debug_images": True,
                    "ignore_line_weight": True,
                }
            ]
        )
        replay = history_index.list_records()[0]["replay"]
        self.assertEqual(replay["dpi"], 400)
        self.assertEqual(replay["stroke_tol"], 2.5)
        self.assertEqual(replay["diff_strictness"], "loose")
        self.assertEqual(replay["exclude_regions"], [{"x": 0, "y": 0, "w": 5, "h": 5}])
        self.assertEqual(replay["bbox_merge_gap_mm"], 3.0)
        self.assertEqual(replay["bbox_merge_max_area_ratio"], 12.0)
        self.assertIs(replay["keep_debug_images"], True)
        self.assertIs(replay["ignore_line_weight"], True)

    def test_find_by_index_and_id(self) -> None:
        self._write_mcp(
            [
                {"ts": "2026-07-15 12:00:02", "result": "completed", "job_id": "J-new"},
                {"ts": "2026-07-15 12:00:01", "result": "completed", "job_id": "J-old"},
            ]
        )
        by_index = history_index.find_record("#1")
        self.assertIsNotNone(by_index)
        assert by_index is not None
        self.assertEqual(by_index["id"], "mcp:J-new")
        self.assertEqual(history_index.find_record("2")["id"], "mcp:J-old")  # type: ignore[index]
        self.assertEqual(history_index.find_record("mcp:J-old")["id"], "mcp:J-old")  # type: ignore[index]
        self.assertIsNone(history_index.find_record("nope"))
        self.assertIsNone(history_index.find_record("#99"))

    def test_append_mcp_record_persists_and_caps(self) -> None:
        history_index.append_mcp_record({"ts": "2026-07-15 12:00:00", "result": "completed", "job_id": "J1"})
        history_index.append_mcp_record({"ts": "2026-07-15 12:00:01", "result": "completed", "job_id": "J2"})
        records = history_index.read_mcp_records()
        self.assertEqual([r["job_id"] for r in records], ["J1", "J2"])

        for n in range(history_index.MAX_MCP_RECORDS + 20):
            history_index.append_mcp_record({"ts": "2026-07-15 12:00:02", "result": "completed", "job_id": f"K{n}"})
        capped = history_index.read_mcp_records()
        self.assertEqual(len(capped), history_index.MAX_MCP_RECORDS)
        self.assertEqual(capped[-1]["job_id"], f"K{history_index.MAX_MCP_RECORDS + 20 - 1}")


if __name__ == "__main__":
    unittest.main()
