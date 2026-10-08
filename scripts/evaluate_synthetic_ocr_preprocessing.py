"""Compare bounded local preprocessing variants on selected synthetic PDFs.

This diagnostic runs Windows OCR locally and reports aggregate WER only. It
does not make network requests or print/persist recognized OCR text.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import re
import sys

from PIL import Image, ImageOps
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import evaluate_synthetic_ocr as evaluator  # noqa: E402
import server  # noqa: E402

VARIANT_NAMES = ("original", "gray_autocontrast", "upscale_1p5_autocontrast")


def image_png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def preprocessing_variants(image_bytes: bytes) -> dict[str, bytes]:
    with Image.open(io.BytesIO(image_bytes)) as opened:
        original = opened.convert("RGB")
    gray = ImageOps.grayscale(original)
    gray_autocontrast = ImageOps.autocontrast(gray, cutoff=1).convert("RGB")
    width, height = original.size
    upscale = ImageOps.autocontrast(gray, cutoff=1).resize(
        (int(width * 1.5), int(height * 1.5)), Image.Resampling.LANCZOS
    ).convert("RGB")
    return {
        "original": image_bytes,
        "gray_autocontrast": image_png(gray_autocontrast),
        "upscale_1p5_autocontrast": image_png(upscale),
    }


def evaluate_sample(sample_id: str, language_tag: str) -> dict:
    pdf_path, reference_path, page_count, planned_images = evaluator.preflight(sample_id)
    reference_bytes = reference_path.read_bytes()
    reference_tokens = evaluator.tokens(reference_bytes.decode("utf-8"))
    page_variant_lines = {name: [] for name in VARIANT_NAMES}
    image_count = 0
    reader = PdfReader(str(pdf_path), strict=True)
    for page_num, page in enumerate(reader.pages, start=1):
        if (page.extract_text() or "").strip():
            continue
        for embedded in getattr(page, "images", []):
            image_count += 1
            if image_count > server.MAX_OCR_IMAGES_PER_PDF:
                raise ValueError("PDF melebihi batas gambar untuk OCR lokal.")
            try:
                normalized = server.normalize_image(embedded.data)
            except ValueError:
                continue
            variants = preprocessing_variants(normalized)
            for name in VARIANT_NAMES:
                recognized = evaluator.local_windows_ocr_text(
                    variants[name], language_tag
                )
                page_variant_lines[name].extend(
                    (page_num, line)
                    for line in recognized.splitlines()
                    if line.strip()
                )
    if image_count != planned_images:
        raise ValueError("Jumlah gambar PDF berubah setelah preflight.")

    variant_metrics = {}
    for name, lines in page_variant_lines.items():
        hypothesis = "\n".join(
            line for _, line in sorted(lines, key=lambda item: item[0])
        )
        edits, denominator = evaluator.word_error_counts(
            reference_tokens, evaluator.tokens(hypothesis)
        )
        variant_metrics[name] = {
            "word_edits": edits,
            "reference_word_count": denominator,
            "ocr_word_count": len(evaluator.tokens(hypothesis)),
            "word_error_rate": round(edits / denominator, 4) if denominator else None,
        }
    return {
        "sample_id": sample_id,
        "sample_pdf_sha256": evaluator.file_sha256(pdf_path),
        "reference_text_sha256": evaluator.file_sha256(reference_path),
        "pdf_pages": page_count,
        "ocr_images_processed": image_count,
        "variants": variant_metrics,
    }


def evaluate_samples(sample_ids: list[str], language_tag: str = "en-US") -> dict:
    if os.name != "nt":
        raise ValueError("Diagnostic Windows OCR hanya tersedia di Windows.")
    if not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", language_tag):
        raise ValueError("Tag bahasa Windows OCR tidak valid.")
    if not sample_ids or len(sample_ids) > 8 or len(set(sample_ids)) != len(sample_ids):
        raise ValueError("Pilih 1–8 sample ID sintetis yang unik.")

    rows = []
    failures = []
    for index, sample_id in enumerate(sample_ids, start=1):
        try:
            rows.append(evaluate_sample(sample_id, language_tag))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            failures.append({"sample_id": sample_id, "error_type": type(error).__name__})
        print(
            f"Preprocessing probe: {index}/{len(sample_ids)} sampel; "
            f"berhasil={len(rows)}, gagal={len(failures)}",
            file=sys.stderr,
            flush=True,
        )

    aggregates = {}
    for variant in VARIANT_NAMES:
        reference_words = sum(
            row["variants"][variant]["reference_word_count"] for row in rows
        )
        edits = sum(row["variants"][variant]["word_edits"] for row in rows)
        ocr_words = sum(row["variants"][variant]["ocr_word_count"] for row in rows)
        aggregates[variant] = {
            "word_edits": edits,
            "reference_word_count": reference_words,
            "ocr_word_count": ocr_words,
            "micro_word_error_rate": round(edits / reference_words, 4) if reference_words else None,
        }

    return {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": "synthetic-cv-32",
        "network_mode": "disabled_local_windows_ocr",
        "ocr_engine": "Windows.Media.Ocr",
        "ocr_language": language_tag,
        "ocr_engine_os_build": platform.version(),
        "ocr_model_fingerprint": None,
        "pipeline_version": server.pipeline_version(),
        "requirements_sha256": hashlib.sha256(
            (ROOT / "requirements.txt").read_bytes()
        ).hexdigest(),
        "dependency_versions": {
            name: importlib.metadata.version(name)
            for name in ("pypdf", "python-docx", "Pillow", "lxml", "typing-extensions")
        },
        "runner_sha256": hashlib.sha256(
            Path(__file__).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "ocr_bridge_sha256": evaluator.file_sha256(evaluator.WINDOWS_OCR_BRIDGE),
        "samples_attempted": len(sample_ids),
        "samples_processed": len(rows),
        "samples_failed": len(failures),
        "total_ocr_images": sum(row["ocr_images_processed"] for row in rows),
        "status": "complete" if not failures else "partial",
        "aggregates": aggregates,
        "per_sample_aggregate": rows,
        "failures": failures,
        "limitations": [
            "Sample selection is diagnostic and not a random or representative estimate of the corpus.",
            "WER uses synthetic corpus text references, not human-adjudicated OCR ground truth.",
            "Preprocessing results apply only to the Windows-managed OCR engine and do not select or establish a production OCR provider.",
            "No OCR text is printed or persisted; the output contains aggregate metrics, sample IDs, and fingerprints only.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-id", action="append", required=True, help="Synthetic sample ID; repeat for multiple PDFs (max 8).")
    parser.add_argument("--language", default="en-US", help="Installed Windows OCR language tag (default: en-US).")
    args = parser.parse_args()
    try:
        result = evaluate_samples(args.sample_id, args.language)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Synthetic OCR preprocessing evaluation failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
