"""GitHub release check for the desktop auto-update notification.

Pure logic + a single network call. No Tk imports here so the helpers stay
unit-testable without a display. The GUI layer wires the results into a
badge/dialog; this module only answers "what is the latest release?" and
"is it newer than the running version?".
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from pdfcompare_core.constants import APP_VERSION, GITHUB_REPO

SETUP_ASSET_NAME = "PDFCompareLocal-setup.exe"
SUMS_ASSET_NAME = "SHA256SUMS.txt"
logger = logging.getLogger("pdfcompare.ui.update_check")


def parse_version(s: str) -> tuple[int, ...]:
    """Parse a dotted numeric version like ``"0.1.6"`` or ``"v0.1.6"``.

    Tolerates a leading ``v``/``V`` and trailing non-numeric suffixes
    (e.g. ``"0.1.6-rc1"``); only the leading dot-separated integers are kept.
    Non-numeric segments are dropped, so junk input yields ``()``.
    """
    text = (s or "").strip().lstrip("vV")
    # Strip any pre-release/build suffix after the first non-dot/num boundary.
    parts: list[int] = []
    for segment in text.split("."):
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            parts.append(int(digits))
    return tuple(parts)


def is_newer(current: str, latest_tag: str) -> bool:
    """Return True when ``latest_tag`` denotes a newer version than ``current``."""
    cur = parse_version(current)
    latest = parse_version(latest_tag)
    if not cur or not latest:
        return False
    # Pad to equal length so (0,1) compares correctly against (0,1,0).
    n = max(len(cur), len(latest))
    cur = cur + (0,) * (n - len(cur))
    latest = latest + (0,) * (n - len(latest))
    return latest > cur


def latest_release_url() -> str:
    return f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def fetch_latest_release(timeout: float = 8.0) -> dict[str, Any] | None:
    """Query the GitHub API for the latest release.

    Returns ``{tag, name, html_url, exe_url, setup_url, published_at, body}``
    or ``None`` on any error (network, timeout, non-200, parse failure).
    Never raises — update checks are best-effort and must not disturb the
    user. ``setup_url`` points at the Inno Setup installer asset when the
    release ships one; the GUI uses it for in-place auto-update.
    """
    try:
        req = urllib.request.Request(
            latest_release_url(),
            headers={
                "User-Agent": f"PDFCompareLocal/{APP_VERSION}",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — trusted https endpoint
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        logger.info("Could not fetch the latest GitHub release", exc_info=True)
        return None

    try:
        tag = str(data["tag_name"])
        name = str(data.get("name") or tag)
        html_url = str(data.get("html_url") or "")
        published_at = str(data.get("published_at") or "")
        body = str(data.get("body") or "")
        exe_url = ""
        setup_url = ""
        sums_url = ""
        for asset in data.get("assets") or []:
            asset_name = str(asset.get("name"))
            if asset_name == "PDFCompareLocal.exe":
                exe_url = str(asset.get("browser_download_url") or "")
            elif asset_name == SETUP_ASSET_NAME:
                setup_url = str(asset.get("browser_download_url") or "")
            elif asset_name == SUMS_ASSET_NAME:
                sums_url = str(asset.get("browser_download_url") or "")
    except (KeyError, TypeError, ValueError):
        return None

    return {
        "tag": tag,
        "name": name,
        "html_url": html_url,
        "exe_url": exe_url,
        "setup_url": setup_url,
        "sums_url": sums_url,
        "published_at": published_at,
        "body": body,
    }


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse `sha256sum`-style lines: ``<64-hex-hash>  <file name>``.

    Unknown lines are skipped; the leading ``*`` of binary-mode entries is
    tolerated. Returns {file_name: lowercase_hash}.
    """
    result: dict[str, str] = {}
    for line in (text or "").splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        digest = parts[0].lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            continue
        name = " ".join(parts[1:]).lstrip("*").strip()
        if name:
            result[name] = digest
    return result


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_installer_temp_file(version: str) -> Path:
    """Reserve a unique installer path so concurrent updates cannot collide."""
    safe_version = "".join(ch for ch in version if ch.isalnum() or ch in ".-_") or "update"
    fd, raw_path = tempfile.mkstemp(prefix=f"PDFCompareLocal-setup-{safe_version}-", suffix=".exe")
    os.close(fd)
    return Path(raw_path)


def file_matches_sha256(path: Path, expected: str) -> bool:
    """Verify a file against a normalized SHA-256 value."""
    normalized = expected.strip().lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        return False
    try:
        actual = sha256_of_file(path)
    except OSError:
        logger.warning("Could not read update installer for verification: %s", path, exc_info=True)
        return False
    return hmac.compare_digest(actual, normalized)


def fetch_text(url: str, timeout: float = 30.0) -> str:
    """Small helper for downloading the checksum manifest."""
    req = urllib.request.Request(url, headers={"User-Agent": f"PDFCompareLocal/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — trusted https endpoint
        return resp.read().decode("utf-8", errors="replace")
