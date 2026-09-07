from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: build_pdf_from_slides.py <png-dir> <pdf>")
    png_dir = Path(sys.argv[1])
    target = Path(sys.argv[2])
    slides = sorted(png_dir.glob("slide-*.png"), key=lambda path: int(path.stem.split("-")[-1]))
    if len(slides) != 30:
        raise SystemExit(f"expected 30 rendered slides, found {len(slides)}")
    target.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = 1280, 720
    output = canvas.Canvas(str(target), pagesize=(page_width, page_height))
    for slide in slides:
        output.drawImage(ImageReader(str(slide)), 0, 0, width=page_width, height=page_height, preserveAspectRatio=False, mask="auto")
        output.showPage()
    output.save()


if __name__ == "__main__":
    main()
