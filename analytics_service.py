"""Recruitment Analytics and Governance Service for KarsaHire.

Provides analytics calculations and selection transparency metrics for
hiring team debrief meetings:
1. Job Funnel Analysis (get_job_funnel):
   - Total candidates count
   - Candidate status distribution (needs_review, advance, needs_info, not_selected)
   - Evidence score metrics: average, minimum, and maximum scores.
2. Inter-Rater Agreement Metrics (get_inter_rater_agreement):
   - Dual-review candidate count (reviewed by both Recruiter and Hiring Manager)
   - Consensus rate (% where both roles agreed on candidate decision)
   - Divergence list (override candidates where decisions differ) for debrief discussion.
3. Criteria Health & Bottleneck Diagnostics (get_criteria_health):
   - Percentage distribution of matched, partial, and unknown per criterion
   - Bottleneck warning (unknown > 80% - criterion too strict / vocabulary gap)
   - Too-common warning (matched > 90% - lack of discriminative power).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _normalize_role(role_raw: str) -> str:
    """Normalize reviewer role string to canonical identifiers ('recruiter' | 'hiring_manager')."""
    clean = (role_raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    if clean in ("recruiter", "rec"):
        return "recruiter"
    if clean in ("hiring_manager", "hiringmanager", "hm"):
        return "hiring_manager"
    return clean


def get_job_funnel(db: sqlite3.Connection, job_id: str) -> dict[str, Any]:
    """Calculate candidate funnel metrics and score distributions for a requisition.

    Args:
        db: SQLite database connection.
        job_id: Unique identifier of the job requisition.

    Returns:
        dict containing:
        - job_id: Job ID
        - total_candidates: Total count of applicants
        - status_distribution: Count per status (needs_review, advance, needs_info, not_selected)
        - status_percentages: Percentage per status
        - avg_score: Mean candidate evidence score (0.0 to 100.0)
        - min_score: Lowest score among candidates
        - max_score: Highest score among candidates
    """
    cur = db.cursor()
    cur.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cur.fetchone():
        raise ValueError(f"Lowongan dengan ID '{job_id}' tidak ditemukan.")

    cur.execute("SELECT score, status FROM candidates WHERE job_id = ?", (job_id,))
    rows = cur.fetchall()

    total_candidates = len(rows)
    canonical_statuses = ["needs_review", "advance", "needs_info", "not_selected"]
    status_counts: dict[str, int] = {st: 0 for st in canonical_statuses}

    scores: list[float] = []
    for score_val, status_val in rows:
        scores.append(float(score_val))
        st = status_val.strip() if status_val else "needs_review"
        status_counts[st] = status_counts.get(st, 0) + 1

    if total_candidates > 0:
        avg_score = round(sum(scores) / total_candidates, 2)
        min_score = round(min(scores), 2)
        max_score = round(max(scores), 2)
        status_percentages = {
            st: round((cnt / total_candidates) * 100.0, 1)
            for st, cnt in status_counts.items()
        }
    else:
        avg_score = 0.0
        min_score = 0.0
        max_score = 0.0
        status_percentages = {st: 0.0 for st in status_counts}

    return {
        "job_id": job_id,
        "total_candidates": total_candidates,
        "status_distribution": status_counts,
        "status_percentages": status_percentages,
        "avg_score": avg_score,
        "min_score": min_score,
        "max_score": max_score,
        "average_score": avg_score,
        "minimum_score": min_score,
        "maximum_score": max_score,
    }


def get_inter_rater_agreement(db: sqlite3.Connection, job_id: str) -> dict[str, Any]:
    """Calculate inter-rater alignment metrics between Recruiter and Hiring Manager.

    Identifies consensus rate and divergence list for dual-reviewed candidates.

    Args:
        db: SQLite database connection.
        job_id: Unique identifier of the job requisition.

    Returns:
        dict containing:
        - job_id: Job ID
        - total_candidates: Total candidates in requisition
        - dual_reviewed_count / reviewed_by_both_count: Candidates reviewed by both roles
        - consensus_count: Candidates where both reviewers chose the same decision
        - consensus_rate: Agreement percentage (consensus_count / dual_reviewed_count * 100)
        - divergent_count: Count of candidates with decision mismatch
        - divergent_candidates / divergences: Detailed list of diverging evaluations
    """
    cur = db.cursor()
    cur.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cur.fetchone():
        raise ValueError(f"Lowongan dengan ID '{job_id}' tidak ditemukan.")

    cur.execute("SELECT id, score, status FROM candidates WHERE job_id = ?", (job_id,))
    candidates_map = {
        row[0]: {"score": float(row[1]), "status": row[2]}
        for row in cur.fetchall()
    }

    cur.execute(
        "SELECT r.id, r.candidate_id, r.reviewer, r.role, r.decision, r.note, r.created_at "
        "FROM reviews r "
        "JOIN candidates c ON r.candidate_id = c.id "
        "WHERE c.job_id = ? "
        "ORDER BY r.created_at ASC",
        (job_id,),
    )
    review_rows = cur.fetchall()

    candidate_reviews: dict[str, dict[str, dict[str, Any]]] = {
        cid: {} for cid in candidates_map
    }
    for r in review_rows:
        cid = r[1]
        role_key = _normalize_role(r[3])
        if role_key in ("recruiter", "hiring_manager"):
            candidate_reviews[cid][role_key] = {
                "review_id": r[0],
                "reviewer": r[2],
                "role": r[3],
                "decision": r[4],
                "note": r[5] or "",
                "created_at": r[6],
            }

    consensus_count = 0
    divergent_candidates: list[dict[str, Any]] = []
    dual_reviewed_count = 0

    for cid, roles in candidate_reviews.items():
        if "recruiter" in roles and "hiring_manager" in roles:
            dual_reviewed_count += 1
            rec_rev = roles["recruiter"]
            hm_rev = roles["hiring_manager"]
            cand_meta = candidates_map.get(cid, {})

            if rec_rev["decision"] == hm_rev["decision"]:
                consensus_count += 1
            else:
                divergent_candidates.append({
                    "candidate_id": cid,
                    "recruiter_decision": rec_rev["decision"],
                    "hiring_manager_decision": hm_rev["decision"],
                    "recruiter": rec_rev["reviewer"],
                    "hiring_manager": hm_rev["reviewer"],
                    "recruiter_note": rec_rev["note"],
                    "hiring_manager_note": hm_rev["note"],
                    "score": cand_meta.get("score", 0.0),
                    "status": cand_meta.get("status", ""),
                })

    if dual_reviewed_count > 0:
        consensus_rate = round((consensus_count / dual_reviewed_count) * 100.0, 1)
    else:
        consensus_rate = 0.0

    return {
        "job_id": job_id,
        "total_candidates": len(candidates_map),
        "dual_reviewed_count": dual_reviewed_count,
        "reviewed_by_both_count": dual_reviewed_count,
        "consensus_count": consensus_count,
        "consensus_rate": consensus_rate,
        "agreement_rate": consensus_rate,
        "divergent_count": len(divergent_candidates),
        "divergent_candidates": divergent_candidates,
        "divergences": divergent_candidates,
        "overrides": divergent_candidates,
    }


def get_criteria_health(db: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    """Analyze criteria difficulty and identify bottlenecks or uncalibrated criteria.

    Calculates the proportion of matched, partial, and unknown evidence per criterion,
    and flags criteria that are too strict (unknown > 80%) or too common (matched > 90%).

    Args:
        db: SQLite database connection.
        job_id: Unique identifier of the job requisition.

    Returns:
        list of dicts containing:
        - criterion_id: Criterion unique identifier
        - criterion / label: Criterion label
        - requirement_type / type: 'required' or 'preferred'
        - weight: Criterion scoring weight
        - total_evaluated: Number of candidate evaluations
        - matched_count: Matched count
        - partial_count: Partial count
        - unknown_count: Unknown count
        - matched_percentage / matched_pct: % matched
        - partial_percentage / partial_pct: % partial
        - unknown_percentage / unknown_pct: % unknown
        - is_bottleneck: bool (True if unknown > 80%)
        - is_too_common: bool (True if matched > 90%)
        - health_status: 'bottleneck' | 'too_common' | 'healthy'
        - flag: Human readable flag description
        - recommendation: Actionable suggestion for debrief discussion
    """
    cur = db.cursor()
    cur.execute("SELECT id, criteria_json FROM jobs WHERE id = ?", (job_id,))
    job_row = cur.fetchone()
    if not job_row:
        raise ValueError(f"Lowongan dengan ID '{job_id}' tidak ditemukan.")

    try:
        criteria = json.loads(job_row[1]) if job_row[1] else []
    except (json.JSONDecodeError, TypeError):
        criteria = []

    # If criteria_json is empty, attempt discovery from existing evidence records
    if not criteria:
        cur.execute(
            "SELECT DISTINCT e.criterion_id, e.criterion, e.requirement_type, e.weight "
            "FROM evidence e "
            "JOIN candidates c ON e.candidate_id = c.id "
            "WHERE c.job_id = ?",
            (job_id,),
        )
        criteria = [
            {"id": r[0], "label": r[1], "type": r[2], "weight": float(r[3])}
            for r in cur.fetchall()
        ]

    cur.execute("SELECT COUNT(*) FROM candidates WHERE job_id = ?", (job_id,))
    total_candidates = cur.fetchone()[0]

    # Aggregate evidence counts by criterion_id and result
    cur.execute(
        "SELECT e.criterion_id, e.criterion, e.result, COUNT(*) "
        "FROM evidence e "
        "JOIN candidates c ON e.candidate_id = c.id "
        "WHERE c.job_id = ? "
        "GROUP BY e.criterion_id, e.result",
        (job_id,),
    )
    counts_by_id: dict[str, dict[str, int]] = {}
    counts_by_label: dict[str, dict[str, int]] = {}

    for row in cur.fetchall():
        crit_id, crit_lbl, result_val, cnt = row[0], row[1], row[2], row[3]
        if crit_id not in counts_by_id:
            counts_by_id[crit_id] = {"matched": 0, "partial": 0, "unknown": 0}
        if result_val in counts_by_id[crit_id]:
            counts_by_id[crit_id][result_val] += cnt

        if crit_lbl not in counts_by_label:
            counts_by_label[crit_lbl] = {"matched": 0, "partial": 0, "unknown": 0}
        if result_val in counts_by_label[crit_lbl]:
            counts_by_label[crit_lbl][result_val] += cnt

    health_report: list[dict[str, Any]] = []

    for c in criteria:
        cid = c.get("id", "")
        label = c.get("label") or c.get("criterion", "")
        req_type = c.get("type", "required")
        weight = float(c.get("weight", 1.0))

        stats = counts_by_id.get(cid) or counts_by_label.get(label) or {
            "matched": 0, "partial": 0, "unknown": 0
        }
        matched_cnt = stats["matched"]
        partial_cnt = stats["partial"]
        unknown_cnt = stats["unknown"]
        eval_total = matched_cnt + partial_cnt + unknown_cnt

        denom = eval_total if eval_total > 0 else total_candidates

        if denom > 0:
            matched_pct = round((matched_cnt / denom) * 100.0, 1)
            partial_pct = round((partial_cnt / denom) * 100.0, 1)
            unknown_pct = round((unknown_cnt / denom) * 100.0, 1)
            is_bottleneck = unknown_pct > 80.0
            is_too_common = matched_pct > 90.0
        else:
            matched_pct = 0.0
            partial_pct = 0.0
            unknown_pct = 0.0
            is_bottleneck = False
            is_too_common = False

        if is_bottleneck:
            health_status = "bottleneck"
            flag = "terlalu ketat / bottleneck"
            recommendation = (
                "Kriteria bottleneck: >80% kandidat tidak memiliki bukti eksplisit. "
                "Pertimbangkan perluasan alias taksonomi atau relaksasi menjadi preferred."
            )
        elif is_too_common:
            health_status = "too_common"
            flag = "terlalu umum"
            recommendation = (
                "Kriteria terlalu umum: >90% kandidat memenuhinya. "
                "Daya beda kriteria rendah untuk seleksi awal."
            )
        else:
            health_status = "healthy"
            flag = "normal"
            recommendation = "Kriteria dalam distribusi wajar dan sehat."

        health_report.append({
            "criterion_id": cid,
            "criterion": label,
            "label": label,
            "requirement_type": req_type,
            "type": req_type,
            "weight": weight,
            "total_evaluated": denom,
            "matched_count": matched_cnt,
            "partial_count": partial_cnt,
            "unknown_count": unknown_cnt,
            "matched_pct": matched_pct,
            "partial_pct": partial_pct,
            "unknown_pct": unknown_pct,
            "matched_percentage": matched_pct,
            "partial_percentage": partial_pct,
            "unknown_percentage": unknown_pct,
            "is_bottleneck": is_bottleneck,
            "is_too_common": is_too_common,
            "health_status": health_status,
            "flag": flag,
            "recommendation": recommendation,
        })

    return health_report


def get_hiring_analytics_summary(db: sqlite3.Connection, job_id: str) -> dict[str, Any]:
    """Provide a consolidated recruitment debrief analytics summary for a job."""
    return {
        "job_id": job_id,
        "funnel": get_job_funnel(db, job_id),
        "inter_rater_agreement": get_inter_rater_agreement(db, job_id),
        "criteria_health": get_criteria_health(db, job_id),
    }
