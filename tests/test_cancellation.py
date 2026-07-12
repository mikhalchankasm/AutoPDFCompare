"""Cancellation must actually stop the run, not just the queue.

Previously the parent blocked in as_completed() and the cancel check lived in
the progress callback, so cancellation was noticed only when a page finished —
and the pages already running always ran to completion. Now the parent polls
the cancel callback, and the workers poll a shared flag between the expensive
phases of a page (render A, render B, align, diff, write).
"""

from __future__ import annotations

import concurrent.futures
import multiprocessing
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from pdfcompare_core.pdf_io import find_pages_dir, find_summary_json_path, internal_dir
from pdfcompare_core.runner import (
    RunCancelled,
    _init_pool_worker,
    compare_pdfs,
    process_pair_task,
    regenerate_report_pages,
)


class _Flag:
    """Cancel flag that flips to set after `after` checks."""

    def __init__(self, after: int = 0) -> None:
        self.after = after
        self.checks = 0

    def is_set(self) -> bool:
        self.checks += 1
        return self.checks > self.after


def _make_pdf(path: Path, pages: int, extra: bool) -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.draw_rect(fitz.Rect(50, 50, 400, 300), color=(0, 0, 0), width=2)
        if extra:
            page.draw_circle(fitz.Point(300, 500 + i), 40, color=(0, 0, 0), width=3)
    doc.save(path)
    doc.close()


