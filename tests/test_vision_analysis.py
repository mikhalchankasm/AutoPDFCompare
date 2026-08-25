from __future__ import annotations

import importlib
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from pdfcompare_core.pdf_io import imwrite_compat
from pdfcompare_core.vision_analysis import (
    VisionAnalysis,
    VisionAnalysisCache,
    VisionAnalysisError,
    build_vision_evidence,
    create_vision_report,
    select_vision_rows,
    validate_qwen_base_url,
    vision_zone_coverage,
)


def changed_row(seq: int = 1) -> dict[str, object]:
    return {
        "seq": seq,
        "status": "matched",
        "a_page": seq,
        "b_page": seq,
        "pair_dir": f"{seq:03d}__A_{seq}__B_{seq}",
        "change_level": "minor",
        "diff_percent": 0.25,
        "diff_foreground_percent": 2.5,
        "diff_area_mm2": 12.4,
        "bboxes_count": 1,
    }


def build_run(tmp_path: Path, pairs: list[dict[str, object]]) -> Path:
    run_dir = tmp_path / "run"
    internal = run_dir / "_pdfcompare"
    pages = internal / "pages"
    internal.mkdir(parents=True)
    (internal / "summary.json").write_text(
        json.dumps({"file_a": "old.pdf", "file_b": "new.pdf", "pairs": pairs}),
        encoding="utf-8",
    )
    for row in pairs:
        if row.get("status") != "matched" or row.get("a_page") is None or row.get("b_page") is None:
            continue
        pair_dir = pages / str(row["pair_dir"])
        pair_dir.mkdir(parents=True)
        old = np.full((480, 640, 3), 255, dtype=np.uint8)
        new = old.copy()
        cv2.rectangle(old, (120, 140), (240, 230), (0, 0, 0), 3)
        cv2.rectangle(new, (150, 140), (270, 230), (0, 0, 0), 3)
        overlay = new.copy()
        cv2.rectangle(overlay, (110, 130), (280, 240), (0, 0, 255), 4)
        imwrite_compat(pair_dir / "a.png", old)
        imwrite_compat(pair_dir / "b.png", new)
        imwrite_compat(pair_dir / "overlay.png", overlay)
        (pair_dir / "bboxes.json").write_text(
            json.dumps([{"x": 110, "y": 130, "w": 170, "h": 110}]), encoding="utf-8"
        )
    return run_dir


def test_selection_never_includes_one_sided_or_non_diff_rows() -> None:
    rows = [
        changed_row(1),
        {**changed_row(2), "status": "added", "a_page": None},
        {**changed_row(3), "status": "removed", "b_page": None},
        {**changed_row(4), "b_page": None},
        {**changed_row(5), "status": "size_mismatch"},
        {**changed_row(6), "change_level": "unchanged"},
        {**changed_row(7), "diff_percent": 0.0, "bboxes_count": 0},
        changed_row(8),
    ]

    selection = select_vision_rows(rows, excluded_seqs=[8])

    assert [row["seq"] for row in selection.eligible] == [1]
    assert selection.skipped == {
        "excluded": [8],
        "added": [2],
        "removed": [3],
        "one_sided": [4],
        "not_matched": [5],
        "unchanged": [6],
        "no_diff": [7],
    }


def test_evidence_cache_and_downloadable_report_are_local(tmp_path: Path) -> None:
    row = changed_row()
    run_dir = build_run(tmp_path, [row])
    evidence = build_vision_evidence(run_dir, row, max_zones=8)
    assert evidence.path.is_file()
    assert evidence.zones_total == 1
    assert evidence.zones_shown == 1

    cache = VisionAnalysisCache(run_dir, "vision-test", lang="ru")
    cache.put(1, VisionAnalysis("Линия смещена вправо.", "vision-test", 100, 20))
    artifacts = create_vision_report(run_dir, "vision-test", [row], lang="ru")

    assert artifacts.html_path.is_file()
    assert artifacts.markdown_path.is_file()
    assert artifacts.json_path.is_file()
    assert artifacts.zip_path.is_file()
    assert artifacts.sheet_count == 1
    with zipfile.ZipFile(artifacts.zip_path) as archive:
        names = set(archive.namelist())
        assert {
            "index.html",
            "report.md",
            "README.txt",
            "report.json",
            "sheets/sheet_001/comparison.html",
            "sheets/sheet_001/old.png",
            "sheets/sheet_001/new.png",
            "sheets/sheet_001/details/zone_01_old.png",
            "sheets/sheet_001/details/zone_01_new.png",
        } <= names
        report = json.loads(archive.read("report.json"))
        markdown = archive.read("report.md").decode("utf-8")
        sheet_html = archive.read("sheets/sheet_001/comparison.html").decode("utf-8")
    assert report["sheets"][0]["seq"] == 1
    assert report["sheets"][0]["description"] == "Линия смещена вправо."
    assert report["sheets"][0]["images"]["old"] == "sheets/sheet_001/old.png"
    assert "![OLD — старая ревизия](sheets/sheet_001/old.png)" in markdown
    assert "DIFF" not in markdown
    html = artifacts.html_path.read_text(encoding="utf-8")
    assert "Матрица AI-сравнения" in html
    assert "Скрыть шум" in sheet_html
    assert "showNoise=true" in sheet_html
    assert "changes.hidden=s.facts.length<2" in sheet_html
    assert "Ctrl+колесо" in sheet_html


