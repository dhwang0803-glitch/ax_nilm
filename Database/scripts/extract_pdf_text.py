"""AI Hub PDF 설명서 텍스트 추출 (pymupdf)."""
import sys
from pathlib import Path

import fitz


def extract(pdf_path: Path, out_path: Path) -> None:
    doc = fitz.open(pdf_path)
    with out_path.open("w", encoding="utf-8") as f:
        for i, page in enumerate(doc, start=1):
            f.write(f"\n\n===== PAGE {i} =====\n\n")
            f.write(page.get_text("text"))
    doc.close()
    print(f"[ok] {pdf_path.name} -> {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    staging = Path("Database/dataset_staging/aihub_71685/docs")
    out_dir = Path("Database/dataset_staging/aihub_71685/docs/_extracted")
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = [
        "105-129.+전기+인프라+지능화를+위한+가전기기+전력+사용량+데이터_데이터설명서.pdf",
        "105-129.+전기+인프라+지능화를+위한+가전기기+전력+사용량+데이터_활용가이드라인.pdf",
    ]
    for name in targets:
        src = staging / name
        if not src.exists():
            print(f"[skip] {src} not found", file=sys.stderr)
            continue
        dst = out_dir / (src.stem + ".txt")
        extract(src, dst)
