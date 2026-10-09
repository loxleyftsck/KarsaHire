"""Measure local Windows OCR WER across the bundled synthetic CV corpus only.

This runner has no network OCR option. It prints aggregate metrics, sample IDs,
and input/code fingerprints; it never prints or persists recognized OCR text.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import re
import sys

import evaluate_synthetic_ocr as evaluator
from synthetic_dataset_fingerprint import pinned_dataset_snapshot_sha256


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalized_file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def evaluate_corpus(language_tag: str = "en-US") -> dict:
    if os.name != "nt":
        raise ValueError("Evaluasi korpus Windows OCR hanya tersedia di Windows.")
    if not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", language_tag):
        raise ValueError("Tag bahasa Windows OCR tidak valid.")

    dataset_snapshot_before = pinned_dataset_snapshot_sha256(evaluator.DATASET)
    runner_path = Path(__file__).resolve()
    fingerprint_helper_path = runner_path.with_name("synthetic_dataset_fingerprint.py")
    runner_sha256_before = normalized_file_sha256(runner_path)
    fingerprint_helper_sha256_before = normalized_file_sha256(fingerprint_helper_path)
    manifest_path = evaluator.resolve_dataset_file(evaluator.DATASET / "manifest.json")
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = sha256_bytes(manifest_bytes)
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, list) or len(manifest) != evaluator.server.SYNTHETIC_DATASET_SIZE:
        raise ValueError(
            f"Manifest korpus sintetis harus memuat tepat {evaluator.server.SYNTHETIC_DATASET_SIZE} sampel."
        )
    sample_ids = []
    seen_sample_ids = set()
    for entry in manifest:
        sample_id = entry.get("sample_id") if isinstance(entry, dict) else None
        if not isinstance(sample_id, str) or not re.fullmatch(r"r\d{5}", sample_id):
            raise ValueError("Manifest korpus sintetis memuat sample ID yang tidak valid.")
        if sample_id in seen_sample_ids:
            raise ValueError("Manifest korpus sintetis memuat sample ID duplikat.")
        seen_sample_ids.add(sample_id)
        sample_ids.append(sample_id)
    sample_ids.sort()

    sample_results: list[dict] = []
    failures: list[dict] = []
    for index, sample_id in enumerate(sample_ids, start=1):
        try:
            result = evaluator.evaluate(
                sample_id,
                use_local_windows_ocr=True,
                windows_ocr_language=language_tag,
            )
            if result.get("network_mode") != "disabled_local_windows_ocr" or result.get("ocr_requests_sent") != 0:
                raise ValueError("Evaluasi korpus harus tetap menggunakan OCR lokal tanpa request jaringan.")
            if result.get("dataset_manifest_sha256") != manifest_sha256:
                raise ValueError("Manifest berubah selama evaluasi korpus OCR.")
            if result.get("ocr_images_processed") != result.get("ocr_images_planned"):
                raise ValueError("Tidak semua gambar scan pada sampel berhasil diproses oleh OCR lokal.")
            if not isinstance(result.get("reference_word_count"), int) or result["reference_word_count"] <= 0:
                raise ValueError("Teks referensi sampel kosong atau jumlah token tidak valid.")
            sample_results.append({
                "sample_id": sample_id,
                "dataset_manifest_sha256": result["dataset_manifest_sha256"],
                "sample_pdf_sha256": result["sample_pdf_sha256"],
                "reference_text_sha256": result["reference_text_sha256"],
                "pdf_pages": result["pdf_pages"],
                "ocr_images_planned": result["ocr_images_planned"],
                "ocr_images_processed": result["ocr_images_processed"],
                "ocr_requests_sent": result["ocr_requests_sent"],
                "reference_word_count": result["reference_word_count"],
                "ocr_word_count": result["ocr_word_count"],
                "word_edits": result["word_edits"],
                "word_error_rate": result["word_error_rate"],
                "pipeline_version": result["pipeline_version"],
                "evaluator_sha256": result["evaluator_sha256"],
                "ocr_bridge_sha256": result["ocr_bridge_sha256"],
                "ocr_engine_version": result["ocr_engine_version"],
            })
        except (OSError, ValueError, json.JSONDecodeError) as error:
            failures.append({"sample_id": sample_id, "error_type": type(error).__name__})
        if index % 4 == 0 or index == len(sample_ids):
            print(
                f"Windows OCR sintetis: {index}/{len(sample_ids)} sampel; "
                f"berhasil={len(sample_results)}, gagal={len(failures)}",
                file=sys.stderr,
                flush=True,
            )

    dataset_snapshot_after = pinned_dataset_snapshot_sha256(evaluator.DATASET)
    if dataset_snapshot_after != dataset_snapshot_before:
        raise ValueError("Korpus sintetis berubah selama evaluasi OCR; hasil tidak dapat diterbitkan.")
    if normalized_file_sha256(runner_path) != runner_sha256_before:
        raise ValueError("Runner OCR berubah selama evaluasi; hasil tidak dapat diterbitkan.")
    if normalized_file_sha256(fingerprint_helper_path) != fingerprint_helper_sha256_before:
        raise ValueError("Helper fingerprint berubah selama evaluasi; hasil tidak dapat diterbitkan.")
    for key in ("pipeline_version", "evaluator_sha256", "ocr_bridge_sha256", "ocr_engine_version"):
        if len({row[key] for row in sample_results}) > 1:
            raise ValueError(f"Versi {key} berubah di tengah evaluasi korpus OCR.")

    complete = len(sample_results) == len(sample_ids) and not failures
    reference_words = sum(row["reference_word_count"] for row in sample_results)
    ocr_words = sum(row["ocr_word_count"] for row in sample_results)
    edits = sum(row["word_edits"] for row in sample_results)
    return {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": "synthetic-cv-32",
        "dataset_manifest_sha256": manifest_sha256,
        "dataset_snapshot_sha256": dataset_snapshot_before,
        "network_mode": "disabled_local_windows_ocr",
        "ocr_engine": "Windows.Media.Ocr",
        "ocr_language": language_tag,
        "ocr_model_fingerprint": None,
        "python_version": platform.python_version(),
        "pipeline_version": sample_results[0]["pipeline_version"] if sample_results else None,
        "dependency_versions": {
            name: importlib.metadata.version(name)
            for name in ("pypdf", "python-docx", "Pillow", "lxml", "typing-extensions")
        },
        "requirements_sha256": hashlib.sha256(
            (evaluator.ROOT / "requirements.txt").read_bytes()
        ).hexdigest(),
        "status": "complete" if complete else "partial",
        "samples_attempted": len(sample_ids),
        "samples_processed": len(sample_results),
        "samples_failed": len(failures),
        "ocr_images_processed": sum(row["ocr_images_processed"] for row in sample_results),
        "ocr_requests_sent": sum(row["ocr_requests_sent"] for row in sample_results),
        "pdf_pages": sum(row["pdf_pages"] for row in sample_results),
        "reference_word_count": reference_words if complete else None,
        "ocr_word_count": ocr_words if complete else None,
        "word_edits": edits if complete else None,
        "corpus_micro_word_error_rate": round(edits / reference_words, 4) if complete and reference_words else None,
        "runner_sha256": runner_sha256_before,
        "dataset_fingerprint_helper_sha256": fingerprint_helper_sha256_before,
        "evaluator_sha256": sample_results[0]["evaluator_sha256"] if sample_results else None,
        "ocr_bridge_sha256": sample_results[0]["ocr_bridge_sha256"] if sample_results else None,
        "ocr_engine_version": sample_results[0]["ocr_engine_version"] if sample_results else None,
        "per_sample_aggregate": sample_results,
        "failures": failures,
        "limitations": [
            "The bundled corpus is synthetic and English-language; this does not decide M0 pilot languages or job family.",
            "WER uses corpus text references, not independently human-adjudicated OCR ground truth.",
            "Windows manages the OCR model and exposes no stable model fingerprint.",
            "Aggregate synthetic results do not establish production OCR quality, hiring quality, or fairness.",
            "OCR output text is not printed or persisted; only aggregate metrics, sample IDs, and fingerprints are retained.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--language",
        default="en-US",
        help="Installed Windows OCR language tag to probe (default: en-US).",
    )
    args = parser.parse_args()
    try:
        report = evaluate_corpus(args.language)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Synthetic Windows OCR corpus evaluation failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
