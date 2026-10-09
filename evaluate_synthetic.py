"""Automatic benchmark and evaluation script for synthetic CVs in KarsaHire.

Evaluates candidate profile extraction (skills, experience, education) and
multi-position matching using taxonomy.py and matching.py on 32 synthetic CVs.
Saves comprehensive evaluation results to data/synthetic_evaluation_report.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time
from collections import Counter
from typing import Any

import matching
import taxonomy

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = ROOT_DIR / "data" / "synthetic-cv-32"
DEFAULT_OUTPUT_FILE = ROOT_DIR / "data" / "synthetic_evaluation_report.json"

POSITION_TEMPLATES: dict[str, list[str]] = {
    "Software Developer": [
        "Programming",
        "Software development",
        "Git",
        "REST API",
        "SQL",
        "Automated testing",
    ],
    "Network & Systems Administrator": [
        "Computer networking",
        "Server administration",
        "System monitoring",
        "Linux",
    ],
    "Accountant": [
        "General ledger",
        "Financial statements",
        "Account reconciliation",
        "Month-end close",
    ],
}


def build_criteria_for_position(labels: list[str]) -> list[dict[str, Any]]:
    """Build standard criteria objects with equal weighting for matching."""
    return [
        {
            "id": f"crit_{i + 1}",
            "label": label,
            "weight": 1.0,
            "type": "required",
        }
        for i, label in enumerate(labels)
    ]


def discover_samples(data_dir: Path) -> list[str]:
    """Discover synthetic CV sample IDs from manifest.json or directory scan."""
    manifest_file = data_dir / "manifest.json"
    if manifest_file.is_file():
        try:
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            if isinstance(manifest_data, list):
                sample_ids = [
                    entry["sample_id"]
                    for entry in manifest_data
                    if isinstance(entry, dict) and "sample_id" in entry
                ]
                if sample_ids:
                    return sample_ids
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback to scanning subdirectories with resume_text.txt
    subdirs = sorted(
        [
            d.name
            for d in data_dir.iterdir()
            if d.is_dir() and (d / "resume_text.txt").is_file()
        ]
    )
    return subdirs


def evaluate_synthetic_dataset(
    data_dir: Path = DEFAULT_DATA_DIR,
    output_path: Path = DEFAULT_OUTPUT_FILE,
) -> dict[str, Any]:
    """Run benchmark evaluation over all synthetic CVs and generate metrics report."""
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Direktori dataset sintetis tidak ditemukan: {data_dir}")

    sample_ids = discover_samples(data_dir)
    if not sample_ids:
        raise ValueError(f"Tidak ada sampel resume_text.txt ditemukan di {data_dir}")

    total_samples = len(sample_ids)
    prepared_templates = {
        name: build_criteria_for_position(labels)
        for name, labels in POSITION_TEMPLATES.items()
    }

    extraction_times_ms: list[float] = []
    scoring_times_ms: list[float] = []
    total_candidate_times_ms: list[float] = []

    candidates_with_skills_count = 0
    candidates_with_exp_count = 0
    candidates_with_edu_count = 0

    all_detected_skills: Counter[str] = Counter()
    scores_by_position: dict[str, list[float]] = {name: [] for name in POSITION_TEMPLATES}
    candidate_results: list[dict[str, Any]] = []

    start_benchmark_time = time.perf_counter()

    for sid in sample_ids:
        txt_file = data_dir / sid / "resume_text.txt"
        if not txt_file.is_file():
            continue

        raw_text = txt_file.read_text(encoding="utf-8")
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        pages = [(None, line) for line in lines]

        # 1. Profile Extraction Benchmark
        t0 = time.perf_counter()
        profile = matching.profile_from_text(raw_text)
        t_extract = (time.perf_counter() - t0) * 1000.0
        extraction_times_ms.append(t_extract)

        extracted_skills = profile.get("skills", [])
        exp_years = profile.get("experience_years_mentioned")
        edu_levels = profile.get("education_levels_mentioned", [])

        if extracted_skills:
            candidates_with_skills_count += 1
            for sk in extracted_skills:
                all_detected_skills[sk] += 1

        if exp_years is not None:
            candidates_with_exp_count += 1

        if edu_levels:
            candidates_with_edu_count += 1

        # 2. Position Matching Benchmark
        t1 = time.perf_counter()
        cand_scores: dict[str, float] = {}
        cand_evidence: dict[str, list[dict[str, Any]]] = {}

        for pos_name, criteria in prepared_templates.items():
            score, evidence = matching.score_candidate(criteria, pages)
            cand_scores[pos_name] = score
            cand_evidence[pos_name] = evidence
            scores_by_position[pos_name].append(score)

        t_score = (time.perf_counter() - t1) * 1000.0
        scoring_times_ms.append(t_score)
        total_candidate_times_ms.append(t_extract + t_score)

        candidate_results.append({
            "sample_id": sid,
            "skills_count": len(extracted_skills),
            "skills": extracted_skills,
            "experience_years": exp_years,
            "education_levels": edu_levels,
            "scores": cand_scores,
            "extraction_time_ms": round(t_extract, 3),
            "scoring_time_ms": round(t_score, 3),
            "total_time_ms": round(t_extract + t_score, 3),
        })

    total_benchmark_time_ms = (time.perf_counter() - start_benchmark_time) * 1000.0

    # 3. Aggregations & Distribution Stats
    pct_skills_detected = (
        round((candidates_with_skills_count / total_samples) * 100.0, 2)
        if total_samples else 0.0
    )
    pct_exp_detected = (
        round((candidates_with_exp_count / total_samples) * 100.0, 2)
        if total_samples else 0.0
    )
    pct_edu_detected = (
        round((candidates_with_edu_count / total_samples) * 100.0, 2)
        if total_samples else 0.0
    )

    top_10_skills = [
        {
            "skill": skill,
            "count": count,
            "percentage": round((count / total_samples) * 100.0, 2),
        }
        for skill, count in all_detected_skills.most_common(10)
    ]

    position_stats: dict[str, dict[str, Any]] = {}
    for pos_name, scores in scores_by_position.items():
        if scores:
            min_score = min(scores)
            max_score = max(scores)
            mean_score = round(statistics.mean(scores), 2)
            median_score = round(statistics.median(scores), 2)
            stdev_score = round(statistics.stdev(scores), 2) if len(scores) > 1 else 0.0
        else:
            min_score = max_score = mean_score = median_score = stdev_score = 0.0

        # Score buckets distribution
        b_80_100 = sum(1 for s in scores if s >= 80.0)
        b_60_79 = sum(1 for s in scores if 60.0 <= s < 80.0)
        b_40_59 = sum(1 for s in scores if 40.0 <= s < 60.0)
        b_20_39 = sum(1 for s in scores if 20.0 <= s < 40.0)
        b_0_19 = sum(1 for s in scores if s < 20.0)

        position_stats[pos_name] = {
            "criteria": POSITION_TEMPLATES[pos_name],
            "sample_count": len(scores),
            "min_score": round(min_score, 2),
            "max_score": round(max_score, 2),
            "mean_score": mean_score,
            "median_score": median_score,
            "stdev_score": stdev_score,
            "distribution_buckets": {
                "80-100%": b_80_100,
                "60-79%": b_60_79,
                "40-59%": b_40_59,
                "20-39%": b_20_39,
                "0-19%": b_0_19,
            },
        }

    report = {
        "metadata": {
            "title": "KarsaHire Synthetic CV Benchmark & Evaluation Report",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset_directory": str(data_dir),
            "total_samples": total_samples,
            "python_runtime": sys.version.split()[0],
        },
        "performance_latency_ms": {
            "avg_extraction_time_per_candidate": round(statistics.mean(extraction_times_ms), 3),
            "median_extraction_time_per_candidate": round(statistics.median(extraction_times_ms), 3),
            "avg_scoring_time_per_candidate": round(statistics.mean(scoring_times_ms), 3),
            "median_scoring_time_per_candidate": round(statistics.median(scoring_times_ms), 3),
            "avg_total_time_per_candidate": round(statistics.mean(total_candidate_times_ms), 3),
            "median_total_time_per_candidate": round(statistics.median(total_candidate_times_ms), 3),
            "total_benchmark_time": round(total_benchmark_time_ms, 2),
        },
        "profile_extraction_metrics": {
            "total_candidates": total_samples,
            "candidates_with_skills_count": candidates_with_skills_count,
            "candidates_with_skills_percentage": pct_skills_detected,
            "candidates_with_education_count": candidates_with_edu_count,
            "candidates_with_education_percentage": pct_edu_detected,
            "candidates_with_experience_count": candidates_with_exp_count,
            "candidates_with_experience_percentage": pct_exp_detected,
            "distinct_skills_detected": len(all_detected_skills),
            "total_skill_occurrences": sum(all_detected_skills.values()),
            "top_10_skills": top_10_skills,
        },
        "position_matching_distribution": position_stats,
        "candidate_results": candidate_results,
    }

    # Save to JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return report


def display_terminal_summary(report: dict[str, Any], output_path: Path) -> None:
    """Print an elegant, readable evaluation summary to terminal stdout."""
    meta = report["metadata"]
    perf = report["performance_latency_ms"]
    extr = report["profile_extraction_metrics"]
    positions = report["position_matching_distribution"]

    divider = "=" * 76
    sub_divider = "-" * 76

    print(divider)
    print("        KARSAHIRE - SYNTHETIC CV EVALUATION & BENCHMARK REPORT")
    print(divider)
    print(f" Dataset Path        : {meta['dataset_directory']}")
    print(f" Total Samples       : {meta['total_samples']} CVs")
    print(f" Timestamp           : {meta['timestamp']}")
    print(f" Python Runtime      : {meta['python_runtime']}")
    print(f" Saved Report        : {output_path}")
    print(sub_divider)

    print("\n[1] PERFORMANCE & LATENCY BENCHMARKS (MILLISECONDS)")
    print(f"  - Avg Profile Extraction Time   : {perf['avg_extraction_time_per_candidate']:.2f} ms / CV")
    print(f"  - Avg Template Scoring Time     : {perf['avg_scoring_time_per_candidate']:.2f} ms / CV (across 3 roles)")
    print(f"  - Avg Total Time per Candidate  : {perf['avg_total_time_per_candidate']:.2f} ms / CV")
    print(f"  - Total Benchmark Execution Time: {perf['total_benchmark_time']:.2f} ms")

    print("\n[2] CANDIDATE PROFILE EXTRACTION METRICS")
    print(f"  - Skill Detection Rate          : {extr['candidates_with_skills_count']}/{meta['total_samples']} "
          f"({extr['candidates_with_skills_percentage']:.1f}%)")
    print(f"  - Education Detection Rate      : {extr['candidates_with_education_count']}/{meta['total_samples']} "
          f"({extr['candidates_with_education_percentage']:.1f}%)")
    print(f"  - Experience Years Detected     : {extr['candidates_with_experience_count']}/{meta['total_samples']} "
          f"({extr['candidates_with_experience_percentage']:.1f}%)")
    print(f"  - Total Distinct Skills Found   : {extr['distinct_skills_detected']} skills")
    print(f"  - Total Skill Mentions          : {extr['total_skill_occurrences']} mentions")

    print("\n[3] TOP 10 DETECTED SKILLS")
    print("  Rank  Skill Name            Frequency  CV Coverage")
    print("  " + "-" * 50)
    for idx, item in enumerate(extr["top_10_skills"], 1):
        print(f"  #{idx:<3} {item['skill']:<20} {item['count']:>4}x       {item['percentage']:>6.1f}%")

    print("\n[4] POSITION TEMPLATE MATCHING SCORE DISTRIBUTIONS")
    print(f"  {'Position Template':<33} {'Min':>6} {'Max':>6} {'Median':>8} {'Mean':>8} {'StDev':>7}")
    print("  " + "-" * 72)
    for pos_name, stat in positions.items():
        print(
            f"  {pos_name:<33} "
            f"{stat['min_score']:>5.1f}% "
            f"{stat['max_score']:>5.1f}% "
            f"{stat['median_score']:>7.1f}% "
            f"{stat['mean_score']:>7.1f}% "
            f"{stat['stdev_score']:>6.1f}%"
        )

    print("\n[5] SCORE RANGE DISTRIBUTION BREAKDOWN")
    for pos_name, stat in positions.items():
        b = stat["distribution_buckets"]
        print(f"  {pos_name}:")
        print(f"    [80-100%]: {b['80-100%']} CVs | [60-79%]: {b['60-79%']} CVs | "
              f"[40-59%]: {b['40-59%']} CVs | [20-39%]: {b['20-39%']} CVs | [0-19%]: {b['0-19%']} CVs")

    print("\n" + divider)
    print(" Benchmark completed successfully.")
    print(divider + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate KarsaHire candidate profile extraction & position matching on synthetic CVs."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Path to synthetic CV directory (default: data/synthetic-cv-32)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="Path to output JSON report (default: data/synthetic_evaluation_report.json)",
    )

    args = parser.parse_args()

    try:
        report = evaluate_synthetic_dataset(data_dir=args.data_dir, output_path=args.output)
        display_terminal_summary(report, args.output)
        return 0
    except Exception as exc:
        print(f"Error during benchmark: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
