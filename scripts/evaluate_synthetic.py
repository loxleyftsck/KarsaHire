"""Summarize the local text-parser baseline against the bundled synthetic CV labels.

This is a development aid, not a hiring-quality benchmark. It reads the source
dataset's text references, so it does not evaluate PDF extraction or OCR.
"""

from __future__ import annotations

import json
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "synthetic-cv-32"
SAMPLE_ID_RE = re.compile(r"r\d{5}\Z")
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def safe_dataset_file(dataset_root: Path, sample_id: str, filename: str) -> Path:
    root = dataset_root.resolve()
    if not SAMPLE_ID_RE.fullmatch(sample_id):
        raise ValueError("ID sampel tidak mengikuti format korpus sintetis.")
    path = (root / sample_id / filename).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Path sampel sintetis berada di luar direktori dataset.")
    return path


def update_digest(digest, label: str, contents: bytes) -> None:
    digest.update(label.encode("ascii") + b"\0")
    digest.update(len(contents).to_bytes(8, "big"))
    digest.update(contents)


def evaluate(dataset_root: Path = DATASET) -> dict:
    dataset_root = dataset_root.resolve()
    manifest_path = (dataset_root / "manifest.json").resolve()
    if not manifest_path.is_relative_to(dataset_root):
        raise ValueError("Manifest dataset berada di luar direktori dataset.")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("Manifest dataset kosong atau formatnya tidak valid.")

    supported_skills = {server.normalize(skill) for skill in server.SKILLS}
    dataset_digest = hashlib.sha256()
    update_digest(dataset_digest, "manifest.json", manifest_bytes)
    matched_predictions = predictions_without_reference_label = reference_labels_without_prediction = 0
    unsupported_reference_labels: dict[str, int] = {}
    predicted_without_reference_label: dict[str, int] = {}
    experience_total = experience_mentions_found = 0
    education_degree_entries = 0
    education_labels_present_in_text = 0
    education_labels_detected = 0
    education_mentions_detected = 0
    education_mentions_matching_source_label = 0
    samples_missing_inputs: list[str] = []

    seen_ids: set[str] = set()
    for row_number, entry in enumerate(manifest, start=1):
        sample_id = entry.get("sample_id") if isinstance(entry, dict) else None
        if not isinstance(sample_id, str) or not SAMPLE_ID_RE.fullmatch(sample_id):
            raise ValueError(f"ID sampel pada baris manifest {row_number} tidak valid.")
        if sample_id in seen_ids:
            raise ValueError(f"ID sampel duplikat pada baris manifest {row_number}.")
        seen_ids.add(sample_id)

        text_path = safe_dataset_file(dataset_root, sample_id, "resume_text.txt")
        expected_path = safe_dataset_file(dataset_root, sample_id, "expected.json")
        metadata_path = safe_dataset_file(dataset_root, sample_id, "metadata.json")
        if not all(path.is_file() for path in (text_path, expected_path, metadata_path)):
            samples_missing_inputs.append(sample_id)
            continue

        text_bytes = text_path.read_bytes()
        expected_bytes = expected_path.read_bytes()
        metadata_bytes = metadata_path.read_bytes()
        for filename, contents in (
            ("resume_text.txt", text_bytes),
            ("expected.json", expected_bytes),
            ("metadata.json", metadata_bytes),
        ):
            update_digest(dataset_digest, f"{sample_id}/{filename}", contents)
        text = text_bytes.decode("utf-8")
        expected = json.loads(expected_bytes.decode("utf-8"))
        metadata = json.loads(metadata_bytes.decode("utf-8"))
        profile = server.profile_from_text(text)

        expected_skills: set[str] = set()
        for skill in expected.get("skills", []):
            label = str(skill.get("skill_name", "")).strip() if isinstance(skill, dict) else ""
            normalized = server.normalize(label)
            if not normalized:
                continue
            if normalized in supported_skills:
                expected_skills.add(normalized)
            else:
                unsupported_reference_labels[label] = unsupported_reference_labels.get(label, 0) + 1

        predicted_skills = {server.normalize(skill) for skill in profile["skills"]}
        matched_predictions += len(predicted_skills & expected_skills)
        unmatched_predictions = predicted_skills - expected_skills
        predictions_without_reference_label += len(unmatched_predictions)
        for skill in unmatched_predictions:
            predicted_without_reference_label[skill] = predicted_without_reference_label.get(skill, 0) + 1
        reference_labels_without_prediction += len(expected_skills - predicted_skills)

        expected_years = metadata.get("years_experience")
        if expected_years is not None:
            experience_total += 1
            if profile["experience_duration_text"] is not None:
                experience_mentions_found += 1

        predicted_education = [server.normalize(label) for label in profile["education_levels_mentioned"]]
        normalized_text = server.normalize(text)
        expected_education_labels = [
            server.normalize(str(education.get("degree", "")).strip())
            for education in expected.get("educations", [])
            if isinstance(education, dict) and str(education.get("degree", "")).strip()
        ]
        education_mentions_detected += len(predicted_education)
        education_mentions_matching_source_label += sum(
            any(label in mention for label in expected_education_labels)
            for mention in predicted_education
        )
        for education in expected.get("educations", []):
            label = str(education.get("degree", "")).strip() if isinstance(education, dict) else ""
            normalized_label = server.normalize(label)
            if not normalized_label:
                continue
            education_degree_entries += 1
            if normalized_label in normalized_text:
                education_labels_present_in_text += 1
                if any(normalized_label in mention for mention in predicted_education):
                    education_labels_detected += 1

    if samples_missing_inputs:
        raise ValueError(
            "Berkas referensi hilang untuk sampel: " + ", ".join(samples_missing_inputs)
        )

    strict_precision = ratio(
        matched_predictions, matched_predictions + predictions_without_reference_label
    )
    labeled_recall = ratio(
        matched_predictions, matched_predictions + reference_labels_without_prediction
    )
    f1 = (
        round(2 * strict_precision * labeled_recall / (strict_precision + labeled_recall), 4)
        if strict_precision is not None and labeled_recall is not None and strict_precision + labeled_recall
        else None
    )
    duration_probe_cases = (
        ("Python engineer with 1.5 years of production experience.", 1.5, "1.5 years"),
        ("Pengalaman Python selama 1,5 tahun.", 1.5, "selama 1,5 tahun"),
        ("Age: 30 years old. Python engineer with five years of experience.", 5, "five years"),
        ("Usia 30,5 tahun.", None, None),
    )
    duration_probe_matches = sum(
        server.profile_from_text(text)["experience_years_mentioned"] == expected_years
        and server.profile_from_text(text)["experience_duration_text"] == expected_phrase
        for text, expected_years, expected_phrase in duration_probe_cases
    )
    evaluator_bytes = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    return {
        "dataset": "synthetic-cv-32",
        "pipeline_version": server.pipeline_version(),
        "dataset_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "dataset_content_sha256": dataset_digest.hexdigest(),
        "evaluator_sha256": hashlib.sha256(evaluator_bytes).hexdigest(),
        "network_mode": "disabled",
        "samples_processed": len(seen_ids),
        "strict_reference_overlap": {
            "matched_predictions": matched_predictions,
            "predictions_without_matching_reference_label": predictions_without_reference_label,
            "reference_labels_without_prediction": reference_labels_without_prediction,
            "precision_if_unmatched_labels_are_treated_as_errors": strict_precision,
            "recall_against_available_reference_labels": labeled_recall,
            "f1_if_unmatched_labels_are_treated_as_errors": f1,
            "unsupported_reference_label_count": sum(unsupported_reference_labels.values()),
            "unsupported_reference_labels": dict(sorted(unsupported_reference_labels.items())),
            "prediction_without_reference_label_count": predictions_without_reference_label,
            "predicted_skills_without_matching_reference_label": dict(
                sorted(predicted_without_reference_label.items(), key=lambda item: (-item[1], item[0]))
            ),
            "interpretation": (
                "Strict label overlap only. Predictions without a matching reference label are not verified errors; "
                "review source text and label completeness before calling them false positives. Recall covers only "
                "available in-vocabulary reference labels."
            ),
        },
        "experience_duration_mention_coverage": {
            "samples_with_reference_years_metadata": experience_total,
            "samples_with_explicit_duration_phrase": experience_mentions_found,
            "samples_without_explicit_duration_phrase": experience_total - experience_mentions_found,
            "coverage": ratio(experience_mentions_found, experience_total),
            "note": "Metadata years_experience describes career duration; it is not ground truth for an explicit phrase extractor.",
        },
        "experience_duration_format_probe": {
            "cases_checked": len(duration_probe_cases),
            "cases_matched": duration_probe_matches,
            "all_cases_matched": duration_probe_matches == len(duration_probe_cases),
            "note": "Small controlled fixtures cover decimal separators and labeled-age separation; not a representative language benchmark.",
        },
        "education_degree_label_coverage": {
            "expected_degree_entries": education_degree_entries,
            "labels_present_verbatim_in_source_text": education_labels_present_in_text,
            "labels_detected_as_literal_credential_mentions": education_labels_detected,
            "coverage_of_labels_present_in_text": ratio(
                education_labels_detected, education_labels_present_in_text
            ),
            "credential_mentions_detected": education_mentions_detected,
            "mentions_matching_an_available_source_label": education_mentions_matching_source_label,
            "mentions_without_a_matching_source_label": (
                education_mentions_detected - education_mentions_matching_source_label
            ),
            "note": (
                "Literal label overlap against synthetic source text only. This does not verify degree equivalency, "
                "credential authenticity, education level, or suitability for a role. Unmatched mentions are not "
                "confirmed extraction errors because source labels may be incomplete or omit non-degree credentials."
            ),
        },
        "limitations": [
            "Evaluates resume_text.txt references; PDF extraction and OCR are not evaluated.",
            "Source labels may omit skills present in the text; false positives need human review.",
            "The strict precision/F1 arithmetic treats unmatched labels as errors only for a conservative overlap score; they are not confirmed extraction errors until a reviewer checks the source text and label coverage.",
            "Recall is calculated against available in-vocabulary labels; omitted or out-of-vocabulary labels are not measured.",
            "Synthetic English CVs do not establish quality, fairness, or readiness for real hiring.",
            "Education coverage measures literal synthetic labels and does not equate credential systems or validate credentials.",
        ],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Evaluasi gagal: {error}", file=sys.stderr)
        raise SystemExit(2)
