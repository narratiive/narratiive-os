from __future__ import annotations
import sys
from pathlib import Path
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

if len(sys.argv) != 3:
    raise SystemExit("usage: build_sketchbook_pdf.py <png-dir> <pdf>")
source, target = Path(sys.argv[1]), Path(sys.argv[2])
pages = sorted(source.glob("page-*.png"), key=lambda item: int(item.stem.split("-")[-1]))
if len(pages) != 5:
    raise SystemExit(f"expected exactly five rendered SKETCHBOOK pages, found {len(pages)}")
target.parent.mkdir(parents=True, exist_ok=True)
pdf = canvas.Canvas(str(target), pagesize=(1280, 720))
for page in pages:
    pdf.drawImage(ImageReader(str(page)), 0, 0, width=1280, height=720, preserveAspectRatio=False, mask="auto")
    pdf.showPage()
pdf.save()
