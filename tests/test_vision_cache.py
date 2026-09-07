from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pdfcompare_core.pdf_io import internal_dir, report_pages_dir
from pdfcompare_core.vision_analysis import VisionAnalysis, VisionAnalysisCache


def test_analysis_cache_invalidates_for_pixels_and_sheet_metadata() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        pair = report_pages_dir(root) / "pair"
        pair.mkdir(parents=True)
        image = pair / "a.png"
        image.write_bytes(b"old raster")
        summary = internal_dir(root) / "summary.json"
        row = {"seq": 1, "pair_dir": "pair", "diff_percent": 1}
        summary.write_text(json.dumps({"pairs": [row]}))
        cache = VisionAnalysisCache(root, "model")
        analysis = VisionAnalysis("changed line", "model", 10, 5)
        cache.put(1, analysis)
        assert cache.get(1) is not None
        image.write_bytes(b"new raster")
        assert cache.get(1) is None
        assert cache.cached_sequences() == []
        cache.put(1, analysis)
        row["diff_percent"] = 25
        summary.write_text(json.dumps({"pairs": [row]}))
        assert cache.get(1) is None
