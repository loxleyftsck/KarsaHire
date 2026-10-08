"""Report reviewer agreement and parser evidence metrics from an annotation CSV.

Only aggregate metrics are written to stdout. The input must not contain CV text,
names, contact information, demographic attributes, or free-text comments.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

if __package__:
    from .evaluation_policy import (
        MIN_REPORTING_CANDIDATES,
        REPORTING_POLICY_STATUS,
        REPORTING_POLICY_VERSION,
        evaluator_fingerprints,
        require_external_evaluation_path,
    )
else:
    from evaluation_policy import (
        MIN_REPORTING_CANDIDATES,
        REPORTING_POLICY_STATUS,
        REPORTING_POLICY_VERSION,
        evaluator_fingerprints,
        require_external_evaluation_path,
    )

ROOT = Path(__file__).resolve().parents[1]


FIELDS = (
    "requisition_id",
    "candidate_id",
    "criteria_version",
    "criterion_id",
    "pipeline_version",
    "job_family",
    "cv_language",
    "source_format",
    "model_result",
    "model_evidence_ref",
    "model_evidence_page",
    "recruiter_reference_label",
    "hiring_manager_reference_label",
    "adjudicated_reference_label",
    "recruiter_label",
    "hiring_manager_label",
    "adjudicated_label",
)
LABELS = ("supported", "partial", "no_evidence", "needs_verification")
REFERENCE_LABELS = ("valid", "incorrect", "missing", "not_applicable")
REFERENCE_REVIEW_LABELS = ("valid", "incorrect")
MODEL_LABELS = {
    "matched": "supported",
    "partial": "partial",
    "unknown": "no_evidence",
    "needs_verification": "needs_verification",
    "parse_error": "needs_verification",
}
ANONYMOUS_ID_PATTERNS = {
    "requisition_id": re.compile(r"job_[a-f0-9]{12}"),
    "candidate_id": re.compile(r"cand_[a-f0-9]{12}"),
    "criterion_id": re.compile(r"crit_[a-f0-9]{12}"),
    "model_evidence_ref": re.compile(r"ev_[a-f0-9]{12}"),
}
CRITERIA_VERSION = re.compile(r"v[0-9]{1,3}(?:\.[0-9]{1,3}){0,2}")
JOB_FAMILY = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
CV_LANGUAGE = re.compile(r"(?:[a-z]{2,3}(?:-[a-z0-9]{2,8})*|unknown)")
PIPELINE_VERSION = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
SOURCE_FORMATS = frozenset({"pdf_text", "pdf_scan", "docx", "txt", "image", "other", "unknown"})
STRATUM_FIELDS = ("criterion_id", "job_family", "cv_language", "source_format")
EVIDENCE_EXPECTED_MODEL_RESULTS = frozenset({"matched", "partial", "needs_verification"})
PAGE_NUMBER_FORMATS = frozenset({"pdf_text", "pdf_scan", "image"})
def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def cohen_kappa(
    left: list[str], right: list[str], labels: tuple[str, ...] = LABELS
) -> float | None:
    count = len(left)
    if not count:
        return None
    observed = sum(a == b for a, b in zip(left, right)) / count
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(left_counts[label] * right_counts[label] for label in labels) / (count * count)
    if expected == 1:
        return None
    return round((observed - expected) / (1 - expected), 4)


def agreement_metrics(
    left: list[str], right: list[str], labels: tuple[str, ...] = LABELS,
    candidate_ids: list[str] | None = None,
) -> dict:
    count = len(left)
    if len(left) != len(right):
        raise ValueError("Reviewer labels must have matching lengths.")
    if candidate_ids is None:
        candidate_ids = [str(index) for index in range(count)]
    if len(candidate_ids) != count:
        raise ValueError("Reviewer labels and candidate IDs must have matching lengths.")
    exact = sum(a == b for a, b in zip(left, right))
    exact_candidates = {
        candidate_id for candidate_id, a, b in zip(candidate_ids, left, right) if a == b
    }
    disagreement_candidates = {
        candidate_id for candidate_id, a, b in zip(candidate_ids, left, right) if a != b
    }
    agreement_suppressed = any(
        0 < len(group) < MIN_REPORTING_CANDIDATES
        for group in (exact_candidates, disagreement_candidates)
    )
    return {
        "double_reviewed_rows": count,
        "exact_agreement_count": None if agreement_suppressed else exact,
        "exact_agreement_rate": None if agreement_suppressed else ratio(exact, count),
        "cohen_kappa": None if agreement_suppressed else cohen_kappa(left, right, labels=labels),
        "agreement_suppressed": agreement_suppressed,
    }


def model_metrics(
    actual: list[str], predicted: list[str], candidate_ids: list[str] | None = None
) -> dict | None:
    if not actual:
        return None
    if candidate_ids is None:
        candidate_ids = [str(index) for index in range(len(actual))]
    if len(candidate_ids) != len(actual) or len(actual) != len(predicted):
        raise ValueError("Model metric labels and candidate IDs must have matching lengths.")
    correct = sum(a == p for a, p in zip(actual, predicted))
    correct_candidates = {
        candidate_id for candidate_id, actual_label, predicted_label in zip(candidate_ids, actual, predicted)
        if actual_label == predicted_label
    }
    incorrect_candidates = {
        candidate_id for candidate_id, actual_label, predicted_label in zip(candidate_ids, actual, predicted)
        if actual_label != predicted_label
    }
    accuracy_suppressed = any(
        0 < len(group) < MIN_REPORTING_CANDIDATES
        for group in (correct_candidates, incorrect_candidates)
    )
    by_label = {}
    contributors_by_label = {}
    for label in LABELS:
        contributors_by_label[label] = {
            candidate_id
            for candidate_id, actual_label, predicted_label in zip(candidate_ids, actual, predicted)
            if actual_label == label or predicted_label == label
        }
        tp = sum(a == label and p == label for a, p in zip(actual, predicted))
        fp = sum(a != label and p == label for a, p in zip(actual, predicted))
        fn = sum(a == label and p != label for a, p in zip(actual, predicted))
        by_label[label] = {
            "support": sum(a == label for a in actual),
            "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn),
            "f1": ratio(2 * tp, 2 * tp + fp + fn),
        }
    suppressed_labels = {
        label for label, contributors in contributors_by_label.items()
        if 0 < len(contributors) < MIN_REPORTING_CANDIDATES
    }
    if len(suppressed_labels) == 1:
        visible_labels = set(LABELS) - suppressed_labels
        complementary_label = max(
            visible_labels,
            key=lambda label: (len(contributors_by_label[label]), label),
        )
        suppressed_labels.add(complementary_label)
    for label in suppressed_labels:
        by_label[label] = None
    return {
        "compared_rows": len(actual),
        "accuracy": None if accuracy_suppressed else ratio(correct, len(actual)),
        "accuracy_suppressed": accuracy_suppressed,
        "by_evidence_label": by_label,
        "suppressed_labels": sorted(suppressed_labels),
    }


def evaluate(path: Path) -> dict:
    path = require_external_evaluation_path(path, ROOT, "Completed annotation CSVs")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if (reader.fieldnames is None or len(reader.fieldnames) != len(FIELDS)
                or set(reader.fieldnames) != set(FIELDS)):
            raise ValueError("Header CSV tidak cocok dengan template anotasi M2.")
        rows = list(reader)

    if not rows:
        raise ValueError("CSV belum memiliki baris anotasi.")

    seen: set[tuple[str, str, str, str]] = set()
    recruiter_labels: list[str] = []
    manager_labels: list[str] = []
    reviewer_candidate_rows: list[str] = []
    actual: list[str] = []
    predicted: list[str] = []
    adjudicated_candidate_rows: list[str] = []
    recruiter_reference_labels: list[str] = []
    manager_reference_labels: list[str] = []
    reviewer_reference_candidate_rows: list[str] = []
    adjudicated_reference_labels: list[str] = []
    expected_adjudicated_reference_labels: list[str] = []
    adjudicated_reference_status_candidates: dict[str, set[str]] = {}
    expected_adjudicated_reference_status_candidates: dict[str, set[str]] = {}
    reviewer_reference_double_reviewed = 0
    all_candidate_ids: set[str] = set()
    reviewer_candidate_ids: set[str] = set()
    unreviewed_candidate_ids: set[str] = set()
    adjudicated_candidate_ids: set[str] = set()
    unadjudicated_candidate_ids: set[str] = set()
    evidence_locator_candidate_ids: set[str] = set()
    evidence_locator_present_candidate_ids: set[str] = set()
    evidence_locator_missing_candidate_ids: set[str] = set()
    page_locator_candidate_ids: set[str] = set()
    page_locator_present_candidate_ids: set[str] = set()
    page_locator_missing_candidate_ids: set[str] = set()
    reference_review_candidate_ids: set[str] = set()
    reference_unreviewed_candidate_ids: set[str] = set()
    reference_agreement_candidate_ids: set[str] = set()
    adjudicated_reference_candidate_ids: set[str] = set()
    unadjudicated_reference_candidate_ids: set[str] = set()
    model_result_candidates: dict[str, set[str]] = {}
    coverage = {field: Counter() for field in STRATUM_FIELDS}
    candidates_by_stratum: dict[str, dict[str, set[str]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    reviewer_candidates_by_stratum: dict[str, dict[str, set[str]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    model_candidates_by_stratum: dict[str, dict[str, set[str]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    model_result_counts: Counter[str] = Counter()
    reviewer_by_stratum: dict[str, dict[str, tuple[list[str], list[str], list[str]]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    model_by_stratum: dict[str, dict[str, tuple[list[str], list[str], list[str]]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    reviewer_reference_by_stratum: dict[str, dict[str, tuple[list[str], list[str], list[str]]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    adjudicated_reference_by_stratum: dict[str, dict[str, list[str]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    expected_adjudicated_reference_by_stratum: dict[str, dict[str, list[str]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    adjudicated_reference_status_candidates_by_stratum: dict[str, dict[str, dict[str, set[str]]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    expected_reference_status_candidates_by_stratum: dict[str, dict[str, dict[str, set[str]]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    reviewer_reference_candidates_by_stratum: dict[str, dict[str, set[str]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    adjudicated_reference_candidates_by_stratum: dict[str, dict[str, set[str]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    evidence_locator_counts = Counter()
    page_locator_counts = Counter()
    evidence_locator_by_stratum: dict[str, dict[str, Counter[str]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    page_locator_by_stratum: dict[str, dict[str, Counter[str]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    evidence_locator_candidates: dict[str, dict[str, set[str]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    page_locator_candidates: dict[str, dict[str, set[str]]] = {
        field: {} for field in STRATUM_FIELDS
    }
    evidence_locator_status_candidates: dict[str, dict[str, dict[str, set[str]]]] = {
        status: {field: {} for field in STRATUM_FIELDS}
        for status in ("present", "missing")
    }
    page_locator_status_candidates: dict[str, dict[str, dict[str, set[str]]]] = {
        status: {field: {} for field in STRATUM_FIELDS}
        for status in ("present", "missing")
    }
    criteria_versions: set[str] = set()
    pipeline_versions: set[str] = set()
    double_reviewed = adjudicated = 0
    for row_number, row in enumerate(rows, start=2):
        if None in row:
            raise ValueError(f"Baris {row_number} memiliki kolom tambahan; gunakan template tanpa kolom bebas.")
        key_fields = tuple((row.get(field) or "").strip() for field in FIELDS[:4])
        if any(not value for value in key_fields):
            raise ValueError(f"ID anonim pada baris {row_number} belum lengkap.")
        for field in ("requisition_id", "candidate_id", "criterion_id"):
            if not ANONYMOUS_ID_PATTERNS[field].fullmatch((row.get(field) or "").strip()):
                raise ValueError(f"Gunakan pseudonim berformat aman untuk {field} pada baris {row_number}.")
        criteria_version = (row.get("criteria_version") or "").strip()
        if not CRITERIA_VERSION.fullmatch(criteria_version):
            raise ValueError(f"Versi kriteria tidak valid pada baris {row_number}.")
        criteria_versions.add(criteria_version)
        pipeline_version = (row.get("pipeline_version") or "").strip()
        if not PIPELINE_VERSION.fullmatch(pipeline_version):
            raise ValueError(f"Versi pipeline tidak valid pada baris {row_number}.")
        pipeline_versions.add(pipeline_version)
        if key_fields in seen:
            raise ValueError(f"Baris {row_number} menggandakan kombinasi requisition/kandidat/kriteria.")
        seen.add(key_fields)

        strata = {}
        candidate_id = key_fields[1]
        all_candidate_ids.add(candidate_id)
        for field in STRATUM_FIELDS:
            value = (row.get(field) or "").strip()
            if field == "job_family" and not JOB_FAMILY.fullmatch(value):
                raise ValueError(f"Gunakan kode job_family huruf kecil yang aman pada baris {row_number}.")
            if field == "cv_language" and not CV_LANGUAGE.fullmatch(value):
                raise ValueError(f"Gunakan tag bahasa kecil seperti en atau id, atau unknown, pada baris {row_number}.")
            if field == "source_format" and value not in SOURCE_FORMATS:
                raise ValueError(f"source_format tidak valid pada baris {row_number}.")
            strata[field] = value
            coverage[field][value] += 1
            candidates_by_stratum[field].setdefault(value, set()).add(candidate_id)

        model_result = (row.get("model_result") or "").strip()
        if model_result not in MODEL_LABELS:
            raise ValueError(f"Label model tidak valid pada baris {row_number}.")
        model_result_counts[model_result] += 1
        model_result_candidates.setdefault(model_result, set()).add(candidate_id)
        evidence_ref = (row.get("model_evidence_ref") or "").strip()
        if evidence_ref and not ANONYMOUS_ID_PATTERNS["model_evidence_ref"].fullmatch(evidence_ref):
            raise ValueError(f"Gunakan referensi evidence anonim berformat aman pada baris {row_number}.")
        page = (row.get("model_evidence_page") or "").strip()
        if page and (not page.isdigit() or int(page) < 1):
            raise ValueError(f"Nomor halaman tidak valid pada baris {row_number}.")
        if page and not evidence_ref:
            raise ValueError(f"Nomor halaman pada baris {row_number} memerlukan model_evidence_ref.")
        if model_result in EVIDENCE_EXPECTED_MODEL_RESULTS:
            evidence_locator_candidate_ids.add(candidate_id)
            evidence_locator_counts["expected"] += 1
            evidence_locator_counts["present"] += bool(evidence_ref)
            evidence_locator_status = "present" if evidence_ref else "missing"
            (evidence_locator_present_candidate_ids if evidence_ref else evidence_locator_missing_candidate_ids).add(candidate_id)
            for field, value in strata.items():
                group = evidence_locator_by_stratum[field].setdefault(value, Counter())
                group["expected"] += 1
                group["present"] += bool(evidence_ref)
                evidence_locator_candidates[field].setdefault(value, set()).add(candidate_id)
                evidence_locator_status_candidates[evidence_locator_status][field].setdefault(value, set()).add(candidate_id)
            if strata["source_format"] in PAGE_NUMBER_FORMATS:
                page_locator_candidate_ids.add(candidate_id)
                page_locator_counts["expected"] += 1
                page_locator_counts["present"] += bool(evidence_ref and page)
                page_locator_status = "present" if evidence_ref and page else "missing"
                (page_locator_present_candidate_ids if page_locator_status == "present" else page_locator_missing_candidate_ids).add(candidate_id)
                for field, value in strata.items():
                    group = page_locator_by_stratum[field].setdefault(value, Counter())
                    group["expected"] += 1
                    group["present"] += bool(evidence_ref and page)
                    page_locator_candidates[field].setdefault(value, set()).add(candidate_id)
                    page_locator_status_candidates[page_locator_status][field].setdefault(value, set()).add(candidate_id)
        labels = {
            field: (row.get(field) or "").strip()
            for field in ("recruiter_label", "hiring_manager_label", "adjudicated_label")
        }
        for label in labels.values():
            if label and label not in LABELS:
                raise ValueError(f"Label anotasi tidak valid pada baris {row_number}.")
        reference_labels = {
            field: (row.get(field) or "").strip()
            for field in (
                "recruiter_reference_label",
                "hiring_manager_reference_label",
                "adjudicated_reference_label",
            )
        }
        for label in reference_labels.values():
            if label and label not in REFERENCE_LABELS:
                raise ValueError(f"Label referensi evidence tidak valid pada baris {row_number}.")
            if not label:
                continue
            if not evidence_ref:
                expected_reference_label = (
                    "missing"
                    if model_result in EVIDENCE_EXPECTED_MODEL_RESULTS
                    else "not_applicable"
                )
                if label != expected_reference_label:
                    raise ValueError(f"Label referensi evidence tidak cocok dengan locator pada baris {row_number}.")
            elif model_result not in EVIDENCE_EXPECTED_MODEL_RESULTS and label != "incorrect":
                raise ValueError(f"Referensi untuk hasil tanpa evidence harus ditandai incorrect pada baris {row_number}.")
            elif (
                label == "valid"
                and strata["source_format"] in PAGE_NUMBER_FORMATS
                and not page
            ):
                raise ValueError(f"Referensi halaman wajib tersedia untuk label valid pada baris {row_number}.")

        recruiter = labels["recruiter_label"]
        manager = labels["hiring_manager_label"]
        adjudicated_label = labels["adjudicated_label"]
        if adjudicated_label and not (recruiter and manager):
            raise ValueError(
                f"Baris {row_number} tidak dapat diadjudikasi sebelum label kedua reviewer lengkap."
            )
        recruiter_reference = reference_labels["recruiter_reference_label"]
        manager_reference = reference_labels["hiring_manager_reference_label"]
        adjudicated_reference = reference_labels["adjudicated_reference_label"]
        if adjudicated_reference and not (recruiter_reference and manager_reference):
            raise ValueError(
                f"Referensi pada baris {row_number} tidak dapat diadjudikasi sebelum kedua reviewer memeriksanya."
            )
        if recruiter and manager:
            double_reviewed += 1
            reviewer_candidate_ids.add(candidate_id)
            recruiter_labels.append(recruiter)
            manager_labels.append(manager)
            reviewer_candidate_rows.append(candidate_id)
            for field, value in strata.items():
                pair = reviewer_by_stratum[field].setdefault(value, ([], [], []))
                pair[0].append(recruiter)
                pair[1].append(manager)
                pair[2].append(candidate_id)
                reviewer_candidates_by_stratum[field].setdefault(value, set()).add(candidate_id)
        else:
            unreviewed_candidate_ids.add(candidate_id)

        if recruiter_reference and manager_reference:
            reviewer_reference_double_reviewed += 1
            reference_review_candidate_ids.add(candidate_id)
            if recruiter_reference in REFERENCE_REVIEW_LABELS and manager_reference in REFERENCE_REVIEW_LABELS:
                reference_agreement_candidate_ids.add(candidate_id)
                recruiter_reference_labels.append(recruiter_reference)
                manager_reference_labels.append(manager_reference)
                reviewer_reference_candidate_rows.append(candidate_id)
                for field, value in strata.items():
                    pair = reviewer_reference_by_stratum[field].setdefault(value, ([], [], []))
                    pair[0].append(recruiter_reference)
                    pair[1].append(manager_reference)
                    pair[2].append(candidate_id)
                    reviewer_reference_candidates_by_stratum[field].setdefault(value, set()).add(candidate_id)
        else:
            reference_unreviewed_candidate_ids.add(candidate_id)

        if adjudicated_label:
            adjudicated += 1
            adjudicated_candidate_ids.add(candidate_id)
            actual.append(adjudicated_label)
            predicted.append(MODEL_LABELS[model_result])
            adjudicated_candidate_rows.append(candidate_id)
            for field, value in strata.items():
                pair = model_by_stratum[field].setdefault(value, ([], [], []))
                pair[0].append(adjudicated_label)
                pair[1].append(MODEL_LABELS[model_result])
                pair[2].append(candidate_id)
                model_candidates_by_stratum[field].setdefault(value, set()).add(candidate_id)
        else:
            unadjudicated_candidate_ids.add(candidate_id)

        if adjudicated_reference:
            adjudicated_reference_candidate_ids.add(candidate_id)
            adjudicated_reference_labels.append(adjudicated_reference)
            adjudicated_reference_status_candidates.setdefault(adjudicated_reference, set()).add(candidate_id)
            if model_result in EVIDENCE_EXPECTED_MODEL_RESULTS:
                expected_adjudicated_reference_labels.append(adjudicated_reference)
                expected_adjudicated_reference_status_candidates.setdefault(adjudicated_reference, set()).add(candidate_id)
            for field, value in strata.items():
                adjudicated_reference_by_stratum[field].setdefault(value, []).append(adjudicated_reference)
                adjudicated_reference_candidates_by_stratum[field].setdefault(value, set()).add(candidate_id)
                adjudicated_reference_status_candidates_by_stratum[field].setdefault(value, {}).setdefault(
                    adjudicated_reference, set()
                ).add(candidate_id)
                if model_result in EVIDENCE_EXPECTED_MODEL_RESULTS:
                    expected_adjudicated_reference_by_stratum[field].setdefault(value, []).append(adjudicated_reference)
                    expected_reference_status_candidates_by_stratum[field].setdefault(value, {}).setdefault(
                        adjudicated_reference, set()
                    ).add(candidate_id)
        else:
            unadjudicated_reference_candidate_ids.add(candidate_id)

    if not double_reviewed and not adjudicated:
        raise ValueError("Belum ada baris yang ditinjau oleh kedua reviewer atau diadjudikasi.")
    if len(criteria_versions) != 1:
        raise ValueError("Satu CSV harus berisi satu criteria_version; evaluasi versi berbeda secara terpisah.")
    if len(pipeline_versions) != 1:
        raise ValueError("Satu CSV harus berisi satu pipeline_version; evaluasi versi berbeda secara terpisah.")

    agreement = agreement_metrics(
        recruiter_labels, manager_labels, candidate_ids=reviewer_candidate_rows
    )
    agreement["note"] = "Unweighted Cohen's kappa; null means no comparable rows or a degenerate marginal distribution."

    def eligible_values(field: str, values, candidates: dict[str, dict[str, set[str]]]) -> tuple[set[str], bool]:
        suppressed_values = {
            value for value in values
            if len(candidates[field].get(value, ())) < MIN_REPORTING_CANDIDATES
        }
        reported_values = set(values) - suppressed_values
        if len(suppressed_values) == 1 and reported_values:
            # Hide a second cell so totals cannot reveal the only low-count cell by subtraction.
            complementary = min(
                reported_values,
                key=lambda value: (len(candidates[field].get(value, ())), value),
            )
            reported_values.remove(complementary)
            suppressed_values.add(complementary)
        return reported_values, bool(suppressed_values)

    def eligible_outcome_values(
        field: str,
        values,
        candidates: dict[str, dict[str, set[str]]],
        outcome_candidates: dict[str, dict[str, dict[str, set[str]]]],
    ) -> tuple[set[str], bool]:
        suppressed_values = {
            value for value in values
            if len(candidates[field].get(value, ())) < MIN_REPORTING_CANDIDATES
            or any(
                0 < len(outcome_candidates[status][field].get(value, ())) < MIN_REPORTING_CANDIDATES
                for status in outcome_candidates
            )
        }
        reported_values = set(values) - suppressed_values
        if len(suppressed_values) == 1 and reported_values:
            complementary = min(
                reported_values,
                key=lambda value: (len(candidates[field].get(value, ())), value),
            )
            reported_values.remove(complementary)
            suppressed_values.add(complementary)
        return reported_values, bool(suppressed_values)

    def visible_strata(
        field: str,
        groups: dict[str, tuple],
        candidates: dict[str, dict[str, set[str]]],
        metric,
    ) -> dict:
        eligible = {}
        visible, suppressed = eligible_values(field, groups, candidates)
        for value in sorted(visible):
            result = metric(*groups[value])
            if result is not None:
                eligible[value] = result
        return {"reported": eligible, "suppressed": suppressed}

    def reviewer_agreement_metric(left: list[str], right: list[str], candidate_ids: list[str]) -> dict:
        return agreement_metrics(left, right, candidate_ids=candidate_ids)

    agreement_by_stratum = {
        field: visible_strata(field, groups, reviewer_candidates_by_stratum, reviewer_agreement_metric)
        for field, groups in reviewer_by_stratum.items()
    }
    model_metrics_all = model_metrics(actual, predicted, adjudicated_candidate_rows)
    model_metrics_by_stratum = {
        field: visible_strata(field, groups, model_candidates_by_stratum, model_metrics)
        for field, groups in model_by_stratum.items()
    }

    coverage_by_stratum = {}
    for field, counts in coverage.items():
        visible, suppressed = eligible_values(field, counts, candidates_by_stratum)
        eligible = {
            value: counts[value]
            for value in sorted(visible)
        }
        coverage_by_stratum[field] = {"reported": eligible, "suppressed": suppressed}

    def locator_presence(expected: int, present: int) -> dict:
        return {
            "expected_rows": expected,
            "present_rows": present,
            "missing_rows": expected - present,
            "presence_rate": ratio(present, expected),
        }

    def locator_presence_by_stratum(
        grouped_counts: dict[str, dict[str, Counter[str]]],
        candidates: dict[str, dict[str, set[str]]],
        outcome_candidates: dict[str, dict[str, dict[str, set[str]]]],
    ) -> dict:
        result = {}
        for field in STRATUM_FIELDS:
            expected_counts = Counter({
                value: counts["expected"]
                for value, counts in grouped_counts[field].items()
            })
            visible, suppressed = eligible_outcome_values(
                field, expected_counts, candidates, outcome_candidates
            )
            result[field] = {
                "reported": {
                    value: locator_presence(
                        grouped_counts[field][value]["expected"],
                        grouped_counts[field][value]["present"],
                    )
                    for value in sorted(visible)
                },
                "suppressed": suppressed,
            }
        return result

    def sparse_categories(
        labels: tuple[str, ...], candidates_by_label: dict[str, set[str]]
    ) -> set[str]:
        suppressed = {
            label for label in labels
            if 0 < len(candidates_by_label.get(label, ())) < MIN_REPORTING_CANDIDATES
        }
        if len(suppressed) == 1:
            available = set(labels) - suppressed
            complementary = max(
                available,
                key=lambda label: (len(candidates_by_label.get(label, ())), label),
            )
            suppressed.add(complementary)
        return suppressed

    def reference_assessment_metrics(
        statuses: list[str],
        expected_locator_statuses: list[str] | None = None,
        status_candidates: dict[str, set[str]] | None = None,
        expected_status_candidates: dict[str, set[str]] | None = None,
    ) -> dict:
        counts = Counter(statuses)
        expected_counts = Counter(
            statuses if expected_locator_statuses is None else expected_locator_statuses
        )
        status_candidates = status_candidates or {}
        expected_status_candidates = expected_status_candidates or status_candidates
        valid_count = counts["valid"]
        incorrect_count = counts["incorrect"]
        expected_locator_rows = (
            expected_counts["valid"] + expected_counts["incorrect"] + expected_counts["missing"]
        )
        expected_valid_rows = expected_counts["valid"]
        suppressed_statuses = sparse_categories(REFERENCE_LABELS, status_candidates)
        suppressed_validity = bool(sparse_categories(
            ("valid", "incorrect"), status_candidates
        ))
        suppressed_coverage = bool(sparse_categories(
            ("valid", "incorrect", "missing"), expected_status_candidates
        ))
        return {
            "assessed_rows": len(statuses),
            "status_counts": {
                label: None if label in suppressed_statuses else counts[label]
                for label in REFERENCE_LABELS
            },
            "status_counts_suppressed": bool(suppressed_statuses),
            "citation_validity_rows": None if suppressed_validity else valid_count + incorrect_count,
            "citation_validity_rate": None if suppressed_validity else ratio(valid_count, valid_count + incorrect_count),
            "citation_validity_suppressed": suppressed_validity,
            "expected_locator_rows": None if suppressed_coverage else expected_locator_rows,
            "citation_coverage_rate": None if suppressed_coverage else ratio(expected_valid_rows, expected_locator_rows),
            "citation_coverage_suppressed": suppressed_coverage,
        }

    def reference_agreement_metric(
        left: list[str], right: list[str], candidate_ids: list[str]
    ) -> dict:
        metrics = agreement_metrics(
            left, right, labels=REFERENCE_REVIEW_LABELS, candidate_ids=candidate_ids
        )
        metrics["note"] = "Rows marked missing or not_applicable are excluded because no source locator is being judged."
        return metrics

    def reference_quality_metric(
        statuses: list[str],
        expected_statuses: list[str],
        status_candidates: dict[str, set[str]],
        expected_status_candidates: dict[str, set[str]],
    ) -> dict:
        return reference_assessment_metrics(
            statuses, expected_statuses, status_candidates, expected_status_candidates
        )

    reference_agreement = reference_agreement_metric(
        recruiter_reference_labels, manager_reference_labels, reviewer_reference_candidate_rows
    )
    reference_agreement_by_stratum = {
        field: visible_strata(
            field, groups, reviewer_reference_candidates_by_stratum,
            reference_agreement_metric,
        )
        for field, groups in reviewer_reference_by_stratum.items()
    }
    reference_quality_groups_by_stratum = {
        field: {
            value: (
                statuses,
                expected_adjudicated_reference_by_stratum[field].get(value, []),
                adjudicated_reference_status_candidates_by_stratum[field].get(value, {}),
                expected_reference_status_candidates_by_stratum[field].get(value, {}),
            )
            for value, statuses in groups.items()
        }
        for field, groups in adjudicated_reference_by_stratum.items()
    }
    reference_quality_by_stratum = {
        field: visible_strata(
            field, groups, adjudicated_reference_candidates_by_stratum,
            reference_quality_metric,
        )
        for field, groups in reference_quality_groups_by_stratum.items()
    }

    unique_candidate_count = len(all_candidate_ids)
    sample_suppressed = unique_candidate_count < MIN_REPORTING_CANDIDATES
    suppressed_measures: set[str] = set()
    if model_metrics_all:
        if model_metrics_all["accuracy_suppressed"]:
            suppressed_measures.add("model_vs_adjudication.accuracy_outcome")
        if model_metrics_all["suppressed_labels"]:
            suppressed_measures.add("model_vs_adjudication.by_evidence_label")

    def guarded_measure(value, contributors: set[str], name: str, complements: tuple[set[str], ...] = ()):
        empty_zero_is_safe = not contributors and value == 0
        hidden = (len(contributors) < MIN_REPORTING_CANDIDATES and not empty_zero_is_safe) or any(
            0 < len(group) < MIN_REPORTING_CANDIDATES for group in complements
        )
        if hidden:
            suppressed_measures.add(name)
            return None
        return value

    input_rows = guarded_measure(len(rows), all_candidate_ids, "input_rows")
    reviewed_rows = guarded_measure(
        double_reviewed, reviewer_candidate_ids, "reviewer_double_reviewed_rows",
        (unreviewed_candidate_ids,),
    )
    adjudicated_rows = guarded_measure(
        adjudicated, adjudicated_candidate_ids, "adjudicated_rows",
        (unadjudicated_candidate_ids,),
    )
    reviewer_agreement_report = guarded_measure(
        agreement, reviewer_candidate_ids, "reviewer_agreement",
    )
    model_metrics_report = guarded_measure(
        model_metrics_all, adjudicated_candidate_ids, "model_vs_adjudication",
    )
    model_result_visible, model_result_suppressed = eligible_values(
        "model_result", model_result_counts, {"model_result": model_result_candidates}
    )
    if model_result_suppressed:
        suppressed_measures.add("model_result_counts")
    reported_model_result_counts = {
        "reported": {
            name: model_result_counts[name]
            for name in sorted(model_result_visible)
        },
        "suppressed": model_result_suppressed,
    }

    def guarded_locator_presence(
        expected: int,
        present: int,
        contributors: set[str],
        name: str,
        grouped_counts: dict[str, dict[str, Counter[str]]],
        dimension_candidates: dict[str, dict[str, set[str]]],
        present_candidates: set[str],
        missing_candidates: set[str],
        outcome_candidates: dict[str, dict[str, dict[str, set[str]]]],
    ) -> dict:
        result = locator_presence(expected, present)
        visible = guarded_measure(result, contributors, name, (present_candidates, missing_candidates))
        return {
            **(visible or {key: None for key in result}),
            "suppressed": visible is None,
            "by_stratum": locator_presence_by_stratum(
                grouped_counts, dimension_candidates, outcome_candidates
            ),
        }

    reference_reviewed_rows = guarded_measure(
        reviewer_reference_double_reviewed, reference_review_candidate_ids,
        "evidence_reference_review.reviewer_double_reviewed_rows",
        (reference_unreviewed_candidate_ids,),
    )
    reference_review_unreviewed_rows = guarded_measure(
        len(rows) - reviewer_reference_double_reviewed, reference_unreviewed_candidate_ids,
        "evidence_reference_review.reviewer_unreviewed_rows",
        (reference_review_candidate_ids,),
    )
    reference_review_rate = guarded_measure(
        ratio(reviewer_reference_double_reviewed, len(rows)), reference_review_candidate_ids,
        "evidence_reference_review.reviewer_review_rate",
        (reference_unreviewed_candidate_ids,),
    )
    reference_adjudicated_rows = guarded_measure(
        len(adjudicated_reference_labels), adjudicated_reference_candidate_ids,
        "evidence_reference_review.adjudicated_rows",
        (unadjudicated_reference_candidate_ids,),
    )
    reference_unadjudicated_rows = guarded_measure(
        len(rows) - len(adjudicated_reference_labels), unadjudicated_reference_candidate_ids,
        "evidence_reference_review.adjudication_unreviewed_rows",
        (adjudicated_reference_candidate_ids,),
    )
    reference_adjudication_rate = guarded_measure(
        ratio(len(adjudicated_reference_labels), len(rows)), adjudicated_reference_candidate_ids,
        "evidence_reference_review.adjudication_rate",
        (unadjudicated_reference_candidate_ids,),
    )
    reference_reviewer_agreement_report = guarded_measure(
        reference_agreement, reference_agreement_candidate_ids,
        "evidence_reference_review.reviewer_agreement",
    )
    reference_adjudicated_report = guarded_measure(
        reference_assessment_metrics(
            adjudicated_reference_labels,
            expected_adjudicated_reference_labels,
            adjudicated_reference_status_candidates,
            expected_adjudicated_reference_status_candidates,
        ), adjudicated_reference_candidate_ids,
        "evidence_reference_review.adjudicated",
    )
    if reviewer_agreement_report and reviewer_agreement_report["agreement_suppressed"]:
        suppressed_measures.add("reviewer_agreement.outcome")
    if reference_reviewer_agreement_report and reference_reviewer_agreement_report["agreement_suppressed"]:
        suppressed_measures.add("evidence_reference_review.reviewer_agreement.outcome")
    if reference_adjudicated_report:
        for field in (
            "status_counts_suppressed", "citation_validity_suppressed",
            "citation_coverage_suppressed",
        ):
            if reference_adjudicated_report[field]:
                suppressed_measures.add(f"evidence_reference_review.adjudicated.{field.removesuffix('_suppressed')}")

    fingerprints = evaluator_fingerprints(Path(__file__))
    return {
        "criteria_version": next(iter(criteria_versions)),
        "pipeline_version": next(iter(pipeline_versions)),
        "evaluator_sha256": fingerprints["evaluator_sha256"],
        "input_rows": input_rows,
        "sample_coverage": {
            "rows": input_rows,
            "by_stratum": coverage_by_stratum,
        },
        "stratum_privacy": {
            "policy_version": REPORTING_POLICY_VERSION,
            "policy_status": REPORTING_POLICY_STATUS,
            "policy_sha256": fingerprints["reporting_policy_sha256"],
            "minimum_unique_candidates": MIN_REPORTING_CANDIDATES,
            "candidate_count_unit": "distinct candidate_id values; reuse one pseudonym for a candidate across requisitions within the CSV",
            "note": "The five-candidate floor is provisional. M0 privacy governance must approve it before results are shared.",
        },
        "double_reviewed_rows": reviewed_rows,
        "adjudicated_rows": adjudicated_rows,
        "model_result_counts": reported_model_result_counts,
        "reviewer_agreement": reviewer_agreement_report,
        "reviewer_agreement_by_stratum": agreement_by_stratum,
        "model_vs_adjudication": model_metrics_report,
        "model_vs_adjudication_by_stratum": model_metrics_by_stratum,
        "evidence_locator_presence": {
            "reference": {
                **guarded_locator_presence(
                    evidence_locator_counts["expected"], evidence_locator_counts["present"],
                    evidence_locator_candidate_ids, "evidence_locator_presence.reference",
                    evidence_locator_by_stratum, evidence_locator_candidates,
                    evidence_locator_present_candidate_ids, evidence_locator_missing_candidate_ids,
                    evidence_locator_status_candidates,
                ),
            },
            "page_number": {
                **guarded_locator_presence(
                    page_locator_counts["expected"], page_locator_counts["present"],
                    page_locator_candidate_ids, "evidence_locator_presence.page_number",
                    page_locator_by_stratum, page_locator_candidates,
                    page_locator_present_candidate_ids, page_locator_missing_candidate_ids,
                    page_locator_status_candidates,
                ),
            },
            "note": "Presence is a completeness check only; it does not prove a reference or page points to text that supports the criterion.",
        },
        "evidence_reference_review": {
            "review_coverage": {
                "input_rows": input_rows,
                "reviewer_double_reviewed_rows": reference_reviewed_rows,
                "reviewer_unreviewed_rows": reference_review_unreviewed_rows,
                "reviewer_review_rate": reference_review_rate,
                "adjudicated_rows": reference_adjudicated_rows,
                "adjudication_unreviewed_rows": reference_unadjudicated_rows,
                "adjudication_rate": reference_adjudication_rate,
            },
            "reviewer_double_reviewed_rows": reference_reviewed_rows,
            "reviewer_agreement_rows": guarded_measure(
                len(recruiter_reference_labels), reference_agreement_candidate_ids,
                "evidence_reference_review.reviewer_agreement_rows",
            ),
            "reviewer_agreement": reference_reviewer_agreement_report,
            "adjudicated": reference_adjudicated_report,
            "reviewer_agreement_by_stratum": reference_agreement_by_stratum,
            "adjudicated_by_stratum": reference_quality_by_stratum,
            "note": "A valid locator is one that reviewers confirmed points to source text supporting or explaining the model result. This judgment is separate from whether the criterion label itself is correct.",
        },
        "overall_privacy": {
            "policy_version": REPORTING_POLICY_VERSION,
            "policy_status": REPORTING_POLICY_STATUS,
            "policy_sha256": fingerprints["reporting_policy_sha256"],
            "minimum_unique_candidates": MIN_REPORTING_CANDIDATES,
            "suppressed": sample_suppressed or bool(suppressed_measures),
            "sample_suppressed": sample_suppressed,
            "distinct_candidate_count": None if sample_suppressed else unique_candidate_count,
            "suppressed_measures": sorted(suppressed_measures),
            "note": "Each overall measure is withheld unless at least five distinct candidates contribute to that measure; complementary groups below the floor are also hidden. M0 privacy governance must approve or replace this provisional floor before results are shared.",
        },
        "limitations": [
            "Evidence labels describe what the CV supports; they are not candidate quality or hiring decisions.",
            "Evidence locator presence does not validate that the source citation is accurate or relevant; a reviewer must inspect the original document.",
            "Citation-validity metrics use the adjudicated human reference labels, not automatic PDF or text matching.",
            "Metrics describe only the supplied sample and do not establish fairness or production readiness.",
            "Stratum metrics may be unstable for small groups and their counts may expose individuals; keep outputs restricted and apply the approved minimum-cell rule before sharing.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Completed M2 annotation CSV")
    args = parser.parse_args()
    try:
        print(json.dumps(evaluate(args.csv_path), ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        print(f"Evaluasi anotasi gagal: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
