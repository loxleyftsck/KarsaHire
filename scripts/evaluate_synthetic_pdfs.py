"""Audit text extractability of the bundled synthetic PDF corpus without OCR."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "synthetic-cv-32"


def evaluate() -> dict:
    manifest_path = DATASET / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("Manifest dataset kosong atau formatnya tidak valid.")

    seen_ids: set[str] = set()
    pdf_count = page_count = text_pages = textless_pages = 0
    missing_pdfs: list[str] = []
    malformed_pdfs: list[str] = []

    for entry in manifest:
        sample_id = str(entry.get("sample_id", "")) if isinstance(entry, dict) else ""
        if not sample_id or sample_id in seen_ids:
            raise ValueError(f"ID sampel kosong atau duplikat: {sample_id!r}")
        seen_ids.add(sample_id)
        if not sample_id.startswith("r") or not sample_id[1:].isdigit() or len(sample_id) != 6:
            raise ValueError(f"ID sampel tidak valid: {sample_id!r}")

        pdf_path = DATASET / sample_id / f"{sample_id}.pdf"
        if not pdf_path.is_file():
            missing_pdfs.append(sample_id)
            continue

        try:
            reader = PdfReader(str(pdf_path), strict=True)
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as error:
            malformed_pdfs.append(f"{sample_id}: {type(error).__name__}")
            continue

        pdf_count += 1
        page_count += len(pages)
        text_pages += sum(bool(text.strip()) for text in pages)
        textless_pages += sum(not text.strip() for text in pages)

    return {
        "dataset": "synthetic-cv-32",
        "pdfs_expected": len(seen_ids),
        "pdfs_read": pdf_count,
        "pages_read": page_count,
        "pages_with_extractable_text": text_pages,
        "pages_without_extractable_text": textless_pages,
        "missing_pdf_sample_ids": missing_pdfs,
        "malformed_pdfs": malformed_pdfs,
        "ocr_required_for_textless_pages": textless_pages > 0,
        "limitations": [
            "Uses local pypdf text extraction only; no OCR requests are made.",
            "A page without extractable text may contain a scan; this audit does not assess OCR quality.",
            "Synthetic English pages do not establish parsing quality for real applicant documents.",
        ],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"PDF audit failed: {error}", file=sys.stderr)
        raise SystemExit(2)