class CancellationTests(unittest.TestCase):
    def test_worker_aborts_page_when_flag_is_set(self) -> None:
        # A page already being rendered must stop at the next phase boundary
        # instead of finishing — and leave no half-written rasters behind.
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_pdf(tmp_path / "a.pdf", pages=1, extra=False)
            _make_pdf(tmp_path / "b.pdf", pages=1, extra=True)
            pages_dir = tmp_path / "pages"

            with self.assertRaises(RunCancelled):
                process_pair_task(
                    tmp_path / "a.pdf",
                    tmp_path / "b.pdf",
                    pages_dir,
                    1,
                    0,
                    0,
                    "matched",
                    1.0,
                    72,
                    2.0,
                    False,
                    cancel_event=_Flag(after=0),
                )

            self.assertEqual(list(pages_dir.rglob("*.png")), [])

    def test_worker_aborts_between_render_and_diff(self) -> None:
        # Cancel that arrives after both pages are rendered: the checkpoints past
        # the renders must catch it too, before the diff and before any output is
        # written.
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_pdf(tmp_path / "a.pdf", pages=1, extra=False)
            _make_pdf(tmp_path / "b.pdf", pages=1, extra=True)
            pages_dir = tmp_path / "pages"
            flag = _Flag(after=2)  # survives the pre-render checks, trips before the diff

            with self.assertRaises(RunCancelled):
                process_pair_task(
                    tmp_path / "a.pdf",
                    tmp_path / "b.pdf",
                    pages_dir,
                    1,
                    0,
                    0,
                    "matched",
                    1.0,
                    72,
                    2.0,
                    False,
                    cancel_event=flag,
                )

            self.assertGreater(flag.checks, 2, "the later checkpoints were not reached")
            self.assertEqual(list(pages_dir.rglob("*.png")), [])

    def test_page_runs_normally_when_flag_stays_clear(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_pdf(tmp_path / "a.pdf", pages=1, extra=False)
            _make_pdf(tmp_path / "b.pdf", pages=1, extra=True)
            pages_dir = tmp_path / "pages"

            row = process_pair_task(
                tmp_path / "a.pdf",
                tmp_path / "b.pdf",
                pages_dir,
                1,
                0,
                0,
                "matched",
                1.0,
                72,
                2.0,
                False,
                cancel_event=_Flag(after=10_000),
            )

            self.assertEqual(int(row["seq"]), 1)
            self.assertTrue((pages_dir / "001__A_1__B_1" / "overlay.png").exists())

    def test_cancel_flag_reaches_a_spawned_pool_worker(self) -> None:
        # The cross-process half of the mechanism, exactly as production uses it:
        # a spawn-context Event inherited through the pool's initargs must be
        # visible to process_pair_task running in another process.
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_pdf(tmp_path / "a.pdf", pages=1, extra=False)
            _make_pdf(tmp_path / "b.pdf", pages=1, extra=True)
            pages_dir = tmp_path / "pages"

            ctx = multiprocessing.get_context("spawn")
            event = ctx.Event()
            event.set()
            with concurrent.futures.ProcessPoolExecutor(
                max_workers=1,
                mp_context=ctx,
                initializer=_init_pool_worker,
                initargs=(event,),
            ) as executor:
                future = executor.submit(
                    process_pair_task,
                    tmp_path / "a.pdf",
                    tmp_path / "b.pdf",
                    pages_dir,
                    1,
                    0,
                    0,
                    "matched",
                    1.0,
                    72,
                    2.0,
                    False,
                )
                with self.assertRaises(RunCancelled):
                    future.result()

            self.assertEqual(list(pages_dir.rglob("*.png")), [])

    def test_cancel_before_pages_leaves_no_run_dir_sequential(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_pdf(tmp_path / "a.pdf", pages=2, extra=False)
            _make_pdf(tmp_path / "b.pdf", pages=2, extra=True)
            out = tmp_path / "runs"

            with self.assertRaises(RunCancelled):
                compare_pdfs(
                    tmp_path / "a.pdf",
                    tmp_path / "b.pdf",
                    out,
                    high_dpi=72,
                    run_name="cancelled",
                    workers=1,
                    cancel_cb=lambda: True,
                )

            # Cancelled runs are removed, not quarantined: there is nothing to debug.
            self.assertEqual(list(out.glob("*")), [])

    def test_cancel_before_pages_leaves_no_run_dir_parallel(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_pdf(tmp_path / "a.pdf", pages=3, extra=False)
            _make_pdf(tmp_path / "b.pdf", pages=3, extra=True)
            out = tmp_path / "runs"

            with self.assertRaises(RunCancelled):
                compare_pdfs(
                    tmp_path / "a.pdf",
                    tmp_path / "b.pdf",
                    out,
                    high_dpi=72,
                    run_name="cancelled",
                    workers=2,
                    cancel_cb=lambda: True,
                )

            self.assertEqual(list(out.glob("*")), [])

    def test_cancel_after_first_page_stops_the_rest(self) -> None:
        # Cancel once page 1 is done: page 2 must never be processed.
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_pdf(tmp_path / "a.pdf", pages=3, extra=False)
            _make_pdf(tmp_path / "b.pdf", pages=3, extra=True)
            out = tmp_path / "runs"
            messages: list[str] = []
            cancelled = False

            def progress(pct: float, msg: str) -> None:
                nonlocal cancelled
                messages.append(msg)
                if "Сравнение листов 1/3" in msg:
                    cancelled = True

            with self.assertRaises(RunCancelled):
                compare_pdfs(
                    tmp_path / "a.pdf",
                    tmp_path / "b.pdf",
                    out,
                    high_dpi=72,
                    run_name="cancelled",
                    workers=1,
                    progress_cb=progress,
                    cancel_cb=lambda: cancelled,
                )

            self.assertTrue(any("Сравнение листов 1/3" in m for m in messages), messages)
            self.assertFalse(any("Сравнение листов 2/3" in m for m in messages), messages)
            self.assertEqual(list(out.glob("*")), [])


    def test_cancelled_rerender_leaves_the_report_untouched(self) -> None:
        # Cancelling a re-render must roll the run back: it swaps pages in place,
        # so a half-applied cancel would corrupt an existing report.
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_pdf(tmp_path / "a.pdf", pages=2, extra=False)
            _make_pdf(tmp_path / "b.pdf", pages=2, extra=True)
            run_dir = compare_pdfs(
                tmp_path / "a.pdf", tmp_path / "b.pdf", tmp_path / "runs", high_dpi=72, run_name="base"
            )
            summary_before = find_summary_json_path(run_dir).read_bytes()
            pages_before = sorted(p.stat().st_size for p in find_pages_dir(run_dir).rglob("*.png"))

            with self.assertRaises(RunCancelled):
                regenerate_report_pages(
                    run_dir, [1], high_dpi=200, report_lang="ru", workers=1, cancel_cb=lambda: True
                )

            self.assertEqual(find_summary_json_path(run_dir).read_bytes(), summary_before)
            self.assertEqual(sorted(p.stat().st_size for p in find_pages_dir(run_dir).rglob("*.png")), pages_before)
            self.assertEqual(list(internal_dir(run_dir).glob(".rerender_*")), [])

    def test_cancel_cb_stops_stages_outside_the_page_loop(self) -> None:
        # A core caller passing only cancel_cb (no raising progress_cb) must be
        # able to cancel during alignment / report generation too, not just
        # between pages.
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _make_pdf(tmp_path / "a.pdf", pages=1, extra=False)
            _make_pdf(tmp_path / "b.pdf", pages=1, extra=True)
            out = tmp_path / "runs"
            # A single page means the page loop is entered exactly once; flipping
            # the flag only after several emits lands us in a later stage.
            flag = _Flag(after=3)

            with self.assertRaises(RunCancelled):
                compare_pdfs(
                    tmp_path / "a.pdf",
                    tmp_path / "b.pdf",
                    out,
                    high_dpi=72,
                    run_name="cancelled",
                    workers=1,
                    cancel_cb=flag.is_set,
                )

            self.assertEqual(list(out.glob("*")), [])


if __name__ == "__main__":
    unittest.main()
