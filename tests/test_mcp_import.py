from __future__ import annotations

import importlib

import pytest


def test_mcp_entrypoint_imports_when_dependency_installed() -> None:
    pytest.importorskip("mcp")
    importlib.import_module("scripts.pdfcompare_mcp")


def test_update_check_reports_the_local_checkout() -> None:
    # The MCP server runs from its own git checkout, which the GUI installer never
    # touches; this tool is how an agent notices the checkout has fallen behind.
    pytest.importorskip("mcp")
    mcp_module = importlib.import_module("scripts.pdfcompare_mcp")

    result = mcp_module.check_pdfcompare_update(fetch=False)  # offline: no network in CI

    assert result["ok"] is True
    assert result["version"]
    assert result["commit"] != "unknown"
    assert "update_available" in result
    assert result["message"]
