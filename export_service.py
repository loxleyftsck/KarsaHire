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


def export_job_dossier_html(db: sqlite3.Connection, job_id: str) -> str:
    """Generate an executive debrief dossier HTML report for a job requisition."""
    report = export_job_report_json(db, job_id)
    job_meta = report["metadata"]
    criteria = report["criteria"]
    approvers = report["approvers"]
    candidates = report["candidates"]
    audit_events = report["audit_events"]

    # Try fetching interview summary for candidates if interview_service is available
    try:
        from interview_service import get_candidate_interview_summary
    except ImportError:
        get_candidate_interview_summary = None

    def esc(text: Any) -> str:
        s = str(text if text is not None else "")
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    status_labels = {
        "needs_review": "Perlu Review",
        "advance": "Lanjut Proses",
        "needs_info": "Perlu Informasi",
        "not_selected": "Tidak Lanjut",
        "awaiting_approval": "Menunggu Persetujuan",
        "approved": "Disetujui",
        "active": "Aktif",
    }

    # Criteria table rows
    crit_rows = []
    for idx, c in enumerate(criteria, start=1):
        if isinstance(c, dict):
            label = c.get("label", "")
            req_type = c.get("type", "required")
            weight = c.get("weight", 2.0 if req_type == "required" else 1.0)
        elif isinstance(c, (list, tuple)) and len(c) >= 2:
            req_type = c[0]
            label = c[1]
            weight = 2.0 if req_type in ("required", "wajib") else 1.0
        else:
            label = str(c)
            req_type = "required"
            weight = 2.0

        type_badge = "Wajib" if req_type in ("required", "wajib") else "Diutamakan"
        crit_rows.append(f"""
        <tr>
          <td><strong>{idx}</strong></td>
          <td>{esc(label)}</td>
          <td><span class="badge badge-{req_type}">{type_badge}</span></td>
          <td>{weight}</td>
        </tr>
        """)

    # Candidates leaderboard rows
    cand_rows = []
    for idx, cand in enumerate(candidates, start=1):
        cand_id = cand["id"]
        score = round(cand.get("score", 0))
        status = cand.get("status", "needs_review")
        status_text = status_labels.get(status, status)
        file_type = cand.get("file_type", "pdf").upper()
        skills = ", ".join(cand.get("profile", {}).get("skills", [])[:6]) or "-"

        # Interview scorecard score
        interview_score_str = "-"
        if get_candidate_interview_summary:
            try:
                sc_summary = get_candidate_interview_summary(db, cand_id)
                if sc_summary and sc_summary.get("overall_average_score"):
                    interview_score_str = f"{sc_summary['overall_average_score']:.1f} / 5.0"
            except Exception:
                pass

        cand_rows.append(f"""
        <tr>
          <td><strong>#{idx}</strong></td>
          <td><code>{esc(cand_id)}</code></td>
          <td><strong>{score}%</strong></td>
          <td><span class="badge badge-{status}">{esc(status_text)}</span></td>
          <td>{esc(interview_score_str)}</td>
          <td>{esc(file_type)}</td>
          <td class="skills-cell">{esc(skills)}</td>
        </tr>
        """)

    # Candidate detailed dossier sections
    candidate_sections = []
    for idx, cand in enumerate(candidates, start=1):
        cand_id = cand["id"]
        score = round(cand.get("score", 0))
        status = cand.get("status", "needs_review")
        profile = cand.get("profile", {})
        evidence_list = cand.get("evidence", [])
        reviews = cand.get("reviews", [])

        exp_years = profile.get("experience_years_mentioned")
        if exp_years is None:
            exp_years = profile.get("experience_years")
        exp_str = f"{exp_years} tahun" if exp_years is not None else "Belum diketahui"

        edu_list = profile.get("education_levels_mentioned") or profile.get("education") or []
        edu_str = ", ".join(edu_list) if edu_list else "Belum diketahui"
        skills_str = ", ".join(profile.get("skills", [])) or "Belum terdeteksi"

        # Evidence rows
        evi_html = []
        for e in evidence_list:
            res = e.get("result", "unknown")
            res_labels = {
                "matched": ("Ada bukti tekstual", "badge-matched"),
                "partial": ("Bukti parsial", "badge-partial"),
                "needs_verification": ("Perlu verifikasi", "badge-verification"),
                "unknown": ("Belum ditemukan", "badge-unknown"),
            }
            lbl, badge_cls = res_labels.get(res, (res, "badge-unknown"))
            snippet = f"“{esc(e.get('snippet'))}”" if e.get("snippet") else "<em>Belum ditemukan pada dokumen CV.</em>"
            page_info = f"Hal. {e.get('page_number')}" if e.get("page_number") else "Dokumen"

            evi_html.append(f"""
            <div class="evidence-box">
              <div class="evidence-box-header">
                <strong>{esc(e.get('criterion'))}</strong>
                <span class="badge {badge_cls}">{lbl}</span>
              </div>
              <div class="evidence-box-snippet">{snippet}</div>
              <div class="evidence-box-footer">{page_info} &bull; Bobot {e.get('weight', 1.0)}</div>
            </div>
            """)

        # Reviews summary
        rev_html = []
        for r in reviews:
            rev_role = "Recruiter" if r.get("role") == "recruiter" else "Hiring Manager"
            rev_dec = status_labels.get(r.get("decision"), r.get("decision"))
            note_str = f" — {esc(r.get('note'))}" if r.get("note") else ""
            rev_html.append(f"<li><strong>{esc(r.get('reviewer'))}</strong> ({rev_role}): <span class='badge badge-{r.get('decision')}'>{rev_dec}</span>{note_str}</li>")

        reviews_block = f"<ul class='reviews-list'>{''.join(rev_html)}</ul>" if rev_html else "<p class='muted'>Belum ada catatan review manusia.</p>"

        candidate_sections.append(f"""
        <article class="candidate-dossier-card">
          <div class="candidate-card-header">
            <div>
              <h3>Kandidat #{idx} &bull; <code>{esc(cand_id)}</code></h3>
              <p class="muted">Format: {esc(cand.get('file_type', '').upper())} &bull; Pengalaman: {esc(exp_str)} &bull; Pendidikan: {esc(edu_str)}</p>
            </div>
            <div class="candidate-card-score">
              <div class="score-pill">{score}%</div>
              <div class="score-sub">Indikator Evidence</div>
            </div>
          </div>
          <div class="candidate-card-skills">
            <strong>Keahlian Terdeteksi:</strong> {esc(skills_str)}
          </div>
          <div class="evidence-grid">
            {''.join(evi_html)}
          </div>
          <div class="reviews-section">
            <h4>Catatan &amp; Keputusan Tim Review:</h4>
            {reviews_block}
          </div>
        </article>
        """)

    # Audit events rows
    audit_rows = []
    for a in audit_events:
        evt_type = a.get("event_type", "")
        actor = a.get("actor", "-")
        created = a.get("created_at", "-")
        cand_id_str = a.get("candidate_id") or "-"
        audit_rows.append(f"""
        <tr>
          <td><small>{esc(created)}</small></td>
          <td><strong>{esc(actor)}</strong></td>
          <td><code>{esc(evt_type)}</code></td>
          <td><small>{esc(cand_id_str)}</small></td>
        </tr>
        """)

    recruiter_sign = approvers.get("recruiter") or "<em>Belum menandatangani</em>"
    hm_sign = approvers.get("hiring_manager") or "<em>Belum menandatangani</em>"

    html = f"""<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <title>Dossier Debrief Rekrutmen — {esc(job_meta.get('title'))} | KarsaHire</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {{
      --bg: #f8faf9;
      --card-bg: #ffffff;
      --text: #1d2825;
      --muted: #5e6c66;
      --border: #e0e6e3;
      --primary: #2d5a43;
      --primary-light: #eaf3ee;
      --accent: #d97706;
      --success: #15803d;
      --danger: #b91c1c;
      --info: #0369a1;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 32px 24px;
    }}
    .dossier-container {{
      max-width: 1040px;
      margin: 0 auto;
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 40px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.04);
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 2px solid var(--border);
      padding-bottom: 24px;
      margin-bottom: 32px;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .brand-mark {{
      width: 36px;
      height: 36px;
      background: var(--primary);
      color: #fff;
      font-weight: bold;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 8px;
      font-size: 20px;
    }}
    .brand-title {{
      font-size: 20px;
      font-weight: 700;
      color: var(--primary);
    }}
    .print-button {{
      background: var(--primary);
      color: #fff;
      border: none;
      padding: 10px 20px;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }}
    .print-button:hover {{ background: #224433; }}
    .header-section {{
      margin-bottom: 32px;
    }}
    .eyebrow {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
      font-weight: 700;
      margin-bottom: 6px;
    }}
    h1 {{
      font-size: 28px;
      color: var(--text);
      margin-bottom: 8px;
    }}
    .job-meta-line {{
      display: flex;
      gap: 20px;
      color: var(--muted);
      font-size: 14px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }}
    .job-desc {{
      background: var(--primary-light);
      padding: 16px;
      border-radius: 8px;
      font-size: 14px;
      color: #244133;
      border-left: 4px solid var(--primary);
      margin-bottom: 24px;
    }}
    .signoff-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      margin-bottom: 32px;
    }}
    .signoff-card {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      background: #fafcfb;
    }}
    .signoff-card strong {{ display: block; font-size: 15px; color: var(--primary); margin-bottom: 4px; }}
    .signoff-card p {{ font-size: 13px; color: var(--muted); }}
    h2 {{
      font-size: 18px;
      margin: 32px 0 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
      color: var(--primary);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      margin-bottom: 24px;
    }}
    th, td {{
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }}
    th {{
      background: #f1f5f3;
      font-weight: 600;
      color: var(--text);
    }}
    .badge {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 600;
    }}
    .badge-required {{ background: #e0f2fe; color: #0369a1; }}
    .badge-preferred {{ background: #fef3c7; color: #92400e; }}
    .badge-advance {{ background: #dcfce7; color: #15803d; }}
    .badge-needs_review {{ background: #fef9c3; color: #854d0e; }}
    .badge-needs_info {{ background: #e0e7ff; color: #4338ca; }}
    .badge-not_selected {{ background: #fee2e2; color: #b91c1c; }}
    .badge-matched {{ background: #dcfce7; color: #166534; }}
    .badge-partial {{ background: #fef3c7; color: #92400e; }}
    .badge-verification {{ background: #fee2e2; color: #991b1b; }}
    .badge-unknown {{ background: #f3f4f6; color: #4b5563; }}
    .candidate-dossier-card {{
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 24px;
      background: #ffffff;
      page-break-inside: avoid;
    }}
    .candidate-card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
    }}
    .candidate-card-header h3 {{
      font-size: 16px;
      color: var(--text);
    }}
    .score-pill {{
      font-size: 20px;
      font-weight: 700;
      color: var(--primary);
      text-align: right;
    }}
    .score-sub {{
      font-size: 11px;
      color: var(--muted);
      text-align: right;
    }}
    .candidate-card-skills {{
      font-size: 13px;
      margin-bottom: 16px;
      color: #374151;
      padding: 8px 12px;
      background: #f9fafb;
      border-radius: 6px;
    }}
    .evidence-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .evidence-box {{
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 10px;
      background: #fafafa;
      font-size: 13px;
    }}
    .evidence-box-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }}
    .evidence-box-snippet {{
      color: #4b5563;
      font-style: italic;
      margin-bottom: 6px;
      font-size: 12px;
      max-height: 80px;
      overflow: hidden;
    }}
    .evidence-box-footer {{
      font-size: 11px;
      color: #9ca3af;
    }}
    .reviews-section {{
      background: #f8faf9;
      border-radius: 6px;
      padding: 12px;
      font-size: 13px;
    }}
    .reviews-section h4 {{
      font-size: 13px;
      color: var(--primary);
      margin-bottom: 6px;
    }}
    .reviews-list {{
      list-style-type: none;
    }}
    .reviews-list li {{
      margin-bottom: 4px;
    }}
    .footer-note {{
      text-align: center;
      font-size: 12px;
      color: var(--muted);
      margin-top: 40px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
    }}
    @media print {{
      body {{ background: #fff; padding: 0; }}
      .dossier-container {{ border: none; box-shadow: none; padding: 0; max-width: 100%; }}
      .print-button {{ display: none; }}
      .candidate-dossier-card {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="dossier-container">
    <div class="topbar">
      <div class="brand">
        <div class="brand-mark">K</div>
        <div class="brand-title">KarsaHire Dossier</div>
      </div>
      <button class="print-button" onclick="window.print()">🖨️ Cetak / Simpan PDF</button>
    </div>

    <div class="header-section">
      <div class="eyebrow">DOKUMEN DEBRIEF REKRUTMEN BERSAMA</div>
      <h1>{esc(job_meta.get('title'))}</h1>
      <div class="job-meta-line">
        <span><strong>Departemen:</strong> {esc(job_meta.get('department') or '-')}</span>
        <span><strong>Status:</strong> <span class="badge badge-{job_meta.get('status')}">{esc(status_labels.get(job_meta.get('status'), job_meta.get('status')))}</span></span>
        <span><strong>Total Pelamar:</strong> {len(candidates)}</span>
        <span><strong>Tanggal Ekspor:</strong> {esc(report.get('created_at', ''))[:10]}</span>
      </div>
      <div class="job-desc">
        <strong>Ringkasan Peran:</strong><br>
        {esc(job_meta.get('description') or 'Tidak ada deskripsi pekerjaan.')}
      </div>
    </div>

    <div class="signoff-grid">
      <div class="signoff-card">
        <strong>Persetujuan Recruiter:</strong>
        <p>{recruiter_sign}</p>
      </div>
      <div class="signoff-card">
        <strong>Persetujuan Hiring Manager:</strong>
        <p>{hm_sign}</p>
      </div>
    </div>

    <h2>1. Matriks Kriteria Penilaian Berbasis Bukti</h2>
    <table>
      <thead>
        <tr>
          <th>No</th>
          <th>Kriteria Kompetensi</th>
          <th>Tipe Persyaratan</th>
          <th>Bobot</th>
        </tr>
      </thead>
      <tbody>
        {''.join(crit_rows)}
      </tbody>
    </table>

    <h2>2. Rekapitulasi &amp; Peringkat Kandidat</h2>
    <table>
      <thead>
        <tr>
          <th>Peringkat</th>
          <th>ID Kandidat</th>
          <th>Evidence Match</th>
          <th>Status Rekrutmen</th>
          <th>Scorecard Rata-rata</th>
          <th>Format</th>
          <th>Keahlian Terdeteksi</th>
        </tr>
      </thead>
      <tbody>
        {''.join(cand_rows) if cand_rows else '<tr><td colspan="7" style="text-align:center;">Belum ada kandidat pada posisi ini.</td></tr>'}
      </tbody>
    </table>

    <h2>3. Berkas Bukti &amp; Evaluasi Mendalam per Kandidat</h2>
    {''.join(candidate_sections) if candidate_sections else '<p class="muted">Belum ada kandidat terdaftar.</p>'}

    <h2>4. Jejak Audit Kepatuhan (Audit Trail)</h2>
    <table>
      <thead>
        <tr>
          <th>Waktu (UTC)</th>
          <th>Aktor</th>
          <th>Jenis Aktivitas</th>
          <th>Kandidat</th>
        </tr>
      </thead>
      <tbody>
        {''.join(audit_rows) if audit_rows else '<tr><td colspan="4" style="text-align:center;">Belum ada riwayat aktivitas.</td></tr>'}
      </tbody>
    </table>

    <div class="footer-note">
      KarsaHire &bull; Rekrutmen Berbasis Bukti &amp; Evaluasi Manusia Terstandarisasi &bull; Berkas Rahasia Tim Rekrutmen
    </div>
  </div>
</body>
</html>"""
    return html


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
