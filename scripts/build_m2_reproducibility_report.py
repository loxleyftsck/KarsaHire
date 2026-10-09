"""Build an aggregate-only M2 baseline report from local synthetic evaluators."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import importlib.metadata
import json
import platform
import re
from pathlib import Path
import subprocess
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate_synthetic
import evaluate_synthetic_formats
import evaluate_synthetic_ocr
import evaluate_synthetic_pdfs
import server
from synthetic_dataset_fingerprint import pinned_dataset_snapshot_sha256


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=True,
            text=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def synthetic_fixture_profile(dataset_root: Path) -> dict[str, int]:
    """Return aggregate identity-pattern coverage without exposing fixture values."""
    dataset_root = dataset_root.resolve(strict=True)
    manifest_path = (dataset_root / "manifest.json").resolve(strict=True)
    if not manifest_path.is_relative_to(dataset_root):
        raise ValueError("Synthetic dataset manifest resolves outside its dataset directory.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, list) or len(manifest) != server.SYNTHETIC_DATASET_SIZE:
        raise ValueError("Synthetic dataset manifest has an unexpected sample count.")

    sample_ids: list[str] = []
    seen_ids: set[str] = set()
    for entry in manifest:
        sample_id = entry.get("sample_id") if isinstance(entry, dict) else None
        if (not isinstance(sample_id, str) or not evaluate_synthetic.SAMPLE_ID_RE.fullmatch(sample_id)
                or sample_id in seen_ids):
            raise ValueError("Synthetic dataset manifest contains an invalid or duplicate sample ID.")
        sample_ids.append(sample_id)
        seen_ids.add(sample_id)

    given_names: list[str] = []
    phone_masks: set[str] = set()
    missing_names = 0
    missing_phones = 0
    for sample_id in sample_ids:
        path = (dataset_root / sample_id / "expected.json").resolve(strict=True)
        if not path.is_relative_to(dataset_root):
            raise ValueError("A synthetic expected-label path resolves outside its dataset directory.")
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("A synthetic expected-label file is not a JSON object.")
        name = record.get("first_name")
        phone = record.get("phone")
        if isinstance(name, str) and name.strip():
            given_names.append(unicodedata.normalize("NFKC", name).strip().casefold())
        else:
            missing_names += 1
        if isinstance(phone, str) and phone.strip():
            phone_masks.add(re.sub(r"\d", "#", " ".join(phone.split())))
        else:
            missing_phones += 1

    name_counts = Counter(given_names)
    return {
        "samples_with_expected_labels": len(sample_ids),
        "missing_given_names": missing_names,
        "duplicate_given_name_groups": sum(count > 1 for count in name_counts.values()),
        "samples_with_phone_labels": len(sample_ids) - missing_phones,
        "missing_phone_labels": missing_phones,
        "phone_format_masks": len(phone_masks),
    }


def build_report() -> dict:
    dataset_root = ROOT / "data" / "synthetic-cv-32"
    dataset_snapshot_before = pinned_dataset_snapshot_sha256(dataset_root)
    fixture_profile = synthetic_fixture_profile(dataset_root)
    text_result = evaluate_synthetic.evaluate()
    format_result = evaluate_synthetic_formats.evaluate()
    pdf_result = evaluate_synthetic_pdfs.evaluate()
    ocr_result = evaluate_synthetic_ocr.evaluate("r00003")
    dataset_snapshot_after = pinned_dataset_snapshot_sha256(dataset_root)
    if dataset_snapshot_after != dataset_snapshot_before:
        raise ValueError("The bundled synthetic dataset changed while the M2 report was built.")
    overlap = text_result["strict_reference_overlap"]
    formats = format_result["formats"]
    source = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=5,
        check=False,
    )
    working_tree_state = "modified" if source.returncode == 0 and source.stdout.strip() else (
        "clean" if source.returncode == 0 else "unknown"
    )
    requirements = ROOT / "requirements.txt"
    dependency_names = ("pypdf", "python-docx", "Pillow", "lxml", "typing-extensions")
    dependency_versions = {
        name: importlib.metadata.version(name) for name in dependency_names
    }
    runner_hash = hashlib.sha256(
        Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()
    return {
        "run_date": date.today().isoformat(),
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": "synthetic-cv-32",
        "base_revision": base_revision(),
        "working_tree_state": working_tree_state,
        "network_mode": "disabled",
        "python_version": platform.python_version(),
        "pipeline_version": text_result["pipeline_version"],
        "dependency_versions": dependency_versions,
        "requirements_sha256": sha256(requirements),
        "report_builder_sha256": runner_hash,
        "dataset_manifest_sha256": text_result["dataset_manifest_sha256"],
        "dataset_snapshot_sha256": dataset_snapshot_before,
        "synthetic_fixture_profile": fixture_profile,
        "evaluations": {
            "text_label_overlap": {
                "samples_processed": text_result["samples_processed"],
                "matched_predictions": overlap["matched_predictions"],
                "predictions_without_matching_reference_label": overlap["predictions_without_matching_reference_label"],
                "available_reference_labels_without_prediction": overlap["reference_labels_without_prediction"],
                "unsupported_reference_label_count": overlap["unsupported_reference_label_count"],
                "strict_precision_if_unmatched_labels_are_errors": overlap["precision_if_unmatched_labels_are_treated_as_errors"],
                "recall_against_available_in_vocabulary_labels": overlap["recall_against_available_reference_labels"],
                "f1_if_unmatched_labels_are_errors": overlap["f1_if_unmatched_labels_are_treated_as_errors"],
                "dataset_content_sha256": text_result["dataset_content_sha256"],
                "evaluator_sha256": text_result["evaluator_sha256"],
                "interpretation": overlap["interpretation"],
            },
            "experience_duration_mention_coverage": text_result["experience_duration_mention_coverage"],
            "experience_duration_format_probe": text_result["experience_duration_format_probe"],
            "education_degree_label_coverage": text_result["education_degree_label_coverage"],
            "format_round_trip": {
                "samples_processed": format_result["samples_processed"],
                "dataset_content_sha256": format_result["dataset_content_sha256"],
                "evaluator_sha256": format_result["evaluator_sha256"],
                "txt": {"text_match_count": formats["txt"]["text_match_count"], "profile_match_count": formats["txt"]["profile_match_count"]},
                "docx": {"text_match_count": formats["docx"]["text_match_count"], "profile_match_count": formats["docx"]["profile_match_count"]},
                "text_pdf": {"text_match_count": formats["text_pdf"]["text_match_count"], "profile_match_count": formats["text_pdf"]["profile_match_count"]},
                "pdf_ascii_punctuation_probe": format_result["pdf_ascii_punctuation_probe"],
                "evidence_excerpt_focus_probe": format_result["evidence_excerpt_focus_probe"],
                "candidate_score_order_probe": format_result["candidate_score_order_probe"],
                "docx_table_order_probe": format_result["docx_table_order_probe"],
                "pdf_page_attribution_probe": format_result["pdf_page_attribution_probe"],
                "limitations": format_result["limitations"],
            },
            "scanned_pdf_preflight": {
                "pdfs_expected": pdf_result["pdfs_expected"],
                "pdfs_read": pdf_result["pdfs_read"],
                "pages_read": pdf_result["pages_read"],
                "pages_with_extractable_text": pdf_result["pages_with_extractable_text"],
                "pages_without_extractable_text": pdf_result["pages_without_extractable_text"],
                "ocr_required_for_textless_pages": pdf_result["ocr_required_for_textless_pages"],
                "network_mode": "disabled",
            },
            "ocr_preflight": {
                key: ocr_result[key]
                for key in (
                    "sample_id", "ocr_model", "sample_pdf_sha256", "reference_text_sha256",
                    "evaluator_sha256", "pdf_pages", "ocr_images_planned", "ocr_requests_sent",
                    "network_mode", "status", "pipeline_version",
                )
            },
        },
        "limits": [
            "The bundled corpus is synthetic, English-language, and IT-focused; it does not define the still-TBD M0 pilot language or job family.",
            "The pinned 32-sample fixture has its own aggregate identity-pattern profile; one phone mask and no repeated given-name group do not establish redaction coverage of natural identifier variation.",
            "Language values in metadata do not change the English prose in this fixture; parser results do not establish Indonesian or other-language CV support.",
            "Source labels may be incomplete; strict overlap counts are not verified false-positive rates.",
            "Text/PDF/DOCX round-trip tests use controlled transformations from the same source text, not independently authored documents.",
            "No independently reviewed/adjudicated sample was supplied, so human agreement and parser-vs-adjudication metrics remain unavailable.",
            "Education results count literal mentions from synthetic labels; they do not establish degree equivalency, credential authenticity, or hiring relevance.",
            "Results do not establish real-CV accuracy, fairness, or production readiness.",
        ],
        "privacy": "Aggregate counts and fingerprints only; no CV text, candidate profiles, or OCR payloads are included.",
    }


def main() -> int:
    try:
        print(json.dumps(build_report(), ensure_ascii=False, indent=2))
        return 0
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        importlib.metadata.PackageNotFoundError,
    ) as error:
        print(f"M2 reproducibility report failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
