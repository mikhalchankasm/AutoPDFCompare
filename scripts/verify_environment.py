"""Fail on package drift from a hash lock before running or shipping the application."""
from __future__ import annotations

import importlib.metadata
import re
import sys
from pathlib import Path

from packaging.requirements import Requirement


def verify(lock: Path) -> list[str]:
    errors = []
    for line in lock.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^[A-Za-z0-9_.-]+==", line):
            continue
        requirement = Requirement(line.rstrip("\\").strip())
        if requirement.marker and not requirement.marker.evaluate():
            continue
        if sys.platform != "win32" and requirement.name.lower() in {"pywin32", "pywin32-ctypes", "pefile"}:
            continue
        try:
            version = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"Missing {requirement}")
            continue
        if version not in requirement.specifier:
            errors.append(f"{requirement.name}: installed {version}, required {requirement.specifier}")
    return errors


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    errors = verify(Path(sys.argv[1]) if len(sys.argv) > 1 else root / "requirements/lock-runtime.txt")
    print("\n".join(errors) if errors else "Installed packages match the lock.")
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
