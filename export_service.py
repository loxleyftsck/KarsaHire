"""Data Export & Audit Service for KarsaHire.

Provides structured data export capabilities for:
1. Candidate summary recap in CSV format (export_candidates_csv)
2. Evidence breakdown in CSV format (export_evidence_csv)
3. Complete hiring debrief report in JSON format (export_job_report_json)

Compliant with KarsaHire's evidence-first recruitment copilot architecture:
- Lexical matching and evidence snippets preserved
- Dual-role sign-off (recruiter & hiring manager) recorded
- Complete immutable audit trail included
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path
from typing import Any


def export_candidates_csv(db: sqlite3.Connection, job_id: str) -> str:
    """Export candidate summary for a job to CSV format.

    Columns:
    candidate_id, file_type, score, status, skills, experience_years, education, reviewer_decision, reviewer_notes, created_at
    """
    cur = db.cursor()
    cur.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cur.fetchone():
        raise ValueError(f"Lowongan dengan ID '{job_id}' tidak ditemukan.")

    cur.execute(
        "SELECT id, file_type, score, status, profile_json, created_at "
        "FROM candidates "
        "WHERE job_id = ? "
        "ORDER BY score DESC, created_at ASC",
        (job_id,),
    )
    candidates = cur.fetchall()

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "candidate_id",
        "file_type",
        "score",
        "status",
        "skills",
        "experience_years",
        "education",
        "reviewer_decision",
        "reviewer_notes",
        "created_at",
    ])

    for row in candidates:
        cand_id, file_type, score, status, profile_json, created_at = row
        try:
            profile = json.loads(profile_json) if profile_json else {}
        except (json.JSONDecodeError, TypeError):
            profile = {}

        skills_raw = profile.get("skills", [])
        if isinstance(skills_raw, list):
            skills_str = ", ".join(str(s) for s in skills_raw)
        else:
            skills_str = str(skills_raw or "")

        exp_years = profile.get("experience_years_mentioned")
        if exp_years is None:
            exp_years = profile.get("experience_years")
        exp_str = str(exp_years) if exp_years is not None else ""

        edu_raw = profile.get("education_levels_mentioned")
        if edu_raw is None:
            edu_raw = profile.get("education", [])
        if isinstance(edu_raw, list):
            edu_str = ", ".join(str(e) for e in edu_raw)
        else:
            edu_str = str(edu_raw or "")

        cur.execute(
            "SELECT reviewer, role, decision, note, created_at "
            "FROM reviews "
            "WHERE candidate_id = ? "
            "ORDER BY created_at DESC",
            (cand_id,),
        )
        reviews = cur.fetchall()
        if reviews:
            reviewer_decision = reviews[0][2]
            notes = [r[3].strip() for r in reviews if r[3] and r[3].strip()]
            reviewer_notes = " | ".join(notes) if notes else ""
        else:
            reviewer_decision = status if status and status != "needs_review" else ""
            reviewer_notes = ""

        writer.writerow([
            cand_id,
            file_type,
            score,
            status,
            skills_str,
            exp_str,
            edu_str,
            reviewer_decision,
            reviewer_notes,
            created_at,
        ])

    return output.getvalue()


def export_evidence_csv(db: sqlite3.Connection, job_id: str) -> str:
    """Export evidence breakdown for a job's candidates to CSV format.

    Columns:
    candidate_id, criterion, requirement_type, weight, result, confidence, snippet, page_number
    """
    cur = db.cursor()
    cur.execute("SELECT id FROM jobs WHERE id = ?", (job_id,))
    if not cur.fetchone():
        raise ValueError(f"Lowongan dengan ID '{job_id}' tidak ditemukan.")

    cur.execute(
        "SELECT e.candidate_id, e.criterion, e.requirement_type, e.weight, e.result, e.confidence, e.snippet, e.page_number "
        "FROM evidence e "
        "JOIN candidates c ON e.candidate_id = c.id "
        "WHERE c.job_id = ? "
        "ORDER BY c.score DESC, c.created_at ASC, e.weight DESC, e.criterion ASC",
        (job_id,),
    )
    evidence_rows = cur.fetchall()

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "candidate_id",
        "criterion",
        "requirement_type",
        "weight",
        "result",
        "confidence",
        "snippet",
        "page_number",
    ])

    for row in evidence_rows:
        cand_id, criterion, req_type, weight, result, confidence, snippet, page_num = row
        page_str = "" if page_num is None else str(page_num)
        writer.writerow([
            cand_id,
            criterion,
            req_type,
            weight,
            result,
            confidence,
            snippet,
            page_str,
        ])

    return output.getvalue()


def export_job_report_json(db: sqlite3.Connection, job_id: str) -> dict[str, Any]:
    """Export complete hiring debrief report for a job to JSON-serializable dict.

    Contains:
    - Job metadata
    - Approved criteria
    - Approvers (recruiter & hiring manager)
    - Full list of candidates (scores, evidence breakdown, and review history)
    - Entire audit trail (audit_events)
    """
    cur = db.cursor()
    cur.execute(
        "SELECT id, title, department, description, criteria_json, status, created_at "
        "FROM jobs WHERE id = ?",
        (job_id,),
    )
    job_row = cur.fetchone()
    if not job_row:
        raise ValueError(f"Lowongan dengan ID '{job_id}' tidak ditemukan.")

    job_meta = {
        "id": job_row[0],
        "title": job_row[1],
        "department": job_row[2],
        "description": job_row[3],
        "status": job_row[5],
        "created_at": job_row[6],
    }

    try:
        criteria = json.loads(job_row[4]) if job_row[4] else []
    except (json.JSONDecodeError, TypeError):
        criteria = []

    cur.execute(
        "SELECT id, job_id, reviewer, role, created_at "
        "FROM approvals WHERE job_id = ? ORDER BY created_at ASC",
        (job_id,),
    )
    approvals = [
        {
            "id": r[0],
            "job_id": r[1],
            "reviewer": r[2],
            "role": r[3],
            "created_at": r[4],
        }
        for r in cur.fetchall()
    ]

    recruiter_app = next((a for a in approvals if a.get("role") == "recruiter"), None)
    hm_app = next((a for a in approvals if a.get("role") == "hiring_manager"), None)

    approvers = {
        "recruiter": recruiter_app["reviewer"] if recruiter_app else None,
        "hiring_manager": hm_app["reviewer"] if hm_app else None,
    }

    # Candidates with evidence & reviews
    cur.execute(
        "SELECT id, file_type, score, status, profile_json, created_at "
        "FROM candidates "
        "WHERE job_id = ? "
        "ORDER BY score DESC, created_at ASC",
        (job_id,),
    )
    candidates = []
    for c_row in cur.fetchall():
        cand_id = c_row[0]
        file_type = c_row[1]
        score = c_row[2]
        status = c_row[3]
        profile_json = c_row[4]
        created_at = c_row[5]

        try:
            profile = json.loads(profile_json) if profile_json else {}
        except (json.JSONDecodeError, TypeError):
            profile = {}

        cur.execute(
            "SELECT id, candidate_id, criterion_id, criterion, requirement_type, weight, result, confidence, snippet, page_number "
            "FROM evidence "
            "WHERE candidate_id = ? "
            "ORDER BY weight DESC, criterion ASC",
            (cand_id,),
        )
        evidence_list = [
            {
                "id": e[0],
                "candidate_id": e[1],
                "criterion_id": e[2],
                "criterion": e[3],
                "requirement_type": e[4],
                "weight": e[5],
                "result": e[6],
                "confidence": e[7],
                "snippet": e[8],
                "page_number": e[9],
            }
            for e in cur.fetchall()
        ]

        cur.execute(
            "SELECT id, candidate_id, reviewer, role, decision, note, created_at "
            "FROM reviews "
            "WHERE candidate_id = ? "
            "ORDER BY created_at DESC",
            (cand_id,),
        )
        reviews_list = [
            {
                "id": r[0],
                "candidate_id": r[1],
                "reviewer": r[2],
                "role": r[3],
                "decision": r[4],
                "note": r[5],
                "created_at": r[6],
            }
            for r in cur.fetchall()
        ]

        candidates.append({
            "id": cand_id,
            "candidate_id": cand_id,
            "job_id": job_id,
            "file_type": file_type,
            "score": score,
            "status": status,
            "profile": profile,
            "evidence": evidence_list,
            "reviews": reviews_list,
            "created_at": created_at,
        })

    # Complete audit trail
    cur.execute(
        "SELECT id, job_id, candidate_id, actor, event_type, details_json, created_at "
        "FROM audit_events "
        "WHERE job_id = ? "
        "ORDER BY created_at ASC",
        (job_id,),
    )
    audit_events = []
    for a_row in cur.fetchall():
        try:
            details = json.loads(a_row[5]) if a_row[5] else {}
        except (json.JSONDecodeError, TypeError):
            details = {}
        audit_events.append({
            "id": a_row[0],
            "job_id": a_row[1],
            "candidate_id": a_row[2],
            "actor": a_row[3],
            "event_type": a_row[4],
            "details": details,
            "details_json": a_row[5],
            "created_at": a_row[6],
        })

    return {
        "job_id": job_meta["id"],
        "id": job_meta["id"],
        "title": job_meta["title"],
        "department": job_meta["department"],
        "description": job_meta["description"],
        "status": job_meta["status"],
        "created_at": job_meta["created_at"],
        "metadata": job_meta,
        "criteria": criteria,
        "approved_criteria": criteria,
        "approvals": approvals,
        "approvers": approvers,
        "approver_details": {
            "recruiter": recruiter_app,
            "hiring_manager": hm_app,
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
        "audit_event_count": len(audit_events),
        "audit_events": audit_events,
    }


def verify_exports(db_path: str | Path = "data/copilot.sqlite3") -> dict[str, Any]:
    """Verification helper testing all export functions against a database."""
    resolved_path = Path(db_path)
    if not resolved_path.is_absolute():
        resolved_path = Path(__file__).resolve().parent / resolved_path

    if not resolved_path.exists():
        raise FileNotFoundError(f"Database tidak ditemukan di {resolved_path}")

    conn = sqlite3.connect(resolved_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM jobs LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise ValueError("Tidak ada job di database.")
        job_id = row[0]

        # 1. Test Candidate CSV
        cand_csv = export_candidates_csv(conn, job_id)
        cand_reader = csv.reader(io.StringIO(cand_csv))
        cand_headers = next(cand_reader)
        expected_cand_headers = [
            "candidate_id",
            "file_type",
            "score",
            "status",
            "skills",
            "experience_years",
            "education",
            "reviewer_decision",
            "reviewer_notes",
            "created_at",
        ]
        assert cand_headers == expected_cand_headers, f"Cand headers mismatch: {cand_headers}"
        cand_rows = list(cand_reader)

        # 2. Test Evidence CSV
        evi_csv = export_evidence_csv(conn, job_id)
        evi_reader = csv.reader(io.StringIO(evi_csv))
        evi_headers = next(evi_reader)
        expected_evi_headers = [
            "candidate_id",
            "criterion",
            "requirement_type",
            "weight",
            "result",
            "confidence",
            "snippet",
            "page_number",
        ]
        assert evi_headers == expected_evi_headers, f"Evidence headers mismatch: {evi_headers}"
        evi_rows = list(evi_reader)

        # 3. Test JSON Report
        report = export_job_report_json(conn, job_id)
        assert isinstance(report, dict), "Report must be a dict"
        assert "metadata" in report, "Report missing metadata"
        assert "criteria" in report, "Report missing criteria"
        assert "approvers" in report, "Report missing approvers"
        assert "candidates" in report, "Report missing candidates"
        assert "audit_events" in report, "Report missing audit_events"
        # Validate JSON serializability
        serialized = json.dumps(report, ensure_ascii=False)
        assert len(serialized) > 0, "Serialized JSON is empty"

        return {
            "job_id": job_id,
            "candidate_csv_rows": len(cand_rows),
            "evidence_csv_rows": len(evi_rows),
            "candidates_count": len(report["candidates"]),
            "audit_events_count": len(report["audit_events"]),
            "approvers": report["approvers"],
            "status": "OK",
        }
    finally:
        conn.close()


if __name__ == "__main__":
    result = verify_exports()
    print("Export verification completed successfully:")
    for k, v in result.items():
        print(f"  {k}: {v}")
