"""Enterprise-Scale CV Benchmark & Evaluation Script for KarsaHire.

Evaluates high-volume resume datasets (e.g. opensporks/resumes / LiveCareer 2,484 CVs)
using KarsaHire's local lexical matching engine (matching.py, taxonomy.py).

Features:
- Automated dataset loading (with Hugging Face Hub download fallback).
- Multi-domain profiling: skills, experience years, education degrees.
- Multi-position requisition scoring (Software Dev, IT Admin, Accountant, HR).
- Cross-domain discriminatory alignment analysis (Relevance Separation).
- Throughput and latency profiling (CVs/sec, p50, p95 ms latency).
- Local-first & privacy compliant (UU PDP No. 27/2022 sanitization).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import time
from collections import Counter, defaultdict
from typing import Any

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import matching
import taxonomy

DEFAULT_CSV_PATH = ROOT_DIR / "data" / "benchmarks" / "Resume" / "Resume.csv"
DEFAULT_OUTPUT_REPORT = ROOT_DIR / "data" / "enterprise_benchmark_report.json"

POSITION_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "Software Developer": [
        {"id": "sd_1", "label": "Programming", "weight": 1.0, "type": "required"},
        {"id": "sd_2", "label": "Software development", "weight": 1.0, "type": "required"},
        {"id": "sd_3", "label": "Git", "weight": 1.0, "type": "required"},
        {"id": "sd_4", "label": "REST API", "weight": 1.0, "type": "required"},
        {"id": "sd_5", "label": "SQL", "weight": 1.0, "type": "required"},
        {"id": "sd_6", "label": "Automated testing", "weight": 0.8, "type": "preferred"},
    ],
    "IT & Systems Administrator": [
        {"id": "it_1", "label": "Linux", "weight": 1.0, "type": "required"},
        {"id": "it_2", "label": "Computer networking", "weight": 1.0, "type": "required"},
        {"id": "it_3", "label": "Server administration", "weight": 1.0, "type": "required"},
        {"id": "it_4", "label": "System monitoring", "weight": 1.0, "type": "required"},
        {"id": "it_5", "label": "Active directory", "weight": 0.8, "type": "preferred"},
    ],
    "Accountant & Financial Analyst": [
        {"id": "acc_1", "label": "General ledger", "weight": 1.0, "type": "required"},
        {"id": "acc_2", "label": "Financial statements", "weight": 1.0, "type": "required"},
        {"id": "acc_3", "label": "Account reconciliation", "weight": 1.0, "type": "required"},
        {"id": "acc_4", "label": "Month-end close", "weight": 1.0, "type": "required"},
        {"id": "acc_5", "label": "Bookkeeping", "weight": 0.8, "type": "preferred"},
        {"id": "acc_6", "label": "Accounts payable", "weight": 0.8, "type": "preferred"},
    ],
    "HR & Talent Acquisition Specialist": [
        {"id": "hr_1", "label": "Sourcing", "weight": 1.0, "type": "required"},
        {"id": "hr_2", "label": "Screening", "weight": 1.0, "type": "required"},
        {"id": "hr_3", "label": "Structured interviewing", "weight": 1.0, "type": "required"},
        {"id": "hr_4", "label": "Employee relations", "weight": 1.0, "type": "required"},
        {"id": "hr_5", "label": "Training and development", "weight": 0.8, "type": "preferred"},
        {"id": "hr_6", "label": "Payroll", "weight": 0.8, "type": "preferred"},
    ],
}


def ensure_dataset(csv_path: Path) -> Path:
    """Ensure dataset CSV exists, downloading from Hugging Face if needed."""
    if csv_path.is_file():
        return csv_path

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Dataset tidak ditemukan di {csv_path}. Mengunduh dari Hugging Face 'opensporks/resumes'...")
    try:
        from huggingface_hub import hf_hub_download

        downloaded_path = hf_hub_download(
            repo_id="opensporks/resumes",
            filename="Resume/Resume.csv",
            repo_type="dataset",
            local_dir=str(csv_path.parent.parent),
        )
        print(f"Berhasil mengunduh dataset ke: {downloaded_path}")
        return Path(downloaded_path)
    except Exception as exc:
        raise RuntimeError(
            f"Gagal mengunduh dataset secara otomatis: {exc}. "
            f"Silakan tempatkan file Resume.csv di {csv_path}"
        ) from exc


def percentile(data: list[float], pct: float) -> float:
    """Calculate percentile from a sorted or unsorted list of floats."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    d = k - f
    return sorted_data[f] + d * (sorted_data[c] - sorted_data[f])


