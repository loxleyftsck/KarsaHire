"""Structured Interview Rubrics & Scorecard Service for KarsaHire.

Manages structured interview scorecards, standardized 1-5 rating rubrics,
and dual-role (Recruiter vs. Hiring Manager) evaluations with complete audit logging.

Rating Scale / Rubrik Penilaian Skor 1-5:
1: Tidak memadai (Unsatisfactory / Poor)
2: Kurang (Below Expectations / Needs Improvement)
3: Memenuhi syarat (Meets Expectations / Competent)
4: Kuat (Strong / Above Expectations)
5: Luar biasa (Outstanding / Exceptional)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

SCORE_MIN = 1
SCORE_MAX = 5

SCORE_RUBRIC: dict[int, str] = {
    1: "Tidak memadai",
    2: "Kurang",
    3: "Memenuhi syarat",
    4: "Kuat",
    5: "Luar biasa",
}

# Alias for compatibility
SCORE_DESCRIPTIONS = SCORE_RUBRIC


def now() -> str:
    """Return the current ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str = "sc") -> str:
    """Generate a unique random identifier with prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def normalize_role(role: str) -> str:
    """Normalize role string to canonical snake_case."""
    return str(role or "").strip().lower().replace(" ", "_")


def validate_score(score: Any, criterion_id: str = "") -> int:
    """Validate that score is an integer between 1 and 5.

    Raises:
        ValueError: If score is not between 1 and 5 or cannot be converted to int.
    """
    try:
        if isinstance(score, float) and score.is_integer():
            val = int(score)
        elif isinstance(score, str) and "." in score:
            f_val = float(score)
            if f_val.is_integer():
                val = int(f_val)
            else:
                raise ValueError()
        else:
            val = int(score)
    except (ValueError, TypeError) as exc:
        label = f" untuk kriteria '{criterion_id}'" if criterion_id else ""
        raise ValueError(f"Skor{label} harus berupa angka bulat 1-5.") from exc

    if not (SCORE_MIN <= val <= SCORE_MAX):
        label = f" untuk kriteria '{criterion_id}'" if criterion_id else ""
        raise ValueError(
            f"Skor{label} harus berada dalam rentang 1-5 "
            f"(1: Tidak memadai, 2: Kurang, 3: Memenuhi syarat, 4: Kuat, 5: Luar biasa). "
            f"Diberikan: {score}"
        )
    return val


def init_interview_tables(db: sqlite3.Connection) -> None:
    """Initialize SQLite tables for structured interview scorecards and criterion ratings."""
    db.executescript("""
    CREATE TABLE IF NOT EXISTS interview_scorecards (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        candidate_id TEXT NOT NULL,
        reviewer TEXT NOT NULL,
        role TEXT NOT NULL,
        overall_recommendation TEXT NOT NULL,
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS interview_criterion_scores (
        id TEXT PRIMARY KEY,
        scorecard_id TEXT NOT NULL REFERENCES interview_scorecards(id) ON DELETE CASCADE,
        criterion_id TEXT NOT NULL,
        criterion_label TEXT NOT NULL,
        score INTEGER NOT NULL CHECK (score >= 1 AND score <= 5),
        evidence_notes TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS audit_events (
        id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        candidate_id TEXT,
        actor TEXT NOT NULL,
        event_type TEXT NOT NULL,
        details_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_interview_scorecards_candidate ON interview_scorecards(candidate_id);
    CREATE INDEX IF NOT EXISTS idx_interview_scorecards_job ON interview_scorecards(job_id);
    CREATE INDEX IF NOT EXISTS idx_criterion_scores_scorecard ON interview_criterion_scores(scorecard_id);
    CREATE INDEX IF NOT EXISTS idx_criterion_scores_criterion ON interview_criterion_scores(criterion_id);
    """)


def record_scorecard(db: sqlite3.Connection, data: dict[str, Any]) -> str:
    """Record a structured interview scorecard and criterion ratings with audit logging.

    Args:
        db: SQLite database connection.
        data: Scorecard dictionary containing:
            - job_id (str): Associated requisition / job ID.
            - candidate_id (str): Candidate ID.
            - reviewer (str): Name of interviewer / reviewer.
            - role (str): Role ('recruiter', 'hiring_manager', etc.).
            - overall_recommendation (str): Recommendation (e.g. 'hire', 'strong_hire', 'no_hire').
            - notes (str, optional): General observations or notes.
            - created_at (str, optional): ISO timestamp.
            - criterion_scores (list[dict], optional): List of criterion scores.
                Each item:
                - criterion_id (str): Identifier of the criterion.
                - criterion_label (str, optional): Rubric criterion title / label.
                - score (int): Score between 1 and 5.
                - evidence_notes (str, optional): Specific observations / notes.

    Returns:
        The generated or provided scorecard ID.

    Raises:
        ValueError: If required fields are missing or score values are invalid.
    """
    if not isinstance(data, (dict, Mapping)):
        raise TypeError("Data scorecard harus berupa dictionary.")

    job_id = str(data.get("job_id", "")).strip()
    if not job_id:
        raise ValueError("job_id wajib diisi.")

    candidate_id = str(data.get("candidate_id", "")).strip()
    if not candidate_id:
        raise ValueError("candidate_id wajib diisi.")

    reviewer = str(data.get("reviewer", "")).strip()
    if not reviewer:
        raise ValueError("Nama reviewer wajib diisi.")

    raw_role = data.get("role")
    if not raw_role or not str(raw_role).strip():
        raise ValueError("Peran reviewer (role) wajib diisi.")
    role = normalize_role(str(raw_role))

    overall_recommendation = str(data.get("overall_recommendation", "")).strip()
    if not overall_recommendation:
        raise ValueError("Rekomendasi keseluruhan (overall_recommendation) wajib diisi.")

    notes = str(data.get("notes", "")).strip()
    created_at = str(data.get("created_at") or now()).strip()
    scorecard_id = str(data.get("id") or new_id("sc")).strip()

    # Extract criterion scores supporting multiple key aliases
    raw_scores = (
        data.get("criterion_scores")
        if data.get("criterion_scores") is not None
        else data.get("criteria_scores")
        if data.get("criteria_scores") is not None
        else data.get("scores")
        if data.get("scores") is not None
        else data.get("criteria")
        if data.get("criteria") is not None
        else []
    )

    if not isinstance(raw_scores, list):
        raise ValueError("Penilaian kriteria harus berupa list.")

    parsed_scores: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_scores):
        if not isinstance(item, (dict, Mapping)):
            raise ValueError(f"Kriteria ke-{idx+1} harus berupa objek dictionary.")
        crit_id = str(item.get("criterion_id", "")).strip()
        if not crit_id:
            raise ValueError(f"Kriteria ke-{idx+1} wajib menyertakan 'criterion_id'.")
        crit_label = str(item.get("criterion_label") or crit_id).strip()
        score_val = validate_score(item.get("score"), crit_id)
        evidence_notes = str(item.get("evidence_notes", "")).strip()
        cs_id = str(item.get("id") or new_id("cs")).strip()

        parsed_scores.append({
            "id": cs_id,
            "criterion_id": crit_id,
            "criterion_label": crit_label,
            "score": score_val,
            "evidence_notes": evidence_notes,
        })

    # Calculate average score for audit details
    avg_score = (
        round(sum(c["score"] for c in parsed_scores) / len(parsed_scores), 2)
        if parsed_scores
        else None
    )

    audit_details = {
        "scorecard_id": scorecard_id,
        "reviewer": reviewer,
        "role": role,
        "overall_recommendation": overall_recommendation,
        "criterion_count": len(parsed_scores),
        "average_score": avg_score,
        "criteria": [
            {
                "criterion_id": c["criterion_id"],
                "criterion_label": c["criterion_label"],
                "score": c["score"],
                "score_label": SCORE_RUBRIC.get(c["score"], ""),
            }
            for c in parsed_scores
        ],
    }

    audit_id = new_id("evt")

    with db:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO interview_scorecards "
            "(id, job_id, candidate_id, reviewer, role, overall_recommendation, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (scorecard_id, job_id, candidate_id, reviewer, role, overall_recommendation, notes, created_at),
        )

        for cs in parsed_scores:
            cur.execute(
                "INSERT INTO interview_criterion_scores "
                "(id, scorecard_id, criterion_id, criterion_label, score, evidence_notes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    cs["id"],
                    scorecard_id,
                    cs["criterion_id"],
                    cs["criterion_label"],
                    cs["score"],
                    cs["evidence_notes"],
                ),
            )

        cur.execute(
            "INSERT INTO audit_events "
            "(id, job_id, candidate_id, actor, event_type, details_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                audit_id,
                job_id,
                candidate_id,
                reviewer,
                "interview_scorecard_recorded",
                json.dumps(audit_details, ensure_ascii=False),
                created_at,
            ),
        )

    return scorecard_id


def get_candidate_scorecards(db: sqlite3.Connection, candidate_id: str) -> list[dict[str, Any]]:
    """Retrieve all structured interview scorecards and criterion ratings for a candidate."""
    cur = db.cursor()
    cur.execute(
        "SELECT id, job_id, candidate_id, reviewer, role, overall_recommendation, notes, created_at "
        "FROM interview_scorecards "
        "WHERE candidate_id = ? "
        "ORDER BY created_at ASC",
        (candidate_id,),
    )
    scorecard_rows = cur.fetchall()

    scorecards: list[dict[str, Any]] = []
    for sc in scorecard_rows:
        sc_id = sc[0]
        cur.execute(
            "SELECT id, scorecard_id, criterion_id, criterion_label, score, evidence_notes "
            "FROM interview_criterion_scores "
            "WHERE scorecard_id = ? "
            "ORDER BY rowid ASC",
            (sc_id,),
        )
        cs_rows = cur.fetchall()
        criterion_scores = []
        for cs in cs_rows:
            score_int = int(cs[4])
            criterion_scores.append({
                "id": cs[0],
                "scorecard_id": cs[1],
                "criterion_id": cs[2],
                "criterion_label": cs[3],
                "score": score_int,
                "score_label": SCORE_RUBRIC.get(score_int, ""),
                "evidence_notes": cs[5] or "",
            })

        avg_score = (
            round(sum(c["score"] for c in criterion_scores) / len(criterion_scores), 2)
            if criterion_scores
            else None
        )

        scorecards.append({
            "id": sc[0],
            "job_id": sc[1],
            "candidate_id": sc[2],
            "reviewer": sc[3],
            "role": sc[4],
            "overall_recommendation": sc[5],
            "notes": sc[6] or "",
            "created_at": sc[7],
            "criterion_scores": criterion_scores,
            "scores": criterion_scores,
            "average_score": avg_score,
        })

    return scorecards


def get_scorecard(db: sqlite3.Connection, scorecard_id: str) -> dict[str, Any] | None:
    """Retrieve a single interview scorecard by ID with all its criterion ratings."""
    cur = db.cursor()
    cur.execute(
        "SELECT id, job_id, candidate_id, reviewer, role, overall_recommendation, notes, created_at "
        "FROM interview_scorecards "
        "WHERE id = ?",
        (scorecard_id,),
    )
    sc = cur.fetchone()
    if not sc:
        return None

    cur.execute(
        "SELECT id, scorecard_id, criterion_id, criterion_label, score, evidence_notes "
        "FROM interview_criterion_scores "
        "WHERE scorecard_id = ? "
        "ORDER BY rowid ASC",
        (scorecard_id,),
    )
    cs_rows = cur.fetchall()
    criterion_scores = []
    for cs in cs_rows:
        score_int = int(cs[4])
        criterion_scores.append({
            "id": cs[0],
            "scorecard_id": cs[1],
            "criterion_id": cs[2],
            "criterion_label": cs[3],
            "score": score_int,
            "score_label": SCORE_RUBRIC.get(score_int, ""),
            "evidence_notes": cs[5] or "",
        })

    avg_score = (
        round(sum(c["score"] for c in criterion_scores) / len(criterion_scores), 2)
        if criterion_scores
        else None
    )

    return {
        "id": sc[0],
        "job_id": sc[1],
        "candidate_id": sc[2],
        "reviewer": sc[3],
        "role": sc[4],
        "overall_recommendation": sc[5],
        "notes": sc[6] or "",
        "created_at": sc[7],
        "criterion_scores": criterion_scores,
        "scores": criterion_scores,
        "average_score": avg_score,
    }


def get_candidate_interview_summary(db: sqlite3.Connection, candidate_id: str) -> dict[str, Any]:
    """Calculate average interview scores per criterion and per reviewer role (Recruiter vs Hiring Manager).

    Returns a structured summary containing:
        - candidate_id (str)
        - total_scorecards (int)
        - overall_average_score (float | None)
        - recruiter_average (float | None)
        - hiring_manager_average (float | None)
        - by_role (dict): breakdown by role ('recruiter', 'hiring_manager', etc.)
        - by_criterion (dict): breakdown per criterion across all reviewers and by role
        - scorecards (list[dict]): all scorecards evaluated for this candidate
    """
    scorecards = get_candidate_scorecards(db, candidate_id)

    summary: dict[str, Any] = {
        "candidate_id": candidate_id,
        "total_scorecards": len(scorecards),
        "overall_average_score": None,
        "overall_average": None,
        "recruiter_average": None,
        "hiring_manager_average": None,
        "by_role": {
            "recruiter": {
                "scorecard_count": 0,
                "reviewers": [],
                "average_score": None,
                "recommendations": [],
                "by_criterion": {},
                "criteria": {},
            },
            "hiring_manager": {
                "scorecard_count": 0,
                "reviewers": [],
                "average_score": None,
                "recommendations": [],
                "by_criterion": {},
                "criteria": {},
            },
        },
        "by_criterion": {},
        "criteria": {},
        "scorecards": scorecards,
    }

    if not scorecards:
        return summary

    all_scores: list[int] = []

    # Map roles to their scorecards
    role_map: dict[str, list[dict[str, Any]]] = {}
    for sc in scorecards:
        role = sc["role"]
        role_map.setdefault(role, []).append(sc)

    # Process each role
    for role, sc_list in role_map.items():
        if role not in summary["by_role"]:
            summary["by_role"][role] = {
                "scorecard_count": 0,
                "reviewers": [],
                "average_score": None,
                "recommendations": [],
                "by_criterion": {},
                "criteria": {},
            }

        reviewers = list(dict.fromkeys(sc["reviewer"] for sc in sc_list))
        recommendations = [sc["overall_recommendation"] for sc in sc_list]

        role_scores: list[int] = []
        role_crit_scores: dict[str, list[int]] = {}
        role_crit_labels: dict[str, str] = {}

        for sc in sc_list:
            for cs in sc["criterion_scores"]:
                val = cs["score"]
                crit_id = cs["criterion_id"]
                label = cs["criterion_label"]
                role_scores.append(val)
                all_scores.append(val)
                role_crit_scores.setdefault(crit_id, []).append(val)
                role_crit_labels[crit_id] = label

        role_crit_summary = {}
        for crit_id, scores_list in role_crit_scores.items():
            avg = round(sum(scores_list) / len(scores_list), 2)
            role_crit_summary[crit_id] = {
                "criterion_id": crit_id,
                "criterion_label": role_crit_labels.get(crit_id, crit_id),
                "average_score": avg,
                "count": len(scores_list),
            }

        role_avg = (
            round(sum(role_scores) / len(role_scores), 2)
            if role_scores
            else None
        )

        summary["by_role"][role]["scorecard_count"] = len(sc_list)
        summary["by_role"][role]["reviewers"] = reviewers
        summary["by_role"][role]["average_score"] = role_avg
        summary["by_role"][role]["recommendations"] = recommendations
        summary["by_role"][role]["by_criterion"] = role_crit_summary
        summary["by_role"][role]["criteria"] = role_crit_summary

    # Process by_criterion across all scorecards
    crit_all_scores: dict[str, list[int]] = {}
    crit_all_labels: dict[str, str] = {}
    crit_role_scores: dict[str, dict[str, list[int]]] = {}

    for sc in scorecards:
        role = sc["role"]
        for cs in sc["criterion_scores"]:
            cid = cs["criterion_id"]
            val = cs["score"]
            lbl = cs["criterion_label"]
            crit_all_scores.setdefault(cid, []).append(val)
            crit_all_labels[cid] = lbl
            crit_role_scores.setdefault(cid, {}).setdefault(role, []).append(val)

    by_criterion_summary = {}
    for cid, scores_list in crit_all_scores.items():
        overall_crit_avg = round(sum(scores_list) / len(scores_list), 2)
        role_breakdown = {}
        role_averages = {}
        for r, r_scores in crit_role_scores.get(cid, {}).items():
            r_avg = round(sum(r_scores) / len(r_scores), 2)
            role_breakdown[r] = {
                "average_score": r_avg,
                "count": len(r_scores),
            }
            role_averages[r] = r_avg

        by_criterion_summary[cid] = {
            "criterion_id": cid,
            "criterion_label": crit_all_labels.get(cid, cid),
            "average_score": overall_crit_avg,
            "count": len(scores_list),
            "by_role": role_breakdown,
            "role_averages": role_averages,
        }

    summary["by_criterion"] = by_criterion_summary
    summary["criteria"] = by_criterion_summary

    if all_scores:
        overall_avg = round(sum(all_scores) / len(all_scores), 2)
        summary["overall_average_score"] = overall_avg
        summary["overall_average"] = overall_avg

    summary["recruiter_average"] = summary["by_role"]["recruiter"]["average_score"]
    summary["hiring_manager_average"] = summary["by_role"]["hiring_manager"]["average_score"]

    return summary
