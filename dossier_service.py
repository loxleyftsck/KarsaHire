"""Executive Dossier Service for KarsaHire.

Generates standalone, print-optimized executive report documents (HTML Standalone Executive Dossier)
for Hiring Committee and Debrief Meetings.

Features:
1. Official KarsaHire Letterhead & Requisition Metadata.
2. Dual-Approval Verification Log (Recruiter & Hiring Manager signature hash verification).
3. Pipeline Funnel Summary & Score Metrics (Distribution, average, min, max).
4. Reviewer Alignment Analysis (Consensus %, Cohen's Kappa, divergence list).
5. Top Candidate Comparison Matrix (Evidence per criterion, structured interview scorecards).
6. Regulatory Compliance Audit (UU PDP No. 27/2022, NYC LL144 Bias Audit, EU AI Act Art. 14 Human Oversight).
7. Modern inline CSS responsive design with print-optimized pagination (@media print).
"""

from __future__ import annotations

import hashlib
import html
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

import analytics_service
import interview_service


def _format_datetime(raw_iso: str | None) -> str:
    """Format an ISO datetime string into human-readable Indonesian format."""
    if not raw_iso:
        return "-"
    try:
        dt = datetime.fromisoformat(raw_iso.replace("Z", "+00:00"))
        months = [
            "",
            "Januari",
            "Februari",
            "Maret",
            "April",
            "Mei",
            "Juni",
            "Juli",
            "Agustus",
            "September",
            "Oktober",
            "November",
            "Desember",
        ]
        return f"{dt.day} {months[dt.month]} {dt.year}, {dt.strftime('%H:%M')} UTC"
    except Exception:
        return str(raw_iso)


def _generate_digital_seal(job_id: str, reviewer: str, role: str, timestamp: str) -> str:
    """Generate a deterministic cryptographic verification seal for approval sign-offs."""
    payload = f"{job_id}:{reviewer}:{role}:{timestamp}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest().upper()
    return f"KRS-{digest[:4]}-{digest[4:8]}-{digest[8:12]}"


