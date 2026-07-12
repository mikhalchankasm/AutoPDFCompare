"""Tests for the update-check logic (version parsing, comparison, fetch mock).

These exercise the pure logic without touching the network or Tk, plus a
mocked fetch_latest_release to verify GitHub-API response parsing.
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from unittest import mock

from pdfcompare_ui.update_check import (
    fetch_latest_release,
    is_newer,
    latest_release_url,
    parse_version,
)


class ParseVersionTests(unittest.TestCase):
    def test_plain_dotted(self) -> None:
        self.assertEqual(parse_version("0.1.6"), (0, 1, 6))

    def test_leading_v(self) -> None:
        self.assertEqual(parse_version("v0.1.6"), (0, 1, 6))
        self.assertEqual(parse_version("V0.1.6"), (0, 1, 6))

    def test_prerelease_suffix(self) -> None:
        self.assertEqual(parse_version("0.1.6-rc1"), (0, 1, 6))

    def test_empty_and_garbage(self) -> None:
        self.assertEqual(parse_version(""), ())
        self.assertEqual(parse_version("abc"), ())


class IsNewerTests(unittest.TestCase):
    def test_newer_minor(self) -> None:
        self.assertTrue(is_newer("0.1.5", "v0.1.6"))

    def test_same_version(self) -> None:
        self.assertFalse(is_newer("0.1.6", "v0.1.6"))

    def test_older_release(self) -> None:
        self.assertFalse(is_newer("0.2.0", "v0.1.9"))

    def test_different_length_padding(self) -> None:
        # (0,1) should compare equal to (0,1,0), not "newer".
        self.assertFalse(is_newer("0.1.0", "v0.1"))
        self.assertTrue(is_newer("0.1", "v0.1.1"))


class ShouldCheckForUpdatesTests(unittest.TestCase):
    """Test the interval-gating logic via a stub mirroring the mixin."""

    def _make_stub(self, enabled: bool, last_checked_iso: str, skip_version: str = "") -> object:
        from pdfcompare_ui.state_persistence import StatePersistenceMixin

        class Stub(StatePersistenceMixin):
            def __init__(self) -> None:
                self.update_check_state = {
                    "enabled": enabled,
                    "last_checked_utc": last_checked_iso,
                    "skip_version": skip_version,
                }

        return Stub()

    def test_disabled_returns_false(self) -> None:
        stub = self._make_stub(enabled=False, last_checked_iso="")
        self.assertFalse(stub._should_check_for_updates())  # type: ignore[attr-defined]

    def test_never_checked_returns_true(self) -> None:
        stub = self._make_stub(enabled=True, last_checked_iso="")
        self.assertTrue(stub._should_check_for_updates())  # type: ignore[attr-defined]

    def test_checked_recently_returns_false(self) -> None:
        # Interval is 1 hour; 5 minutes ago is too recent.
        recent = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        stub = self._make_stub(enabled=True, last_checked_iso=recent)
        self.assertFalse(stub._should_check_for_updates())  # type: ignore[attr-defined]

    def test_checked_long_ago_returns_true(self) -> None:
        # 2 hours ago exceeds the 1-hour interval.
        old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        stub = self._make_stub(enabled=True, last_checked_iso=old)
        self.assertTrue(stub._should_check_for_updates())  # type: ignore[attr-defined]

    def test_naive_timestamp_treated_as_utc(self) -> None:
        # A timestamp without tzinfo should be assumed UTC, not crash.
        recent_naive = (datetime.now(UTC) - timedelta(minutes=5)).replace(tzinfo=None).isoformat()
        stub = self._make_stub(enabled=True, last_checked_iso=recent_naive)
        self.assertFalse(stub._should_check_for_updates())  # type: ignore[attr-defined]


class FetchLatestReleaseTests(unittest.TestCase):
    SAMPLE_PAYLOAD = {
        "tag_name": "v0.1.7",
        "name": "Release v0.1.7",
        "html_url": "https://github.com/mikhalchankasm/AutoPDFCompare/releases/tag/v0.1.7",
        "published_at": "2026-07-11T12:00:00Z",
        "body": "Release notes here.",
        "assets": [
            {"name": "PDFCompareLocal.exe", "browser_download_url": "https://example.com/exe"},
            {"name": "PDFCompareLocal-portable.zip", "browser_download_url": "https://example.com/zip"},
        ],
    }

    def test_parses_release(self) -> None:
        body = io.BytesIO(json.dumps(self.SAMPLE_PAYLOAD).encode("utf-8"))
        fake_resp = mock.MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = body.read()
        fake_resp.__enter__ = mock.MagicMock(return_value=fake_resp)
        fake_resp.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("pdfcompare_ui.update_check.urllib.request.urlopen", return_value=fake_resp):
            result = fetch_latest_release(timeout=1.0)
        self.assertIsNotNone(result)
        assert result is not None  # for type-checkers
        self.assertEqual(result["tag"], "v0.1.7")
        self.assertEqual(result["exe_url"], "https://example.com/exe")
        self.assertEqual(result["html_url"], self.SAMPLE_PAYLOAD["html_url"])

    def test_returns_none_on_network_error(self) -> None:
        with mock.patch("pdfcompare_ui.update_check.urllib.request.urlopen", side_effect=Exception("timeout")):
            with redirect_stdout(io.StringIO()):  # silence any prints
                result = fetch_latest_release(timeout=0.1)
        self.assertIsNone(result)

    def test_returns_none_on_missing_tag(self) -> None:
        payload = {"name": "broken release"}  # no tag_name
        body = io.BytesIO(json.dumps(payload).encode("utf-8"))
        fake_resp = mock.MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = body.read()
        fake_resp.__enter__ = mock.MagicMock(return_value=fake_resp)
        fake_resp.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("pdfcompare_ui.update_check.urllib.request.urlopen", return_value=fake_resp):
            result = fetch_latest_release(timeout=1.0)
        self.assertIsNone(result)

    def test_latest_release_url_targets_repo(self) -> None:
        url = latest_release_url()
        self.assertIn("api.github.com", url)
        self.assertIn("AutoPDFCompare", url)
        self.assertTrue(url.endswith("/releases/latest"))


if __name__ == "__main__":
    unittest.main()
