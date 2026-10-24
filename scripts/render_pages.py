"""把每本书的每一页渲染成 JPEG：content/pages/<书>/<页码>.jpg（题目页和"看原页"用）。
用法: python3 scripts/render_pages.py [书名 ...]"""
import sys
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parent.parent
books = sys.argv[1:] or [p.stem for p in (ROOT / "books").glob("*.pdf")]
for b in books:
    doc = fitz.open(ROOT / "books" / f"{b}.pdf")
    out = ROOT / "content/pages" / b
    out.mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(doc):
        f = out / f"{i + 1}.jpg"
        if f.exists():
            continue
        zoom = 1400 / page.rect.height  # 统一渲染成约 1400px 高
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB)
        pix.save(f, jpg_quality=72)
    print(b, len(doc), "页")