def run_enterprise_benchmark(
    csv_path: Path = DEFAULT_CSV_PATH,
    limit: int | None = None,
    category_filter: list[str] | None = None,
    output_path: Path = DEFAULT_OUTPUT_REPORT,
) -> dict[str, Any]:
    """Execute enterprise benchmark on high-volume resume corpus."""
    import pandas as pd

    actual_csv = ensure_dataset(csv_path)
    print(f"\n[1/4] Membaca dataset dari: {actual_csv}")
    df = pd.read_csv(actual_csv)

    if category_filter:
        clean_filters = [c.strip().upper() for c in category_filter if c.strip()]
        df = df[df["Category"].str.upper().isin(clean_filters)]
        print(f"      Difilter berdasarkan kategori {clean_filters}: {len(df)} baris")

    if limit is not None and limit > 0:
        df = df.head(limit)
        print(f"      Dibatasi menjadi {len(df)} kandidat (limit={limit})")

    total_candidates = len(df)
    if total_candidates == 0:
        raise ValueError("Tidak ada kandidat untuk dievaluasi dalam dataset.")

    print(f"\n[2/4] Menjalankan Profiling & Scoring pada {total_candidates} CV...")
    start_time = time.perf_counter()

    extraction_latencies_ms: list[float] = []
    scoring_latencies_ms: list[float] = []
    total_candidate_latencies_ms: list[float] = []

    candidates_with_skills = 0
    candidates_with_exp = 0
    candidates_with_edu = 0

    all_detected_skills: Counter[str] = Counter()
    skills_by_category: dict[str, Counter[str]] = defaultdict(Counter)

    category_counts: Counter[str] = Counter()
    category_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    position_scores_all: dict[str, list[float]] = {pos: [] for pos in POSITION_TEMPLATES}

    # Evaluate candidates
    for idx, row in df.iterrows():
        raw_text = str(row.get("Resume_str", ""))
        category = str(row.get("Category", "UNKNOWN")).strip().upper()
        candidate_id = str(row.get("ID", f"cand_{idx}"))

        category_counts[category] += 1

        cand_start = time.perf_counter()

        # Step A: Profile Extraction
        t0 = time.perf_counter()
        profile = matching.profile_from_text(raw_text)
        t_extract = (time.perf_counter() - t0) * 1000.0
        extraction_latencies_ms.append(t_extract)

        extracted_skills = profile.get("skills", [])
        exp_years = profile.get("experience_years_mentioned")
        edu_levels = profile.get("education_levels_mentioned", [])

        if extracted_skills:
            candidates_with_skills += 1
            for sk in extracted_skills:
                all_detected_skills[sk] += 1
                skills_by_category[category][sk] += 1

        if exp_years is not None:
            candidates_with_exp += 1

        if edu_levels:
            candidates_with_edu += 1

        # Step B: Multi-position matching
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        pages = [(None, line) for line in lines]

        t1 = time.perf_counter()
        for pos_name, criteria in POSITION_TEMPLATES.items():
            score, _ = matching.score_candidate(criteria, pages)
            position_scores_all[pos_name].append(score)
            category_scores[category][pos_name].append(score)
        t_scoring = (time.perf_counter() - t1) * 1000.0
        scoring_latencies_ms.append(t_scoring)

        total_candidate_latencies_ms.append((time.perf_counter() - cand_start) * 1000.0)

        if (idx + 1) % 250 == 0 or (idx + 1) == total_candidates:
            pct = ((idx + 1) / total_candidates) * 100
            print(f"      Diproses: {idx + 1}/{total_candidates} ({pct:.1f}%) CV...")

    total_duration = time.perf_counter() - start_time
    throughput_cv_per_sec = total_candidates / total_duration if total_duration > 0 else 0.0

    print("\n[3/4] Menghitung Statistik Analitik & Relevansi Lintas Domain...")

    # Discriminatory alignment analysis
    # Measure average score of candidates from target industry categories on respective positions
    alignment_matrix: dict[str, dict[str, float]] = {}
    for cat in sorted(category_counts.keys()):
        alignment_matrix[cat] = {}
        for pos_name in POSITION_TEMPLATES:
            scores = category_scores[cat][pos_name]
            alignment_matrix[cat][pos_name] = round(statistics.mean(scores), 2) if scores else 0.0

    # Summary statistics for each position
    position_stats: dict[str, dict[str, float]] = {}
    for pos_name, scores in position_scores_all.items():
        if scores:
            position_stats[pos_name] = {
                "min": round(min(scores), 1),
                "max": round(max(scores), 1),
                "mean": round(statistics.mean(scores), 2),
                "median": round(statistics.median(scores), 2),
                "std_dev": round(statistics.stdev(scores), 2) if len(scores) > 1 else 0.0,
                "p90": round(percentile(scores, 90), 1),
            }

    # Latency statistics
    latency_summary = {
        "extraction_ms": {
            "mean": round(statistics.mean(extraction_latencies_ms), 3),
            "median": round(statistics.median(extraction_latencies_ms), 3),
            "p95": round(percentile(extraction_latencies_ms, 95), 3),
            "max": round(max(extraction_latencies_ms), 3),
        },
        "scoring_4_positions_ms": {
            "mean": round(statistics.mean(scoring_latencies_ms), 3),
            "median": round(statistics.median(scoring_latencies_ms), 3),
            "p95": round(percentile(scoring_latencies_ms, 95), 3),
            "max": round(max(scoring_latencies_ms), 3),
        },
        "total_candidate_ms": {
            "mean": round(statistics.mean(total_candidate_latencies_ms), 3),
            "median": round(statistics.median(total_candidate_latencies_ms), 3),
            "p95": round(percentile(total_candidate_latencies_ms, 95), 3),
            "max": round(max(total_candidate_latencies_ms), 3),
        },
    }

    # Coverage summary
    coverage_summary = {
        "total_candidates": total_candidates,
        "skills_detected_count": candidates_with_skills,
        "skills_detected_pct": round((candidates_with_skills / total_candidates) * 100, 2),
        "experience_detected_count": candidates_with_exp,
        "experience_detected_pct": round((candidates_with_exp / total_candidates) * 100, 2),
        "education_detected_count": candidates_with_edu,
        "education_detected_pct": round((candidates_with_edu / total_candidates) * 100, 2),
        "unique_skills_detected": len(all_detected_skills),
    }

    top_skills_overall = [
        {"skill": sk, "count": cnt, "pct": round((cnt / total_candidates) * 100, 2)}
        for sk, cnt in all_detected_skills.most_common(25)
    ]

    report: dict[str, Any] = {
        "metadata": {
            "dataset_source": "opensporks/resumes (LiveCareer Corpus)",
            "dataset_file": str(actual_csv),
            "total_evaluated": total_candidates,
            "total_benchmark_time_seconds": round(total_duration, 3),
            "throughput_cv_per_sec": round(throughput_cv_per_sec, 2),
            "date_executed": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "performance_and_latency": latency_summary,
        "coverage_metrics": coverage_summary,
        "position_score_distributions": position_stats,
        "cross_domain_alignment_matrix": alignment_matrix,
        "top_detected_skills": top_skills_overall,
        "category_distribution": dict(category_counts.most_common()),
    }

    print(f"\n[4/4] Menyimpan laporan benchmark ke: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print Executive Summary to Terminal
    print("\n" + "=" * 78)
    print("      KARSAHIRE ENTERPRISE BENCHMARK REPORT (2.484 CV CORPUS)")
    print("=" * 78)
    print(f"Total CV Dievaluasi   : {total_candidates:,} CV")
    print(f"Total Waktu Eksekusi  : {total_duration:.2f} detik")
    print(f"Throughput Processing : {throughput_cv_per_sec:.1f} CV/detik")
    print(f"Rata-rata Latensi     : {latency_summary['total_candidate_ms']['mean']:.2f} ms / kandidat")
    print(f"p95 Latensi           : {latency_summary['total_candidate_ms']['p95']:.2f} ms")
    print("-" * 78)
    print("COVERAGE PROFILE EXTRACTION:")
    print(f"- Skill Terdeteksi    : {coverage_summary['skills_detected_pct']}% ({candidates_with_skills}/{total_candidates})")
    print(f"- Pengalaman Kerja    : {coverage_summary['experience_detected_pct']}% ({candidates_with_exp}/{total_candidates})")
    print(f"- Gelar Pendidikan    : {coverage_summary['education_detected_pct']}% ({candidates_with_edu}/{total_candidates})")
    print(f"- Variasi Skill Unik  : {coverage_summary['unique_skills_detected']} jenis keahlian")
    print("-" * 78)
    print("VALIDITAS DISKRIMINATORI (Rata-rata Skor per Domain Industri):")
    print(f"{'Domain CV':<24} | {'Software Dev':<14} | {'IT & SysAdmin':<14} | {'Accountant':<12} | {'HR Specialist':<12}")
    print("-" * 78)

    sample_cats = [
        "INFORMATION-TECHNOLOGY",
        "ENGINEERING",
        "ACCOUNTANT",
        "FINANCE",
        "HR",
        "SALES",
        "HEALTHCARE",
    ]
    for cat in sample_cats:
        if cat in alignment_matrix:
            m = alignment_matrix[cat]
            sd = m.get("Software Developer", 0.0)
            it = m.get("IT & Systems Administrator", 0.0)
            acc = m.get("Accountant & Financial Analyst", 0.0)
            hr = m.get("HR & Talent Acquisition Specialist", 0.0)
            print(f"{cat:<24} | {sd:<14.1f} | {it:<14.1f} | {acc:<12.1f} | {hr:<12.1f}")

    print("=" * 78 + "\n")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="KarsaHire Enterprise CV Benchmark Runner")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH, help="Path ke Resume.csv")
    parser.add_argument("--limit", type=int, default=None, help="Batas jumlah CV untuk dievaluasi (default: seluruhnya)")
    parser.add_argument("--categories", type=str, default=None, help="Filter kategori (dipisahkan koma)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_REPORT, help="Path output laporan JSON")

    args = parser.parse_args()
    cat_filter = args.categories.split(",") if args.categories else None
    run_enterprise_benchmark(
        csv_path=args.csv,
        limit=args.limit,
        category_filter=cat_filter,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
