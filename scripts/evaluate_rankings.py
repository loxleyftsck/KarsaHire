"""Compare a frozen candidate order with blinded, adjudicated human ranks.

The input contains pseudonymous IDs and ordinal ranks only. This measures rank
agreement against an approved evidence-based rubric; it is not a hiring-quality
or candidate-suitability measure.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
from collections import defaultdict
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


FIELDS = (
    "requisition_id",
    "candidate_id",
    "criteria_version",
    "pipeline_version",
    "job_family",
    "cv_language",
    "source_format",
    "model_rank",
    "recruiter_rank",
    "hiring_manager_rank",
    "adjudicated_rank",
)
ID_PATTERNS = {
    "requisition_id": re.compile(r"job_[a-f0-9]{12}"),
    "candidate_id": re.compile(r"cand_[a-f0-9]{12}"),
}
VERSION_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
CRITERIA_VERSION_PATTERN = re.compile(r"v[0-9]{1,3}(?:\.[0-9]{1,3}){0,2}")
JOB_FAMILY_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
LANGUAGE_PATTERN = re.compile(r"(?:[a-z]{2,3}(?:-[a-z0-9]{2,8})*|unknown)")
SOURCE_FORMATS = frozenset({"pdf_text", "pdf_scan", "docx", "txt", "image", "other", "unknown"})
STRATA = ("job_family", "cv_language", "source_format")
TOP_K = 5
ROOT = Path(__file__).resolve().parents[1]
METRIC_NAMES = (
    "model_vs_adjudicated_kendall_tau_b",
    "recruiter_vs_hiring_manager_kendall_tau_b",
    "model_top_k_overlap_precision",
    "model_top_k_overlap_recall",
)
METRIC_CONTRIBUTORS = {
    "model_vs_adjudicated_kendall_tau_b": "model_tau",
    "recruiter_vs_hiring_manager_kendall_tau_b": "reviewer_tau",
    "model_top_k_overlap_precision": "top_k",
    "model_top_k_overlap_recall": "top_k",
}


def rank_value(raw: str, field: str, row_number: int) -> int:
    value = raw.strip()
    if not value or not value.isascii() or not value.isdecimal():
        raise ValueError(f"{field} must be a positive integer on row {row_number}.")
    rank = int(value)
    if rank < 1:
        raise ValueError(f"{field} must be a positive integer on row {row_number}.")
    return rank


def competition_ranks_valid(ranks: list[int]) -> bool:
    if not ranks:
        return False
    ordered = sorted(ranks)
    if ordered[0] != 1 or ordered[-1] > len(ordered):
        return False
    expected = [index + 1 for index, rank in enumerate(ordered) if index == 0 or rank != ordered[index - 1]]
    return sorted(set(ordered)) == expected


def kendall_tau_b(rows: list[dict], left_field: str, right_field: str) -> float | None:
    concordant = discordant = tied_left = tied_right = 0
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            left_delta = left[left_field] - right[left_field]
            right_delta = left[right_field] - right[right_field]
            if left_delta == 0 and right_delta == 0:
                continue
            if left_delta == 0:
                tied_left += 1
            elif right_delta == 0:
                tied_right += 1
            elif left_delta * right_delta > 0:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt(
        (concordant + discordant + tied_left)
        * (concordant + discordant + tied_right)
    )
    if denominator == 0:
        return None
    return round((concordant - discordant) / denominator, 4)


def top_k_overlap(rows: list[dict], k: int = TOP_K) -> tuple[float, float] | None:
    if len(rows) < k:
        return None
    model_top = {
        row["candidate_id"]
        for row in sorted(rows, key=lambda item: item["model_rank"])[:k]
    }
    adjudicated_boundary = sorted(row["adjudicated_rank"] for row in rows)[k - 1]
    adjudicated_top = {
        row["candidate_id"]
        for row in rows
        if row["adjudicated_rank"] <= adjudicated_boundary
    }
    overlap = len(model_top & adjudicated_top)
    return round(overlap / len(model_top), 4), round(overlap / len(adjudicated_top), 4)


def summarize_with_contributors(rows: list[dict]) -> tuple[dict, dict[str, set[str]]]:
    by_requisition: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_requisition[row["requisition_id"]].append(row)

    model_tau = []
    reviewer_tau = []
    top_k_precision = []
    top_k_recall = []
    contributors = {"model_tau": set(), "reviewer_tau": set(), "top_k": set()}
    for requisition_rows in by_requisition.values():
        if len(requisition_rows) < 2:
            continue
        tau = kendall_tau_b(requisition_rows, "model_rank", "adjudicated_rank")
        reviewer = kendall_tau_b(requisition_rows, "recruiter_rank", "hiring_manager_rank")
        if tau is not None:
            model_tau.append(tau)
            contributors["model_tau"].update(row["candidate_id"] for row in requisition_rows)
        if reviewer is not None:
            reviewer_tau.append(reviewer)
            contributors["reviewer_tau"].update(row["candidate_id"] for row in requisition_rows)
        overlap = top_k_overlap(requisition_rows)
        if overlap is not None:
            precision, recall = overlap
            top_k_precision.append(precision)
            top_k_recall.append(recall)
            contributors["top_k"].update(row["candidate_id"] for row in requisition_rows)

    def macro_mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    def guarded_metric(name: str, values: list[float]) -> dict:
        candidate_count = len(contributors[name])
        suppressed = candidate_count < MIN_REPORTING_CANDIDATES
        return {
            "requisitions": None if suppressed else len(values),
            "unique_candidates": None if suppressed else candidate_count,
            "macro_mean": None if suppressed else macro_mean(values),
            "suppressed": suppressed,
        }

    model_metric = guarded_metric("model_tau", model_tau)
    reviewer_metric = guarded_metric("reviewer_tau", reviewer_tau)
    precision_metric = guarded_metric("top_k", top_k_precision)
    recall_metric = guarded_metric("top_k", top_k_recall)

    summary = {
        "model_vs_adjudicated_kendall_tau_b": model_metric,
        "recruiter_vs_hiring_manager_kendall_tau_b": reviewer_metric,
        "top_k": TOP_K,
        "model_top_k_overlap_precision": precision_metric,
        "model_top_k_overlap_recall": recall_metric,
    }
    return summary, contributors


def summarize(rows: list[dict]) -> dict:
    return summarize_with_contributors(rows)[0]


def suppress_metric(metric: dict) -> None:
    metric.update({
        "requisitions": None,
        "unique_candidates": None,
        "macro_mean": None,
        "suppressed": True,
    })


def evaluate(path: Path) -> dict:
    path = require_external_evaluation_path(path, ROOT, "Completed ranking annotations")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError as error:
        raise ValueError("Ranking CSV must be UTF-8 encoded.") from error
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if (reader.fieldnames is None or len(reader.fieldnames) != len(FIELDS)
            or set(reader.fieldnames) != set(FIELDS)):
        raise ValueError("CSV header does not match the M2 ranking template.")
    source_rows = list(reader)
    if not source_rows:
        raise ValueError("Ranking CSV has no annotation rows.")

    rows = []
    seen: set[tuple[str, str]] = set()
    criteria_versions: set[str] = set()
    pipeline_versions: set[str] = set()
    for row_number, source in enumerate(source_rows, start=2):
        if None in source or any(value is None for value in source.values()):
            raise ValueError(f"CSV row {row_number} has missing or extra columns.")
        row = {field: (source.get(field) or "").strip() for field in FIELDS}
        for field in ("requisition_id", "candidate_id"):
            if not ID_PATTERNS[field].fullmatch(row[field]):
                raise ValueError(f"Anonymous {field} is invalid on row {row_number}.")
        key = (row["requisition_id"], row["candidate_id"])
        if key in seen:
            raise ValueError(f"Duplicate requisition/candidate row at line {row_number}.")
        seen.add(key)
        if not CRITERIA_VERSION_PATTERN.fullmatch(row["criteria_version"]):
            raise ValueError(f"criteria_version is invalid on row {row_number}.")
        if not VERSION_PATTERN.fullmatch(row["pipeline_version"]):
            raise ValueError(f"pipeline_version is invalid on row {row_number}.")
        if not JOB_FAMILY_PATTERN.fullmatch(row["job_family"]):
            raise ValueError(f"job_family is invalid on row {row_number}.")
        if not LANGUAGE_PATTERN.fullmatch(row["cv_language"]):
            raise ValueError(f"cv_language is invalid on row {row_number}.")
        if row["source_format"] not in SOURCE_FORMATS:
            raise ValueError(f"source_format is invalid on row {row_number}.")
        criteria_versions.add(row["criteria_version"])
        pipeline_versions.add(row["pipeline_version"])
        for field in ("model_rank", "recruiter_rank", "hiring_manager_rank", "adjudicated_rank"):
            row[field] = rank_value(row[field], field, row_number)
        rows.append(row)

    if len(criteria_versions) != 1 or len(pipeline_versions) != 1:
        raise ValueError("Evaluate one criteria_version and pipeline_version per CSV.")

    by_requisition: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_requisition[row["requisition_id"]].append(row)
    for requisition_rows in by_requisition.values():
        count = len(requisition_rows)
        if count < 2:
            raise ValueError("Each requisition needs at least two candidates for rank comparison.")
        if len({row["job_family"] for row in requisition_rows}) != 1:
            raise ValueError("Each requisition must use one job_family.")
        model_ranks = [row["model_rank"] for row in requisition_rows]
        if sorted(model_ranks) != list(range(1, count + 1)):
            raise ValueError("model_rank must be a unique, complete order from 1 through candidate count.")
        for field in ("recruiter_rank", "hiring_manager_rank", "adjudicated_rank"):
            if not competition_ranks_valid([row[field] for row in requisition_rows]):
                raise ValueError(f"{field} must use complete competition ranks with ties sharing positions.")
        for row in requisition_rows:
            for field in ("recruiter_rank", "hiring_manager_rank", "adjudicated_rank"):
                if row[field] > count:
                    raise ValueError(f"{field} exceeds the candidate count for a requisition.")

    unique_candidates = {row["candidate_id"] for row in rows}
    suppressed = len(unique_candidates) < MIN_REPORTING_CANDIDATES
    overall = None if suppressed else summarize(rows)
    by_stratum = {}
    for field in STRATA:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            grouped[row[field]].append(row)
        summaries: dict[str, dict] = {}
        contributors_by_group: dict[str, dict[str, set[str]]] = {}
        suppressed_cells = False
        for value, group_rows in sorted(grouped.items()):
            summaries[value], contributors_by_group[value] = summarize_with_contributors(group_rows)

        for metric_name in METRIC_NAMES:
            primary_suppressed = [
                value for value, contributors in contributors_by_group.items()
                if summaries[value][metric_name]["suppressed"]
            ]
            if not primary_suppressed:
                continue
            suppressed_cells = True
            if len(primary_suppressed) != 1:
                continue
            visible = [
                value for value, contributors in contributors_by_group.items()
                if value not in primary_suppressed
                and len(contributors[METRIC_CONTRIBUTORS[metric_name]]) >= MIN_REPORTING_CANDIDATES
            ]
            if visible:
                complementary = max(
                    visible,
                    key=lambda value: (
                        len(contributors_by_group[value][METRIC_CONTRIBUTORS[metric_name]]),
                        value,
                    ),
                )
                suppress_metric(summaries[complementary][metric_name])

        reported = {}
        for value, summary in summaries.items():
            available_metrics = [summary[name] for name in METRIC_NAMES]
            if all(metric["suppressed"] for metric in available_metrics):
                suppressed_cells = True
                continue
            if any(metric["suppressed"] for metric in available_metrics):
                suppressed_cells = True
            reported[value] = summary
        by_stratum[field] = {"reported": reported, "some_metrics_suppressed": suppressed_cells}

    fingerprints = evaluator_fingerprints(Path(__file__))
    return {
        "criteria_version": next(iter(criteria_versions)),
        "pipeline_version": next(iter(pipeline_versions)),
        "evaluator_sha256": fingerprints["evaluator_sha256"],
        "privacy": {
            "policy_version": REPORTING_POLICY_VERSION,
            "policy_status": REPORTING_POLICY_STATUS,
            "policy_sha256": fingerprints["reporting_policy_sha256"],
            "minimum_unique_candidates": MIN_REPORTING_CANDIDATES,
            "suppressed": suppressed,
            "per_metric_suppression": True,
            "complementary_stratum_suppression": True,
            "note": "The five-candidate floor is provisional. M0 privacy governance must approve or replace it before results are shared.",
        },
        "overall": overall,
        "by_stratum": by_stratum,
        "method": {
            "aggregation": "macro average across requisitions; each requisition contributes equally",
            "kendall_tau_b": "Pairwise ordinal agreement; human ties are supported.",
            "top_k": "K=5; requisitions with fewer than five candidates are excluded from top-K metrics. The adjudicated top set includes all ties at its fifth-rank boundary.",
            "suppression": "Each metric value and its requisition/candidate contribution counts are withheld unless at least five distinct candidate pseudonyms contributed. When exactly one stratum cell falls below the floor for a metric, the largest visible cell for that metric is also withheld to reduce subtraction-based inference.",
            "rank_direction": "Rank 1 is the highest priority in the frozen model order or human evidence-based order.",
        },
        "limitations": [
            "Metrics measure agreement with human ranking under the approved evidence rubric; they do not measure candidate quality, hiring success, fairness, or suitability.",
            "Recruiter and hiring-manager ranking agreement is reported separately so adjudication does not hide reviewer disagreement.",
            "Results describe only the supplied, fully ranked requisitions. Selection, small samples, and rubric differences can limit interpretation.",
            "No pass threshold is set. HR, privacy, and product owners must set targets after M0 scope and baseline review.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Completed, adjudicated M2 ranking CSV")
    args = parser.parse_args()
    try:
        print(json.dumps(evaluate(args.csv_path), ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        print(f"Ranking evaluation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