def test_mcp_preview_requires_confirmation_and_filters_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("mcp")
    mcp_module = importlib.import_module("scripts.pdfcompare_mcp")
    rows = [changed_row(1), {**changed_row(2), "status": "added", "a_page": None}]
    run_dir = build_run(tmp_path, rows)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-never-returned")

    preview = mcp_module.preview_pdf_vision_analysis(str(run_dir), lang="ru")
    unconfirmed = mcp_module.analyze_pdf_comparison_with_deepseek(str(run_dir), lang="ru")

    assert preview["ok"] is True
    assert preview["eligible_count"] == 1
    assert preview["eligible_sheets"][0]["seq"] == 1
    assert preview["skipped"]["added"] == {"count": 1, "seqs": [2]}
    assert preview["requires_external_upload_confirmation"] is True
    assert unconfirmed["analysis_started"] is False
    assert "secret-never-returned" not in json.dumps(preview)


def test_mcp_confirmed_analysis_uses_cache_and_builds_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("mcp")
    mcp_module = importlib.import_module("scripts.pdfcompare_mcp")
    row = changed_row(1)
    run_dir = build_run(tmp_path, [row])
    secret = "deepseek-test-secret"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)

    class FakeClient:
        def __init__(self, **kwargs: object):
            assert kwargs["api_key"] == secret

        def analyze(self, evidence: object, current_row: object, *, lang: str) -> VisionAnalysis:
            del evidence, current_row, lang
            return VisionAnalysis("Объект смещён.", "vision-test", 80, 15)

    monkeypatch.setattr(mcp_module, "DeepSeekVisionClient", FakeClient)
    result = mcp_module.analyze_pdf_comparison_with_deepseek(
        str(run_dir),
        confirm_external_upload=True,
        model="vision-test",
        lang="ru",
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    cached = mcp_module.analyze_pdf_comparison_with_deepseek(
        str(run_dir),
        confirm_external_upload=True,
        model="vision-test",
        lang="ru",
    )

    assert result["ok"] is True
    assert result["processed_count"] == 1
    assert result["cached_count"] == 0
    assert Path(result["report_html_path"]).is_file()
    assert Path(result["report_markdown_path"]).is_file()
    assert Path(result["report_zip_path"]).is_file()
    html = Path(result["report_html_path"]).read_text(encoding="utf-8")
    assert "Матрица AI-сравнения" in html
    sheet_html = Path(result["report_html_path"]).parent / "sheets" / "sheet_001" / "comparison.html"
    sheet_text = sheet_html.read_text(encoding="utf-8")
    assert "Скрыть шум" in sheet_text
    assert "pointerdown" in sheet_text
    assert "ctrlKey" in sheet_text
    assert 'target="_blank"' not in html
    assert cached["cached_count"] == 1
    assert cached["prompt_tokens"] == 0
    assert cached["completion_tokens"] == 0
    for path in (run_dir / "_pdfcompare" / "vision_analysis").rglob("*"):
        if path.is_file() and path.suffix != ".jpg":
            assert secret not in path.read_text(encoding="utf-8", errors="ignore")


def test_qwen_endpoint_is_restricted_to_alibaba_model_studio() -> None:
    valid = "https://example.maas.aliyuncs.com/compatible-mode/v1"
    assert validate_qwen_base_url(valid + "/") == valid

    for invalid in (
        "",
        "http://example.maas.aliyuncs.com/compatible-mode/v1",
        "https://example.com/compatible-mode/v1",
        "https://example.maas.aliyuncs.com/v1",
        "https://user:password@example.maas.aliyuncs.com/compatible-mode/v1",
    ):
        with pytest.raises(VisionAnalysisError):
            validate_qwen_base_url(invalid)


def test_mcp_qwen_requires_environment_and_keeps_provider_cache_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("mcp")
    mcp_module = importlib.import_module("scripts.pdfcompare_mcp")
    row = changed_row(1)
    run_dir = build_run(tmp_path, [row])
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_BASE_URL", raising=False)

    preview = mcp_module.preview_pdf_vision_analysis(str(run_dir), provider="qwen", lang="ru")
    missing = mcp_module.analyze_pdf_comparison_with_ai(
        str(run_dir),
        provider="qwen",
        confirm_external_upload=True,
        lang="ru",
    )

    assert preview["ok"] is True
    assert preview["provider"] == "qwen"
    assert preview["setup_required"] is True
    assert preview["key_setup"]["required_environment_variables"] == ["QWEN_API_KEY", "QWEN_BASE_URL"]
    assert missing["ok"] is False
    assert missing["required_environment_variable"] == "QWEN_API_KEY"
    assert "чат" in missing["key_setup"]["security_note"]

    secret = "qwen-secret-never-persisted"
    endpoint = "https://example.maas.aliyuncs.com/compatible-mode/v1"
    monkeypatch.setenv("QWEN_API_KEY", secret)
    monkeypatch.setenv("QWEN_BASE_URL", endpoint)

    class FakeQwenClient:
        def __init__(self, **kwargs: object):
            assert kwargs["api_key"] == secret
            assert kwargs["base_url"] == endpoint

        def analyze(self, evidence: object, current_row: object, *, lang: str) -> VisionAnalysis:
            del evidence, current_row, lang
            return VisionAnalysis("Добавлена строка спецификации.", "qwen-test", 120, 30)

    monkeypatch.setattr(mcp_module, "QwenVisionClient", FakeQwenClient)
    result = mcp_module.analyze_pdf_comparison_with_ai(
        str(run_dir),
        provider="qwen",
        confirm_external_upload=True,
        model="qwen-test",
        lang="ru",
    )

    assert result["ok"] is True
    assert result["provider"] == "qwen"
    assert result["cost_estimate"] is None
    report = json.loads(Path(result["report_json_path"]).read_text(encoding="utf-8"))
    assert report["provider"] == "qwen"
    assert "qwen-qwen-test-ru" in result["report_html_path"]
    for path in (run_dir / "_pdfcompare" / "vision_analysis").rglob("*"):
        if path.is_file() and path.suffix != ".jpg":
            assert secret not in path.read_text(encoding="utf-8", errors="ignore")


def test_mcp_gemini_is_default_and_reports_openrouter_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("mcp")
    mcp_module = importlib.import_module("scripts.pdfcompare_mcp")
    row = changed_row(1)
    run_dir = build_run(tmp_path, [row])
    secret = "openrouter-secret-never-persisted"
    monkeypatch.delenv("PDFCOMPARE_VISION_PROVIDER", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)

    preview = mcp_module.preview_pdf_vision_analysis(str(run_dir), lang="ru")

    class FakeGeminiClient:
        def __init__(self, **kwargs: object):
            assert kwargs["api_key"] == secret
            assert kwargs["model"] == "google/gemini-3.7-flash"

        def analyze(self, evidence: object, current_row: object, *, lang: str) -> VisionAnalysis:
            del evidence, current_row, lang
            return VisionAnalysis(
                "Добавлена строка спецификации.",
                "google/gemini-3.7-flash",
                120,
                30,
                reasoning_tokens=12,
                charged_cost_usd=0.0125,
            )

    monkeypatch.setattr(mcp_module, "GeminiVisionClient", FakeGeminiClient)
    result = mcp_module.analyze_pdf_comparison_with_ai(
        str(run_dir),
        confirm_external_upload=True,
        lang="ru",
    )

    assert preview["provider"] == "gemini"
    assert preview["api_key_environment_variable"] == "OPENROUTER_API_KEY"
    assert result["ok"] is True
    assert result["provider"] == "gemini"
    assert result["reasoning_tokens"] == 12
    assert result["cost_estimate"]["charged_by_openrouter_usd"] == 0.0125
    assert "provider=qwen" in result["quality_note"]
    for path in (run_dir / "_pdfcompare" / "vision_analysis").rglob("*"):
        if path.is_file() and path.suffix != ".jpg":
            assert secret not in path.read_text(encoding="utf-8", errors="ignore")


def test_gemini_zone_coverage_requires_every_zone_exactly_once() -> None:
    complete = vision_zone_coverage(
        '<zone_coverage_json>{"zones":[{"zone_id":1},{"zone_id":2},{"zone_id":3}]}</zone_coverage_json>',
        3,
    )
    incomplete = vision_zone_coverage(
        '<zone_coverage_json>{"zones":[{"zone_id":1},{"zone_id":1},{"zone_id":4}]}</zone_coverage_json>',
        3,
    )

    assert complete == {"complete": True, "missing": [], "duplicates": [], "unknown": []}
    assert incomplete == {
        "complete": False,
        "missing": [2, 3],
        "duplicates": [1],
        "unknown": [4],
    }
