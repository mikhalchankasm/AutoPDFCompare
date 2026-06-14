from __future__ import annotations

import importlib

import pytest


def test_mcp_entrypoint_imports_when_dependency_installed() -> None:
    pytest.importorskip("mcp")
    importlib.import_module("scripts.pdfcompare_mcp")