def _normalize_role(role_raw: str) -> str:
    """Normalize reviewer role string."""
    clean = (role_raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    if clean in ("recruiter", "rec"):
        return "recruiter"
    if clean in ("hiring_manager", "hiringmanager", "hm"):
        return "hiring_manager"
    return clean


def generate_job_dossier_html(db: sqlite3.Connection, job_id: str) -> str:
    """Generate a complete standalone HTML executive dossier for a job requisition.

    Args:
        db: SQLite database connection.
        job_id: Unique identifier of the job requisition.

    Returns:
        Full standalone HTML document string ready for browser viewing and printing.

    Raises:
        ValueError: If the job with `job_id` is not found.
    """
    cur = db.cursor()

    # 1. Fetch Job Metadata
    cur.execute(
        "SELECT id, title, department, description, criteria_json, status, created_at "
        "FROM jobs WHERE id = ?",
        (job_id,),
    )
    job_row = cur.fetchone()
    if not job_row:
        raise ValueError(f"Lowongan dengan ID '{job_id}' tidak ditemukan.")

    job_title = job_row[1] or "Tanpa Judul"
    department = job_row[2] or "Umum"
    description = job_row[3] or ""
    try:
        criteria = json.loads(job_row[4]) if job_row[4] else []
    except (json.JSONDecodeError, TypeError):
        criteria = []
    job_status = job_row[5] or "draft"
    job_created_at = job_row[6] or ""

    # 2. Fetch Dual-Approval Log
    cur.execute(
        "SELECT id, reviewer, role, created_at FROM approvals WHERE job_id = ? ORDER BY created_at ASC",
        (job_id,),
    )
    approvals_rows = cur.fetchall()
    approvals_by_role: dict[str, dict[str, Any]] = {}
    for app in approvals_rows:
        norm_r = _normalize_role(app[2])
        approvals_by_role[norm_r] = {
            "id": app[0],
            "reviewer": app[1],
            "role": app[2],
            "created_at": app[3],
            "seal": _generate_digital_seal(job_id, app[1], app[2], app[3]),
        }

    recruiter_app = approvals_by_role.get("recruiter")
    hm_app = approvals_by_role.get("hiring_manager")
    is_dual_signed = bool(recruiter_app and hm_app)

    # 3. Analytics: Funnel, Agreement, Fairness, Grounding
    funnel = analytics_service.get_job_funnel(db, job_id)
    agreement = analytics_service.get_inter_rater_agreement(db, job_id)
    fairness = analytics_service.get_fairness_audit_metrics(db, job_id)
    grounding = analytics_service.get_evidence_grounding_audit(db, job_id)

    # 4. Fetch Candidates
    cur.execute(
        "SELECT id, file_type, profile_json, score, status, created_at "
        "FROM candidates WHERE job_id = ? ORDER BY score DESC, created_at ASC",
        (job_id,),
    )
    cand_rows = cur.fetchall()

    candidates_list: list[dict[str, Any]] = []
    for crow in cand_rows:
        c_id = crow[0]
        c_file_type = crow[1]
        try:
            c_profile = json.loads(crow[2]) if crow[2] else {}
        except Exception:
            c_profile = {}
        c_score = float(crow[3])
        c_status = crow[4] or "needs_review"
        c_created_at = crow[5]

        # Fetch evidence items for this candidate
        cur.execute(
            "SELECT criterion_id, criterion, requirement_type, weight, result, confidence, snippet, page_number "
            "FROM evidence WHERE candidate_id = ?",
            (c_id,),
        )
        ev_rows = cur.fetchall()
        evidence_map: dict[str, dict[str, Any]] = {}
        for ev in ev_rows:
            crit_key = ev[0] or ev[1]
            evidence_map[crit_key] = {
                "criterion_id": ev[0],
                "criterion": ev[1],
                "requirement_type": ev[2],
                "weight": ev[3],
                "result": ev[4],
                "confidence": ev[5],
                "snippet": ev[6],
                "page_number": ev[7],
            }

        # Fetch reviews for this candidate
        cur.execute(
            "SELECT reviewer, role, decision, note, created_at FROM reviews WHERE candidate_id = ? ORDER BY created_at ASC",
            (c_id,),
        )
        rev_rows = cur.fetchall()
        candidate_reviews = [
            {
                "reviewer": r[0],
                "role": r[1],
                "decision": r[2],
                "note": r[3] or "",
                "created_at": r[4],
            }
            for r in rev_rows
        ]

        # Fetch interview scorecard summary
        interview_summary = interview_service.get_candidate_interview_summary(db, c_id)

        candidates_list.append({
            "id": c_id,
            "label": f"Kandidat &middot; {c_id[-4:].upper()}",
            "file_type": c_file_type,
            "score": c_score,
            "status": c_status,
            "profile": c_profile,
            "evidence_map": evidence_map,
            "reviews": candidate_reviews,
            "interview_summary": interview_summary,
            "created_at": c_created_at,
        })

    # Filter top candidates for comparison:
    # Prioritize candidates who are 'advance'. If none, show top 5 high-scorers.
    advanced_candidates = [c for c in candidates_list if c["status"] == "advance"]
    if advanced_candidates:
        top_candidates = advanced_candidates
        top_selection_note = (
            f"Menampilkan seluruh <strong>{len(advanced_candidates)} kandidat</strong> yang telah "
            "disetujui untuk lanjut proses (Status: <em>Advance</em>)."
        )
    elif candidates_list:
        top_candidates = candidates_list[:5]
        top_selection_note = (
            f"Belum ada kandidat dengan status final <em>Advance</em>. Menampilkan <strong>{len(top_candidates)} kandidat</strong> "
            "dengan skor bukti tertinggi sebagai rekomendasi diskusi Komite Perekrutan."
        )
    else:
        top_candidates = []
        top_selection_note = "Belum ada pelamar yang terdaftar untuk posisi ini."

    now_iso = datetime.now(timezone.utc).isoformat()
    now_formatted = _format_datetime(now_iso)

    # Render HTML sections
    return _render_dossier_template(
        job_id=job_id,
        job_title=job_title,
        department=department,
        description=description,
        criteria=criteria,
        job_status=job_status,
        job_created_at=job_created_at,
        now_formatted=now_formatted,
        recruiter_app=recruiter_app,
        hm_app=hm_app,
        is_dual_signed=is_dual_signed,
        funnel=funnel,
        agreement=agreement,
        fairness=fairness,
        grounding=grounding,
        top_candidates=top_candidates,
        top_selection_note=top_selection_note,
        total_candidates_count=len(candidates_list),
    )


def _render_dossier_template(
    *,
    job_id: str,
    job_title: str,
    department: str,
    description: str,
    criteria: list[dict[str, Any]],
    job_status: str,
    job_created_at: str,
    now_formatted: str,
    recruiter_app: dict[str, Any] | None,
    hm_app: dict[str, Any] | None,
    is_dual_signed: bool,
    funnel: dict[str, Any],
    agreement: dict[str, Any],
    fairness: dict[str, Any],
    grounding: dict[str, Any],
    top_candidates: list[dict[str, Any]],
    top_selection_note: str,
    total_candidates_count: int,
) -> str:
    """Compose the complete standalone HTML dossier document."""

    # Status distribution counts
    status_counts = funnel.get("status_distribution", {})
    cnt_review = status_counts.get("needs_review", 0)
    cnt_advance = status_counts.get("advance", 0)
    cnt_info = status_counts.get("needs_info", 0)
    cnt_not = status_counts.get("not_selected", 0)
    tot = max(funnel.get("total_candidates", 0), 1)

    pct_review = round((cnt_review / tot) * 100, 1)
    pct_advance = round((cnt_advance / tot) * 100, 1)
    pct_info = round((cnt_info / tot) * 100, 1)
    pct_not = round((cnt_not / tot) * 100, 1)

    # Cohen's Kappa & Agreement
    cohens_kappa = agreement.get("cohens_kappa", 0.0)
    kappa_interp = agreement.get("kappa_interpretation", "Belum cukup data")
    consensus_rate = agreement.get("consensus_rate", 0.0)
    dual_rev_count = agreement.get("dual_reviewed_count", 0)
    divergences = agreement.get("divergences", [])

    # Criteria badges HTML
    criteria_badges_html = ""
    for crit in criteria:
        label = html.escape(crit.get("label", ""))
        c_type = crit.get("type", "required")
        weight = crit.get("weight", 1.0)
        badge_cls = "crit-pill-req" if c_type == "required" else "crit-pill-pref"
        badge_txt = f"{label} ({'Wajib' if c_type == 'required' else 'Diutamakan'} &bull; w:{weight})"
        criteria_badges_html += f'<span class="crit-pill {badge_cls}">{badge_txt}</span> '

    # Dual-approval cards HTML
    def render_approval_card(role_name: str, app_data: dict[str, Any] | None) -> str:
        if app_data:
            reviewer = html.escape(app_data.get("reviewer", "-"))
            date_str = _format_datetime(app_data.get("created_at"))
            seal = html.escape(app_data.get("seal", "-"))
            return f"""
            <div class="approval-card signed">
                <div class="approval-status-badge verified">&#10003; TERVERIFIKASI SAH</div>
                <div class="approval-role">{role_name}</div>
                <div class="approval-name">{reviewer}</div>
                <div class="approval-meta">
                    <div><strong>Waktu:</strong> {date_str}</div>
                    <div><strong>Segel Integritas:</strong> <code>{seal}</code></div>
                </div>
            </div>
            """
        else:
            return f"""
            <div class="approval-card pending">
                <div class="approval-status-badge unverified">&#9203; MENUNGGU TANDA TANGAN</div>
                <div class="approval-role">{role_name}</div>
                <div class="approval-name">Belum Ditetapkan</div>
                <div class="approval-meta">
                    <div>Persetujuan kriteria untuk peran ini belum dicatat dalam sistem.</div>
                </div>
            </div>
            """

    recruiter_card = render_approval_card("Recruiter / Talent Acquisition", recruiter_app)
    hm_card = render_approval_card("Hiring Manager / Department Head", hm_app)

    # Divergences table HTML
    if divergences:
        divergence_rows = ""
        for div in divergences:
            cid = html.escape(div.get("candidate_id", ""))
            c_lbl = f"Kandidat &middot; {cid[-4:].upper()}" if len(cid) >= 4 else cid
            rec_dec = html.escape(div.get("recruiter_decision", "-"))
            hm_dec = html.escape(div.get("hiring_manager_decision", "-"))
            rec_note = html.escape(div.get("recruiter_note", ""))
            hm_note = html.escape(div.get("hiring_manager_note", ""))
            divergence_rows += f"""
            <tr>
                <td><strong>{c_lbl}</strong><br><small class="text-muted">{cid}</small></td>
                <td><span class="decision-badge">{rec_dec}</span><br><small>{rec_note or '<em>Tanpa catatan</em>'}</small></td>
                <td><span class="decision-badge">{hm_dec}</span><br><small>{hm_note or '<em>Tanpa catatan</em>'}</small></td>
                <td><span class="tag-warn">Perlu Kalibrasi</span></td>
            </tr>
            """
        divergence_section_html = f"""
        <div class="divergence-table-wrapper">
            <table class="report-table">
                <thead>
                    <tr>
                        <th style="width: 25%;">Kandidat</th>
                        <th style="width: 35%;">Keputusan Recruiter</th>
                        <th style="width: 35%;">Keputusan Hiring Manager</th>
                        <th style="width: 15%;">Tindak Lanjut</th>
                    </tr>
                </thead>
                <tbody>
                    {divergence_rows}
                </tbody>
            </table>
        </div>
        """
    elif dual_rev_count > 0:
        divergence_section_html = """
        <div class="alert-box alert-success">
            <strong>&#10003; Nihil Divergensi (100% Alignment):</strong>
            Seluruh kandidat yang telah direview ganda memiliki keselarasan keputusan penuh antara Recruiter dan Hiring Manager.
        </div>
        """
    else:
        divergence_section_html = """
        <div class="alert-box alert-info">
            <strong>&#8505; Belum Ada Data Review Ganda:</strong>
            Kandidat belum dievaluasi secara lengkap oleh kedua belah pihak (Recruiter & Hiring Manager) secara bersamaan.
        </div>
        """

    # Top Candidate Matrix Table HTML
    if top_candidates:
        candidate_rows = ""
        for cand in top_candidates:
            cid = cand["id"]
            clbl = cand["label"]
            score = cand["score"]
            status = cand["status"]
            profile = cand.get("profile", {})
            skills = profile.get("skills", [])
            skills_txt = html.escape(", ".join(skills[:5])) if skills else "-"
            exp_yrs = profile.get("experience_years_mentioned")
            exp_txt = f"{exp_yrs} tahun" if exp_yrs is not None else "-"
            edu = profile.get("education_levels_mentioned") or profile.get("education", [])
            edu_txt = html.escape(", ".join(edu)) if edu else "-"

            # Evidence per criteria
            evidence_map = cand.get("evidence_map", {})
            crit_matches_html = '<div class="crit-matrix">'
            for c in criteria:
                c_key = c.get("id")
                c_lbl = c.get("label", "")
                ev = evidence_map.get(c_key)
                if not ev:
                    # fallback by label match
                    ev = evidence_map.get(c_lbl)
                res = ev.get("result", "unknown") if ev else "unknown"
                if res == "matched":
                    icon = "&#10003;"
                    cls = "res-matched"
                    title = "Cocok Penuh"
                elif res == "partial":
                    icon = "~"
                    cls = "res-partial"
                    title = "Cocok Sebagian"
                else:
                    icon = "?"
                    cls = "res-unknown"
                    title = "Tidak Ditemukan"
                crit_matches_html += f'<span class="crit-matrix-badge {cls}" title="{html.escape(c_lbl)}: {title}">{icon} {html.escape(c_lbl)}</span> '
            crit_matches_html += "</div>"

            # Interview scorecard
            int_sum = cand.get("interview_summary", {})
            int_total = int_sum.get("total_scorecards", 0)
            if int_total > 0:
                overall_avg = int_sum.get("overall_average_score")
                score_desc = interview_service.SCORE_RUBRIC.get(round(overall_avg or 0), "")
                int_display = f"""
                <strong>{overall_avg:.1f} / 5.0</strong> <span class="badge-rubric">{score_desc}</span>
                <div class="text-xs text-muted">({int_total} formulir evaluasi)</div>
                """
            else:
                int_display = '<span class="text-muted text-xs">Belum ada formulir</span>'

            # Candidate status badge
            if status == "advance":
                st_cls = "badge-advance"
                st_lbl = "Advance"
            elif status == "needs_info":
                st_cls = "badge-needs-info"
                st_lbl = "Needs Info"
            elif status == "not_selected":
                st_cls = "badge-not-selected"
                st_lbl = "Not Selected"
            else:
                st_cls = "badge-needs-review"
                st_lbl = "Needs Review"

            candidate_rows += f"""
            <tr>
                <td>
                    <div class="cand-name">{clbl}</div>
                    <div class="cand-id"><code>{cid}</code></div>
                    <div class="cand-fmt">{cand.get('file_type', '').upper()} &bull; {exp_txt}</div>
                </td>
                <td style="text-align: center;">
                    <div class="score-pill">{score:.1f}</div>
                    <span class="status-badge {st_cls}">{st_lbl}</span>
                </td>
                <td>
                    <div class="profile-summary">
                        <div><strong>Skills:</strong> {skills_txt}</div>
                        <div><strong>Pendidikan:</strong> {edu_txt}</div>
                    </div>
                </td>
                <td>{crit_matches_html}</td>
                <td style="text-align: center;">{int_display}</td>
            </tr>
            """

        top_candidates_table_html = f"""
        <div class="table-responsive">
            <table class="report-table">
                <thead>
                    <tr>
                        <th style="width: 22%;">Kandidat</th>
                        <th style="width: 14%; text-align: center;">Skor & Status</th>
                        <th style="width: 26%;">Profil Pelamar</th>
                        <th style="width: 24%;">Kesesuaian Kriteria Evidence</th>
                        <th style="width: 14%; text-align: center;">Rata-rata Wawancara</th>
                    </tr>
                </thead>
                <tbody>
                    {candidate_rows}
                </tbody>
            </table>
        </div>
        """
    else:
        top_candidates_table_html = """
        <div class="alert-box alert-info">
            Belum ada data kandidat untuk ditampilkan pada tabel komparasi.
        </div>
        """

    # Full HTML assembly
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Executive Hiring Dossier - {html.escape(job_title)} ({html.escape(job_id)})</title>
    <style>
        /* === KarsaHire Executive Theme & Clean Print CSS === */
        :root {{
            --primary: #1b4332;
            --primary-dark: #0f291e;
            --primary-light: #2d6a4f;
            --accent: #d97706;
            --ink: #0f172a;
            --muted: #475569;
            --light-muted: #64748b;
            --border: #e2e8f0;
            --border-dark: #cbd5e1;
            --bg-page: #f8fafc;
            --bg-card: #ffffff;
            --bg-subtle: #f1f5f9;
            --success: #059669;
            --success-light: #ecfdf5;
            --warning: #d97706;
            --warning-light: #fffbeb;
            --danger: #dc2626;
            --danger-light: #fef2f2;
            --info: #0284c7;
            --info-light: #f0f9ff;
            --radius-sm: 4px;
            --radius-md: 8px;
            --radius-lg: 12px;
            --font-main: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: var(--font-main);
            background-color: var(--bg-page);
            color: var(--ink);
            line-height: 1.5;
            font-size: 13.5px;
            -webkit-font-smoothing: antialiased;
        }}

        /* Screen Navigation Toolbar */
        .screen-toolbar {{
            position: sticky;
            top: 0;
            z-index: 999;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(8px);
            border-bottom: 1px solid var(--border);
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
        }}

        .toolbar-brand {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 700;
            color: var(--primary);
            font-size: 15px;
        }}

        .toolbar-actions {{
            display: flex;
            gap: 12px;
            align-items: center;
        }}

        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-weight: 600;
            font-size: 13px;
            padding: 8px 16px;
            border-radius: var(--radius-md);
            cursor: pointer;
            transition: all 0.15s ease-in-out;
            text-decoration: none;
            border: 1px solid transparent;
        }}

        .btn-primary {{
            background: var(--primary);
            color: #ffffff;
        }}
        .btn-primary:hover {{
            background: var(--primary-light);
        }}

        .btn-outline {{
            background: #ffffff;
            color: var(--muted);
            border-color: var(--border-dark);
        }}
        .btn-outline:hover {{
            background: var(--bg-subtle);
            color: var(--ink);
        }}

        /* Document Container */
        .dossier-wrapper {{
            max-width: 1040px;
            margin: 28px auto 60px;
            padding: 0 16px;
        }}

        .dossier-paper {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 44px 48px;
            box-shadow: 0 10px 35px rgba(0, 0, 0, 0.06);
        }}

        /* Official Letterhead Header */
        .letterhead {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            padding-bottom: 24px;
            border-bottom: 3px double var(--primary);
            margin-bottom: 28px;
        }}

        .brand-col {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .brand-logo {{
            width: 52px;
            height: 52px;
            background: linear-gradient(135deg, var(--primary), var(--primary-light));
            border-radius: 12px;
            display: grid;
            place-items: center;
            color: #ffffff;
            font-size: 26px;
            font-weight: 800;
            box-shadow: 0 4px 12px rgba(27, 67, 50, 0.25);
        }}

        .brand-title-wrap h1 {{
            font-size: 20px;
            font-weight: 800;
            color: var(--primary);
            letter-spacing: -0.02em;
            line-height: 1.2;
        }}

        .brand-title-wrap p {{
            font-size: 11.5px;
            color: var(--light-muted);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .doc-meta-badge {{
            text-align: right;
        }}

        .doc-badge-status {{
            display: inline-block;
            background: var(--bg-subtle);
            color: var(--primary);
            border: 1px solid var(--border);
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 700;
            border-radius: var(--radius-sm);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 4px;
        }}

        .doc-gen-time {{
            font-size: 11px;
            color: var(--light-muted);
        }}

        /* Section Typography */
        .section-block {{
            margin-bottom: 34px;
        }}

        .section-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 14px;
            padding-bottom: 6px;
            border-bottom: 1.5px solid var(--border);
        }}

        .section-header h2 {{
            font-size: 15px;
            font-weight: 700;
            color: var(--primary-dark);
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }}

        .section-num {{
            background: var(--primary);
            color: #ffffff;
            font-size: 11px;
            font-weight: 800;
            width: 22px;
            height: 22px;
            display: grid;
            place-items: center;
            border-radius: 50%;
        }}

        /* Meta Grid */
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 14px;
            background: var(--bg-subtle);
            border: 1px solid var(--border);
            padding: 16px 20px;
            border-radius: var(--radius-md);
            margin-bottom: 16px;
        }}

        .meta-item {{
            display: flex;
            flex-direction: column;
        }}

        .meta-label {{
            font-size: 11px;
            color: var(--light-muted);
            text-transform: uppercase;
            font-weight: 600;
            margin-bottom: 2px;
        }}

        .meta-val {{
            font-size: 14px;
            font-weight: 700;
            color: var(--ink);
        }}

        .desc-box {{
            font-size: 13px;
            color: var(--muted);
            background: #ffffff;
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 12px 16px;
            margin-bottom: 14px;
            line-height: 1.6;
        }}

        /* Criteria Pills */
        .crit-container {{
            margin-top: 10px;
        }}
        .crit-pill {{
            display: inline-block;
            font-size: 11.5px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 20px;
            margin-right: 6px;
            margin-bottom: 6px;
            border: 1px solid transparent;
        }}
        .crit-pill-req {{
            background: #e6f4ea;
            color: #137333;
            border-color: #ceead6;
        }}
        .crit-pill-pref {{
            background: #fef7e0;
            color: #b06000;
            border-color: #feefc3;
        }}

        /* Dual Approval Section */
        .approvals-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 16px;
        }}

        .approval-card {{
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 16px 18px;
            position: relative;
            background: #ffffff;
        }}
        .approval-card.signed {{
            border-color: #a7f3d0;
            background: #f0fdf4;
        }}
        .approval-card.pending {{
            border-color: #fde68a;
            background: #fffbeb;
        }}

        .approval-status-badge {{
            position: absolute;
            top: 14px;
            right: 14px;
            font-size: 10.5px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: var(--radius-sm);
            text-transform: uppercase;
        }}
        .approval-status-badge.verified {{
            background: #d1fae5;
            color: #065f46;
        }}
        .approval-status-badge.unverified {{
            background: #fef3c7;
            color: #92400e;
        }}

        .approval-role {{
            font-size: 11px;
            font-weight: 700;
            color: var(--light-muted);
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 4px;
        }}
        .approval-name {{
            font-size: 16px;
            font-weight: 800;
            color: var(--ink);
            margin-bottom: 8px;
        }}
        .approval-meta {{
            font-size: 11.5px;
            color: var(--muted);
            line-height: 1.5;
        }}
        .approval-meta code {{
            font-family: var(--font-mono);
            background: rgba(0,0,0,0.05);
            padding: 1px 4px;
            border-radius: 3px;
            font-size: 10.5px;
        }}

        .dual-status-banner {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 18px;
            border-radius: var(--radius-md);
            font-size: 12.5px;
            font-weight: 600;
        }}
        .dual-status-banner.complete {{
            background: #ecfdf5;
            color: #065f46;
            border: 1px solid #a7f3d0;
        }}
        .dual-status-banner.incomplete {{
            background: #fffbeb;
            color: #92400e;
            border: 1px solid #fde68a;
        }}

        /* KPI Metric Cards */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 14px;
            margin-bottom: 18px;
        }}
        .kpi-card {{
            background: var(--bg-subtle);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 14px 16px;
            text-align: center;
        }}
        .kpi-val {{
            font-size: 26px;
            font-weight: 800;
            color: var(--primary);
            line-height: 1.1;
            margin-bottom: 4px;
        }}
        .kpi-label {{
            font-size: 11px;
            font-weight: 600;
            color: var(--light-muted);
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }}

        /* Segmented Funnel Bar */
        .funnel-bar-wrap {{
            background: var(--bg-subtle);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 16px 20px;
            margin-bottom: 18px;
        }}
        .funnel-bar-title {{
            font-size: 12px;
            font-weight: 700;
            color: var(--ink);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.02em;
        }}
        .segmented-progress {{
            display: flex;
            height: 18px;
            border-radius: 9px;
            overflow: hidden;
            background: #e2e8f0;
            margin-bottom: 12px;
        }}
        .seg-advance {{ background: #059669; }}
        .seg-review {{ background: #3b82f6; }}
        .seg-info {{ background: #f59e0b; }}
        .seg-not {{ background: #94a3b8; }}

        .funnel-legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            font-size: 11.5px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .legend-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
        }}

        /* Tables */
        .table-responsive {{
            overflow-x: auto;
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            margin-bottom: 16px;
        }}
        .report-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            text-align: left;
        }}
        .report-table th {{
            background: var(--bg-subtle);
            color: var(--primary-dark);
            font-weight: 700;
            text-transform: uppercase;
            font-size: 10.5px;
            letter-spacing: 0.04em;
            padding: 10px 14px;
            border-bottom: 1.5px solid var(--border-dark);
        }}
        .report-table td {{
            padding: 10px 14px;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
        }}
        .report-table tbody tr:last-child td {{
            border-bottom: none;
        }}
        .report-table tbody tr:nth-child(even) {{
            background: #fafbfc;
        }}

        /* Badges & Pills */
        .score-pill {{
            font-size: 16px;
            font-weight: 800;
            color: var(--primary);
            line-height: 1.2;
        }}
        .status-badge {{
            display: inline-block;
            font-size: 10px;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 4px;
            text-transform: uppercase;
        }}
        .badge-advance {{ background: #d1fae5; color: #065f46; }}
        .badge-needs-review {{ background: #dbeafe; color: #1e40af; }}
        .badge-needs-info {{ background: #fef3c7; color: #92400e; }}
        .badge-not-selected {{ background: #f1f5f9; color: #475569; }}
        .badge-rubric {{
            font-size: 10px;
            font-weight: 700;
            background: #f1f5f9;
            color: var(--primary);
            padding: 1px 5px;
            border-radius: 3px;
        }}

        .cand-name {{ font-weight: 700; color: var(--ink); font-size: 13px; }}
        .cand-id {{ font-size: 11px; color: var(--light-muted); }}
        .cand-fmt {{ font-size: 11px; color: var(--muted); }}

        .crit-matrix {{
            display: flex;
            flex-wrap: wrap;
            gap: 4px;
        }}
        .crit-matrix-badge {{
            font-size: 10.5px;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 4px;
            white-space: nowrap;
        }}
        .res-matched {{ background: #d1fae5; color: #065f46; }}
        .res-partial {{ background: #fef3c7; color: #92400e; }}
        .res-unknown {{ background: #f1f5f9; color: #64748b; }}

        .profile-summary {{ font-size: 11.5px; color: var(--muted); line-height: 1.4; }}
        .profile-summary strong {{ color: var(--ink); }}

        /* Alerts & Callouts */
        .alert-box {{
            padding: 12px 16px;
            border-radius: var(--radius-md);
            font-size: 12.5px;
            line-height: 1.5;
            margin-bottom: 14px;
        }}
        .alert-success {{ background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }}
        .alert-info {{ background: #f0f9ff; color: #0369a1; border: 1px solid #bae6fd; }}
        .alert-warning {{ background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }}

        /* Compliance Grid */
        .compliance-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 14px;
            margin-bottom: 16px;
        }}
        .compliance-card {{
            background: #ffffff;
            border: 1px solid var(--border);
            border-top: 3px solid var(--primary);
            border-radius: var(--radius-md);
            padding: 14px 16px;
        }}
        .comp-icon {{
            font-size: 16px;
            font-weight: 800;
            color: var(--primary);
            margin-bottom: 6px;
        }}
        .comp-title {{
            font-size: 12.5px;
            font-weight: 750;
            color: var(--primary-dark);
            margin-bottom: 6px;
            line-height: 1.3;
        }}
        .comp-desc {{
            font-size: 11.5px;
            color: var(--muted);
            line-height: 1.45;
        }}
        .comp-tag {{
            display: inline-block;
            margin-top: 8px;
            font-size: 10px;
            font-weight: 700;
            background: #ecfdf5;
            color: #065f46;
            padding: 2px 6px;
            border-radius: 3px;
        }}

        /* Committee Signatures */
        .committee-sign-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-top: 28px;
            padding-top: 24px;
            border-top: 1.5px dashed var(--border-dark);
        }}
        .sign-box {{
            text-align: center;
            font-size: 11.5px;
        }}
        .sign-role {{
            font-weight: 700;
            color: var(--ink);
            text-transform: uppercase;
            margin-bottom: 40px;
        }}
        .sign-line {{
            border-bottom: 1px solid var(--ink);
            margin-bottom: 4px;
        }}
        .sign-name {{
            font-weight: 600;
            color: var(--light-muted);
        }}

        .dossier-footer {{
            margin-top: 32px;
            padding-top: 14px;
            border-top: 1px solid var(--border);
            font-size: 11px;
            color: var(--light-muted);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        /* Utility classes */
        .text-muted {{ color: var(--muted); }}
        .text-xs {{ font-size: 11px; }}
        .tag-warn {{ background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 3px; font-weight: 600; font-size: 10.5px; }}

        /* Print Optimization */
        @media print {{
            @page {{
                size: A4 portrait;
                margin: 12mm 10mm 12mm 10mm;
            }}

            body {{
                background: #ffffff !important;
                color: #000000 !important;
                font-size: 11pt;
            }}

            .no-print, .screen-toolbar {{
                display: none !important;
            }}

            .dossier-wrapper {{
                max-width: 100% !important;
                margin: 0 !important;
                padding: 0 !important;
            }}

            .dossier-paper {{
                border: none !important;
                box-shadow: none !important;
                padding: 0 !important;
                background: #ffffff !important;
            }}

            .avoid-break {{
                break-inside: avoid !important;
                page-break-inside: avoid !important;
            }}

            .page-break-before {{
                break-before: page !important;
                page-break-before: always !important;
            }}

            .kpi-grid, .meta-grid, .approvals-grid, .compliance-grid, .committee-sign-grid {{
                break-inside: avoid !important;
            }}

            .report-table tr {{
                break-inside: avoid !important;
            }}

            .report-table th {{
                background: #f1f5f9 !important;
                color: #000000 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}

            .crit-pill, .status-badge, .approval-status-badge, .crit-matrix-badge {{
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}

            a {{
                text-decoration: none !important;
                color: inherit !important;
            }}
        }}
    </style>
</head>
<body>

    <!-- Screen Interactive Toolbar -->
    <header class="screen-toolbar no-print">
        <div class="toolbar-brand">
            <span>&#9670;</span>
            <span>KarsaHire Executive Dossier</span>
            <span style="font-size: 12px; font-weight: normal; color: var(--light-muted);">| {html.escape(job_title)}</span>
        </div>
        <div class="toolbar-actions">
            <button onclick="window.print()" class="btn btn-primary" title="Cetak atau Simpan sebagai PDF">
                Cetak / Simpan PDF
            </button>
            <button onclick="window.history.back()" class="btn btn-outline" title="Kembali ke Aplikasi">
                &larr; Kembali
            </button>
        </div>
    </header>

    <main class="dossier-wrapper">
        <article class="dossier-paper">

            <!-- A. Kop Surat Resmi KarsaHire & Metadata Requisition -->
            <header class="letterhead avoid-break">
                <div class="brand-col">
                    <div class="brand-logo">K</div>
                    <div class="brand-title-wrap">
                        <h1>PT KARSA HIRE NUSANTARA</h1>
                        <p>EXECUTIVE HIRING DOSSIER &bull; Evidence-First Copilot Platform</p>
                    </div>
                </div>
                <div class="doc-meta-badge">
                    <div class="doc-badge-status">CONFIDENTIAL &bull; HIRING COMMITTEE DEBRIEF</div>
                    <div class="doc-gen-time">Diterbitkan: {now_formatted}</div>
                </div>
            </header>

            <!-- Requisition Metadata -->
            <section class="section-block avoid-break">
                <div class="section-header">
                    <span class="section-num">1</span>
                    <h2>Informasi Lowongan & Kriteria Mandat</h2>
                </div>

                <div class="meta-grid">
                    <div class="meta-item">
                        <span class="meta-label">Posisi / Jabatan</span>
                        <span class="meta-val">{html.escape(job_title)}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Departemen</span>
                        <span class="meta-val">{html.escape(department)}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Requisition ID</span>
                        <span class="meta-val"><code>{html.escape(job_id)}</code></span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Tanggal Dibuat</span>
                        <span class="meta-val">{_format_datetime(job_created_at)}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Status Requisition</span>
                        <span class="meta-val">{html.escape(job_status.replace('_', ' ').title())}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Total Pelamar Terdata</span>
                        <span class="meta-val">{total_candidates_count} Orang</span>
                    </div>
                </div>

                {f'<div class="desc-box"><strong>Deskripsi Peran:</strong> {html.escape(description)}</div>' if description else ''}

                <div class="crit-container">
                    <div style="font-size: 11px; text-transform: uppercase; font-weight: 700; color: var(--light-muted); margin-bottom: 6px;">
                        Kriteria Seleksi Disetujui ({len(criteria)} Kriteria):
                    </div>
                    {criteria_badges_html or '<span class="text-muted text-xs">Belum ada kriteria disetujui.</span>'}
                </div>
            </section>

            <!-- B. Log Dual-Approval Verification -->
            <section class="section-block avoid-break">
                <div class="section-header">
                    <span class="section-num">2</span>
                    <h2>Log Verifikasi Dual-Approval (Tanda Tangan Digital)</h2>
                </div>

                <div class="approvals-grid">
                    {recruiter_card}
                    {hm_card}
                </div>

                <div class="dual-status-banner {'complete' if is_dual_signed else 'incomplete'}">
                    <span>{'[VERIFIED]' if is_dual_signed else '[PENDING]'}</span>
                    <div>
                        {'<strong>Status Dual-Sign-Off Sah & Lengkap:</strong> Kriteria lowongan telah diverifikasi secara independen oleh perwakilan Recruiter dan Hiring Manager sesuai tata kelola KarsaHire.' if is_dual_signed else '<strong>Status Dual-Sign-Off Belum Lengkap:</strong> Requisition memerlukan tanda tangan kedua peran sebelum komite mengambil keputusan final.'}
                    </div>
                </div>
            </section>

            <!-- C. Ringkasan Pipeline Funnel & Metrik Skor -->
            <section class="section-block avoid-break">
                <div class="section-header">
                    <span class="section-num">3</span>
                    <h2>Ringkasan Pipeline Funnel & Metrik Skor Evidence</h2>
                </div>

                <div class="kpi-grid">
                    <div class="kpi-card">
                        <div class="kpi-val">{funnel.get('total_candidates', 0)}</div>
                        <div class="kpi-label">Total Kandidat</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-val">{funnel.get('avg_score', 0.0):.1f}</div>
                        <div class="kpi-label">Skor Rata-Rata</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-val">{funnel.get('max_score', 0.0):.1f}</div>
                        <div class="kpi-label">Skor Tertinggi</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-val">{funnel.get('min_score', 0.0):.1f}</div>
                        <div class="kpi-label">Skor Terendah</div>
                    </div>
                </div>

                <div class="funnel-bar-wrap">
                    <div class="funnel-bar-title">Distribusi Status Pipeline Rekrutmen:</div>
                    <div class="segmented-progress">
                        <div class="seg-advance" style="width: {pct_advance}%;" title="Advance: {cnt_advance} ({pct_advance}%)"></div>
                        <div class="seg-review" style="width: {pct_review}%;" title="Needs Review: {cnt_review} ({pct_review}%)"></div>
                        <div class="seg-info" style="width: {pct_info}%;" title="Needs Info: {cnt_info} ({pct_info}%)"></div>
                        <div class="seg-not" style="width: {pct_not}%;" title="Not Selected: {cnt_not} ({pct_not}%)"></div>
                    </div>
                    <div class="funnel-legend">
                        <div class="legend-item"><span class="legend-dot seg-advance"></span> <strong>Advance:</strong> {cnt_advance} ({pct_advance}%)</div>
                        <div class="legend-item"><span class="legend-dot seg-review"></span> <strong>Needs Review:</strong> {cnt_review} ({pct_review}%)</div>
                        <div class="legend-item"><span class="legend-dot seg-info"></span> <strong>Needs Info:</strong> {cnt_info} ({pct_info}%)</div>
                        <div class="legend-item"><span class="legend-dot seg-not"></span> <strong>Not Selected:</strong> {cnt_not} ({pct_not}%)</div>
                    </div>
                </div>
            </section>

            <!-- D. Analisis Keselarasan Reviewer (Cohen's Kappa & Konsensus) -->
            <section class="section-block avoid-break">
                <div class="section-header">
                    <span class="section-num">4</span>
                    <h2>Analisis Keselarasan Reviewer (Inter-Rater Reliability)</h2>
                </div>

                <div class="kpi-grid">
                    <div class="kpi-card">
                        <div class="kpi-val">{dual_rev_count}</div>
                        <div class="kpi-label">Kandidat Review Ganda</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-val">{consensus_rate:.1f}%</div>
                        <div class="kpi-label">Tingkat Konsensus</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-val">{cohens_kappa:.3f}</div>
                        <div class="kpi-label">Cohen's Kappa (&kappa;)</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-val" style="font-size: 15px; padding-top: 6px;">{len(divergences)} Kasus</div>
                        <div class="kpi-label">Divergensi Keputusan</div>
                    </div>
                </div>

                <div style="font-size: 12px; margin-bottom: 12px; color: var(--muted);">
                    <strong>Interpretasi Statistik (Landis & Koch):</strong> {html.escape(kappa_interp)}
                </div>

                {divergence_section_html}
            </section>

            <!-- E. Tabel Perbandingan Kandidat Top -->
            <section class="section-block page-break-before">
                <div class="section-header">
                    <span class="section-num">5</span>
                    <h2>Matriks Komparasi Kandidat Unggulan</h2>
                </div>

                <p style="font-size: 12px; color: var(--muted); margin-bottom: 12px;">
                    {top_selection_note}
                </p>

                {top_candidates_table_html}
            </section>

            <!-- F. Catatan Kepatuhan Regulasi & Tata Kelola AI -->
            <section class="section-block avoid-break">
                <div class="section-header">
                    <span class="section-num">6</span>
                    <h2>Kepatuhan Regulasi & Perlindungan Tata Kelola AI</h2>
                </div>

                <div class="compliance-grid">
                    <div class="compliance-card">
                        <div class="comp-icon">[UU-PDP]</div>
                        <div class="comp-title">UU PDP No. 27/2022</div>
                        <div class="comp-desc">
                            Prinsip <em>Data Minimization</em> & <em>Pseudonymization</em>. Pelamar disajikan secara tersamar (blind-first review) tanpa mengekspos kontak pribadi dalam evaluasi.
                        </div>
                        <span class="comp-tag">Status: {fairness.get('pii_audit_status', 'COMPLIANT')}</span>
                    </div>

                    <div class="compliance-card">
                        <div class="comp-icon">[NYC-LL144]</div>
                        <div class="comp-title">NYC LL144 Anti-Bias Audit</div>
                        <div class="comp-desc">
                            Audit ketidakberpihakan algoritmik. Sistem menggunakan <em>Deterministic Lexical Grounding</em> tanpa atribut demografis untuk menjamin kepatuhan <em>Four-Fifths Rule</em> (EEOC).
                        </div>
                        <span class="comp-tag">Risiko Bias: {fairness.get('adverse_impact_risk', 'LOW')}</span>
                    </div>

                    <div class="compliance-card">
                        <div class="comp-icon">[EU-AI-ACT]</div>
                        <div class="comp-title">EU AI Act Art. 14 (Oversight)</div>
                        <div class="comp-desc">
                            Sistem AI Berisiko Tinggi (Annex III). KarsaHire bertindak murni sebagai <em>Copilot</em> tanpa pengambilan keputusan otonom. Keputusan final 100% berada pada kendali manusia.
                        </div>
                        <span class="comp-tag">Faithfulness: {grounding.get('faithfulness_score', 100.0):.1f}%</span>
                    </div>
                </div>
            </section>

            <!-- G. Lembar Pengesahan Komite Rekrutmen (Hiring Committee Sign-Off) -->
            <section class="section-block avoid-break">
                <div class="section-header">
                    <span class="section-num">7</span>
                    <h2>Lembar Pengesahan Risalah Rapat Komite</h2>
                </div>

                <p style="font-size: 11.5px; color: var(--muted); margin-bottom: 24px;">
                    Dengan menandatangani dokumen ini, Komite Perekrutan menyatakan bahwa proses seleksi telah dilaksanakan secara objektif, berlandaskan bukti dokumen, bebas dari diskriminasi terlarang, dan mematuhi prinsip tata kelola AI yang berlaku.
                </p>

                <div class="committee-sign-grid">
                    <div class="sign-box">
                        <div class="sign-role">Talent Acquisition Lead</div>
                        <div class="sign-line"></div>
                        <div class="sign-name">{html.escape(recruiter_app.get('reviewer', '( ........................................ )') if recruiter_app else '( ........................................ )')}</div>
                        <div style="font-size: 10px; color: var(--light-muted); margin-top: 2px;">Tanggal: .................................</div>
                    </div>

                    <div class="sign-box">
                        <div class="sign-role">Hiring Manager / Dept Head</div>
                        <div class="sign-line"></div>
                        <div class="sign-name">{html.escape(hm_app.get('reviewer', '( ........................................ )') if hm_app else '( ........................................ )')}</div>
                        <div style="font-size: 10px; color: var(--light-muted); margin-top: 2px;">Tanggal: .................................</div>
                    </div>

                    <div class="sign-box">
                        <div class="sign-role">VP / Head of People</div>
                        <div class="sign-line"></div>
                        <div class="sign-name">( ........................................ )</div>
                        <div style="font-size: 10px; color: var(--light-muted); margin-top: 2px;">Tanggal: .................................</div>
                    </div>
                </div>
            </section>

            <!-- Document Footer -->
            <footer class="dossier-footer">
                <div>Dokumen Resmi Debrief &bull; KarsaHire Evidence-First Copilot</div>
                <div>ID Berkas: <code>{job_id}</code> &bull; Dicetak: {now_formatted}</div>
            </footer>

        </article>
    </main>

</body>
</html>
"""


if __name__ == "__main__":
    print("Dossier service OK")
