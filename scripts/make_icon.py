"""Rebuild packaging/PDFCompareLocal.ico from packaging/icon.svg.

The .ico is committed — the build must not depend on a rendering step — but it is
generated, so this is how it is regenerated after the SVG changes:

    python scripts/make_icon.py

It renders with PyMuPDF, which the app already depends on, and writes a PNG-payload
ICO (Vista and later). Windows picks the size it needs: 16 px in the title bar, 32
in the taskbar, 256 in the "extra large icons" view — a single upscaled bitmap looks
soft in the first and blocky in the last, so every size is rendered from the vector.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parents[1]
SVG = REPO_ROOT / "packaging" / "icon.svg"
ICO = REPO_ROOT / "packaging" / "PDFCompareLocal.ico"

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_png(svg: Path, size: int) -> bytes:
    with fitz.open(svg) as doc:
        page = doc[0]
        scale = size / max(page.rect.width, page.rect.height)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=True)
    if (pix.width, pix.height) != (size, size):
        raise RuntimeError(f"rendered {pix.width}x{pix.height}, expected {size}x{size}")
    png: bytes = pix.tobytes("png")
    return png


def build_ico(images: list[tuple[int, bytes]]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(images))  # reserved, type=icon, count
    directory = b""
    payload = b""
    offset = len(header) + 16 * len(images)
    for size, png in images:
        # 256 is stored as 0 in the directory: the field is one byte.
        directory += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,
            0 if size >= 256 else size,
            0,  # palette colours
            0,  # reserved
            1,  # colour planes
            32,  # bits per pixel
            len(png),
            offset,
        )
        payload += png
        offset += len(png)
    return header + directory + payload


def main() -> int:
    if not SVG.exists():
        print(f"missing {SVG}", file=sys.stderr)
        return 1
    images = [(size, render_png(SVG, size)) for size in SIZES]
    ICO.write_bytes(build_ico(images))
    print(f"{ICO.relative_to(REPO_ROOT)}: {ICO.stat().st_size} bytes, sizes {', '.join(map(str, SIZES))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
