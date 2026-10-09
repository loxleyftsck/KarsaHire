"""Candidate Feedback & Transparency Service for KarsaHire.

Generates constructive candidate feedback summaries (Constructive Candidate Feedback)
grounded in verifiable evidence and compliant with Indonesia's Personal Data Protection
Law (UU No. 27/2022 tentang Pelindungan Data Pribadi - UU PDP).

Key Architecture Principles:
1. Explainable & Evidence-First: Distinguishes verified competencies from unverified ('unknown')
   criteria without algorithmic prejudice.
2. Human-in-the-Loop (HITL): Guarantees compliance with Pasal 40 UU PDP by ensuring decisions
   are made by human reviewers (Recruiter & Hiring Manager), strictly prohibiting black-box
   auto-rejections.
3. Constructive & Actionable: Provides transparent feedback with concrete resume/portfolio
   recommendations for candidate career growth and employer branding excellence.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


TRANSPARENCY_NOTICE_PDP = (
    "Pemberitahuan Transparansi & Kepatuhan UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi (UU PDP):\n"
    "1. Sesuai Pasal 40 UU PDP No. 27/2022, Anda berhak untuk tidak tunduk pada keputusan yang semata-mata "
    "didasarkan pada pemrosesan data otomatis (automated decision-making / profiling).\n"
    "2. KarsaHire menerapkan arsitektur Human-in-the-Loop (HITL): seluruh penilaian, verifikasi bukti, dan keputusan "
    "akhir dilakukan secara sadar oleh peninjau manusia (Recruiter dan Hiring Manager), BUKAN penolakan otomatis "
    "algoritma black-box AI.\n"
    "3. Sistem AI hanya bertindak sebagai copilot pembaca bukti (evidence extraction copilot) yang memetakan kualifikasi "
    "secara transparan berdasarkan dokumen yang Anda lampirkan.\n"
    "4. Status kriteria 'unknown' mengindikasikan bukti pendukung belum ditemukan secara eksplisit dalam dokumen, "
    "dan bukan merupakan penilaian negatif atas kompetensi atau potensi Anda.\n"
    "5. Pemrosesan berkas dilakukan secara lokal (local-first) dengan prinsip minimisasi data pribadi (redaksi PII) "
    "tanpa transmisi data ke pihak ketiga di luar batas yurisdiksi."
)


def _row_to_dict(cur: sqlite3.Cursor, row: Any) -> dict[str, Any]:
    """Convert a SQLite row to a dictionary regardless of row_factory setting."""
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return dict(row)
    if isinstance(row, dict):
        return row
    col_names = [d[0] for d in cur.description] if cur.description else []
    return dict(zip(col_names, row))


def _format_strength_explanation(
    criterion: str,
    result: str,
    requirement_type: str,
    snippet: str,
    job_title: str,
) -> str:
    """Generate a constructive evidence explanation for matched or partial criteria."""
    req_label = "wajib (required)" if requirement_type == "required" else "nilai tambah (preferred)"
    if result == "matched":
        if snippet:
            return (
                f"Kompetensi '{criterion}' terverifikasi dengan bukti kuat pada berkas: "
                f"\"{snippet}\". Memenuhi kualifikasi {req_label}."
            )
        return (
            f"Kompetensi '{criterion}' terverifikasi memenuhi standar kualifikasi {req_label} "
            f"untuk posisi {job_title}."
        )
    # partial
    if snippet:
        return (
            f"Kompetensi '{criterion}' teridentifikasi sebagian pada berkas: \"{snippet}\". "
            f"Bukti awal ditemukan, disarankan untuk melengkapi detail kedalaman teknis atau konteks proyek."
        )
    return (
        f"Kompetensi '{criterion}' teridentifikasi sebagian dalam berkas lamaran sebagai kualifikasi {req_label}."
    )


def _format_growth_recommendation(
    criterion: str,
    requirement_type: str,
    job_title: str,
) -> tuple[str, str]:
    """Generate explanation and actionable career recommendation for unverified criteria."""
    req_label = "kualifikasi utama (required)" if requirement_type == "required" else "kualifikasi pendukung (preferred)"
    explanation = (
        f"Kualifikasi '{criterion}' ({req_label}) belum ditemukan atau belum terverifikasi secara "
        f"eksplisit dalam dokumen/CV yang diserahkan untuk posisi {job_title}."
    )
    recommendation = (
        f"Untuk meningkatkan keterbacaan profil pada seleksi mendatang atau tahap verifikasi lanjutan, "
        f"disarankan untuk mencantumkan portofolio proyek konkret, sertifikasi terkait, atau deskripsi "
        f"pencapaian terukur yang mendemonstrasikan pengalaman dengan '{criterion}'."
    )
    return explanation, recommendation


def _format_decision_summary(
    status: str,
    job_title: str,
    reviews: list[dict[str, Any]],
) -> str:
    """Synthesize human decision status, reviewer consensus, and debrief notes."""
    normalized_status = (status or "needs_review").strip().lower()

    reviewers: list[str] = []
    notes: list[str] = []
    for r in reviews:
        name = r.get("reviewer") or ""
        role = r.get("role") or ""
        if name:
            role_desc = "Recruiter" if role == "recruiter" else ("Hiring Manager" if role == "hiring_manager" else role)
            reviewers.append(f"{name} ({role_desc})" if role_desc else name)
        note = (r.get("note") or "").strip()
        if note:
            notes.append(note)

    reviewers_str = ", ".join(reviewers) if reviewers else "tim peninjau rekrutmen"

    if normalized_status == "advance":
        summary = (
            f"Status Keputusan: Lanjut ke Tahap Berikutnya (Advance). "
            f"Berdasarkan peninjauan verifikasi bukti oleh peninjau manusia ({reviewers_str}), "
            f"kandidat dinilai memenuhi kualifikasi utama yang dipersyaratkan untuk posisi {job_title} "
            f"dan direkomendasikan untuk tahapan wawancara / asesmen lanjutan."
        )
    elif normalized_status == "needs_info":
        summary = (
            f"Status Keputusan: Memerlukan Informasi Tambahan (Needs Info). "
            f"Peninjau manusia ({reviewers_str}) menemukan potensi yang relevan pada profil kandidat, "
            f"namun memerlukan klarifikasi berkas atau portofolio tambahan untuk kriteria yang belum "
            f"terverifikasi sebelum keputusan akhir ditetapkan."
        )
    elif normalized_status == "not_selected":
        summary = (
            f"Status Keputusan: Belum Terpilih untuk Posisi Ini (Not Selected). "
            f"Setelah evaluasi menyeluruh berbasis bukti oleh peninjau manusia ({reviewers_str}), "
            f"kualifikasi kandidat pada periode seleksi saat ini belum selaras secara optimal dengan "
            f"prioritas kebutuhan posisi {job_title}."
        )
    else:  # needs_review / pending
        summary = (
            f"Status Keputusan: Dalam Antrean Peninjauan Manusia (Needs Review). "
            f"Berkas kandidat telah diekstraksi dan saat ini sedang menunggu evaluasi serta validasi bukti "
            f"langsung oleh Recruiter dan Hiring Manager."
        )

    if notes:
        summary += f" Catatan Evaluasi Peninjau: \"{notes[0]}\"."

    return summary


def _build_feedback_email_draft(
    candidate_id: str,
    job_title: str,
    candidate_label: str,
    decision_summary: str,
    status: str,
    strengths: list[dict[str, Any]],
    growth_areas: list[dict[str, Any]],
    transparency_notice: str,
) -> str:
    """Compose a professional, polite, and actionable feedback email draft."""
    normalized_status = (status or "needs_review").strip().lower()

    # Strengths bullet points
    if strengths:
        strengths_lines = []
        for s in strengths[:5]:  # highlight top relevant
            crit = s.get("criterion", "")
            res = "Terverifikasi Penuh" if s.get("result") == "matched" else "Terverifikasi Sebagian"
            snippet = s.get("snippet", "")
            evidence_note = f" (Bukti: \"{snippet}\")" if snippet else ""
            strengths_lines.append(f"  • {crit} [{res}]{evidence_note}")
        strengths_text = "\n".join(strengths_lines)
    else:
        strengths_text = "  • Bukti kompetensi awal sedang dalam penelaahan lebih lanjut oleh tim rekrutmen."

    # Growth areas bullet points
    if growth_areas:
        growth_lines = []
        for g in growth_areas[:4]:  # focus on top actionable
            crit = g.get("criterion", "")
            rec = g.get("recommendation", "")
            growth_lines.append(f"  • {crit}: {rec}")
        growth_text = "\n".join(growth_lines)
    else:
        growth_text = (
            "  • Seluruh kriteria kualifikasi yang dipersyaratkan berhasil terverifikasi pada dokumen CV Anda."
        )

    # Next steps instruction based on decision status
    if normalized_status == "advance":
        next_steps = (
            "Tim Talent Acquisition kami akan segera menghubungi Anda untuk koordinasi jadwal "
            "tahap wawancara teknis / interview pengguna. Silakan persiapkan diri Anda dan pantau "
            "kotak masuk email Anda."
        )
    elif normalized_status == "needs_info":
        next_steps = (
            "Kami mengundang Anda untuk memberikan tanggapan atau melampirkan informasi tambahan/portofolio "
            "terkait kriteria di atas dengan membalas email ini dalam waktu 3 (tiga) hari kerja agar tim peninjau "
            "kami dapat memfinalisasi evaluasi berkas Anda."
        )
    elif normalized_status == "not_selected":
        next_steps = (
            "Meskipun saat ini kami belum dapat melanjutkan proses ke tahap berikutnya untuk posisi ini, kami "
            "sangat menghargai kualifikasi Anda. Data Anda (dengan persetujuan Anda) akan tetap tersimpan "
            "dalam talent pool kami untuk peluang karier lain yang sesuai di masa depan. Kami mendorong Anda "
            "untuk terus memperkaya portofolio Anda berdasarkan rekomendasi di atas."
        )
    else:
        next_steps = (
            "Aplikasi Anda saat ini sedang dalam antrean evaluasi aktif oleh tim rekrutmen kami. Kami akan "
            "segera memperbarui status seleksi Anda setelah proses peninjauan selesai."
        )

    email_draft = (
        f"Subjek: Umpan Balik Rekrutmen & Pembaruan Status Seleksi: {job_title} | KarsaHire\n\n"
        f"Yth. Rekan Kandidat ({candidate_label}),\n\n"
        f"Terima kasih atas antusiasme dan waktu yang telah Anda dedikasikan untuk melamar posisi "
        f"{job_title} di perusahaan kami.\n\n"
        f"Sebagai bagian dari komitmen kami terhadap budaya rekrutmen yang transparan, konstruktif, dan beretika "
        f"(mematuhi UU Pelindungan Data Pribadi No. 27/2022), kami ingin membagikan ringkasan umpan balik "
        f"berbasis bukti objektif atas berkas lamaran yang Anda kirimkan.\n\n"
        f"----------------------------------------------------------------------\n"
        f"RINGKASAN STATUS KEPUTUSAN:\n"
        f"{decision_summary}\n"
        f"----------------------------------------------------------------------\n\n"
        f"KOMPETENSI & KEKUATAN YANG TERVERIFIKASI:\n"
        f"Berikut adalah aspek kualifikasi yang berhasil diverifikasi oleh tim peninjau manusia "
        f"berdasarkan dokumen berkas Anda:\n"
        f"{strengths_text}\n\n"
        f"AREA PENGEMBANGAN & SARAN TINDAK LANJUT:\n"
        f"Berikut adalah kriteria yang belum teridentifikasi secara eksplisit dalam berkas, beserta saran "
        f"konstruktif untuk penguatan portofolio Anda:\n"
        f"{growth_text}\n\n"
        f"LANGKAH SELANJUTNYA:\n"
        f"{next_steps}\n\n"
        f"----------------------------------------------------------------------\n"
        f"PERNYATAAN TRANSPARANSI (UU PDP NO. 27/2022):\n"
        f"{transparency_notice}\n"
        f"----------------------------------------------------------------------\n\n"
        f"Kami mendoakan yang terbaik bagi perjalanan karier profesional Anda. Jangan ragu untuk membalas "
        f"email ini apabila Anda memiliki pertanyaan lebih lanjut.\n\n"
        f"Salam hangat,\n"
        f"Tim Talent Acquisition & Rekrutmen\n"
        f"KarsaHire"
    )

    return email_draft


def generate_candidate_feedback(db: sqlite3.Connection, candidate_id: str) -> dict[str, Any]:
    """Generate constructive, evidence-based candidate feedback compliant with UU PDP No. 27/2022.

    Args:
        db: SQLite database connection.
        candidate_id: Unique candidate identifier (e.g. 'cand_...').

    Returns:
        dict containing:
        - candidate_id: Candidate identifier
        - job_title: Title of the applied job requisition
        - strengths: List of criteria where result is 'matched' or 'partial' with evidence explanations
        - growth_areas: List of criteria where result is 'unknown' (unverified) with recommendations
        - decision_summary: Summary of final human review decision & notes
        - transparency_notice: Formal UU PDP Pasal 40 statement confirming human-driven evaluation
        - feedback_email_draft: Ready-to-use professional feedback email template

    Raises:
        ValueError: If candidate_id is empty or candidate is not found.
    """
    if not candidate_id or not str(candidate_id).strip():
        raise ValueError("candidate_id tidak boleh kosong.")

    candidate_id = str(candidate_id).strip()
    cur = db.cursor()

    # 1. Fetch Candidate
    cur.execute(
        "SELECT id, job_id, file_type, profile_json, score, status, created_at "
        "FROM candidates WHERE id = ?",
        (candidate_id,),
    )
    cand_row = cur.fetchone()
    if not cand_row:
        raise ValueError(f"Kandidat dengan ID '{candidate_id}' tidak ditemukan.")

    cand = _row_to_dict(cur, cand_row)
    job_id = cand.get("job_id", "")

    # 2. Fetch Job Requisition
    cur.execute(
        "SELECT id, title, department, description, criteria_json, status, created_at "
        "FROM jobs WHERE id = ?",
        (job_id,),
    )
    job_row = cur.fetchone()
    job = _row_to_dict(cur, job_row) if job_row else {}
    job_title = job.get("title") or "Posisi Rekrutmen"

    # Candidate display label (e.g., 'Kandidat · 2412')
    cand_suffix = candidate_id[-4:].upper() if len(candidate_id) >= 4 else candidate_id.upper()
    candidate_label = f"Kandidat · {cand_suffix}"

    # 3. Fetch Evidence Records
    cur.execute(
        "SELECT id, candidate_id, criterion_id, criterion, requirement_type, weight, "
        "result, confidence, snippet, page_number "
        "FROM evidence WHERE candidate_id = ? "
        "ORDER BY weight DESC, criterion ASC",
        (candidate_id,),
    )
    evidence_rows = cur.fetchall()

    strengths: list[dict[str, Any]] = []
    growth_areas: list[dict[str, Any]] = []

    for erow in evidence_rows:
        ev = _row_to_dict(cur, erow)
        crit_id = ev.get("criterion_id", "")
        criterion = ev.get("criterion", "")
        result = ev.get("result", "")
        req_type = ev.get("requirement_type", "required")
        weight = float(ev.get("weight", 1.0))
        confidence = float(ev.get("confidence", 0.0))
        snippet = (ev.get("snippet") or "").strip()
        page_number = ev.get("page_number")

        if result in ("matched", "partial"):
            explanation = _format_strength_explanation(
                criterion=criterion,
                result=result,
                requirement_type=req_type,
                snippet=snippet,
                job_title=job_title,
            )
            strengths.append({
                "criterion_id": crit_id,
                "criterion": criterion,
                "result": result,
                "requirement_type": req_type,
                "weight": weight,
                "confidence": confidence,
                "snippet": snippet,
                "page_number": page_number,
                "explanation": explanation,
            })
        elif result == "unknown":
            explanation, recommendation = _format_growth_recommendation(
                criterion=criterion,
                requirement_type=req_type,
                job_title=job_title,
            )
            growth_areas.append({
                "criterion_id": crit_id,
                "criterion": criterion,
                "result": "unknown",
                "requirement_type": req_type,
                "weight": weight,
                "explanation": explanation,
                "recommendation": recommendation,
            })

    # 4. Fetch Reviews
    cur.execute(
        "SELECT id, candidate_id, reviewer, role, decision, note, created_at "
        "FROM reviews WHERE candidate_id = ? "
        "ORDER BY created_at DESC",
        (candidate_id,),
    )
    review_rows = cur.fetchall()
    reviews = [_row_to_dict(cur, r) for r in review_rows]

    # 5. Build Decision Summary
    decision_summary = _format_decision_summary(
        status=cand.get("status", "needs_review"),
        job_title=job_title,
        reviews=reviews,
    )

    # 6. Transparency Notice
    transparency_notice = TRANSPARENCY_NOTICE_PDP

    # 7. Feedback Email Draft
    feedback_email_draft = _build_feedback_email_draft(
        candidate_id=candidate_id,
        job_title=job_title,
        candidate_label=candidate_label,
        decision_summary=decision_summary,
        status=cand.get("status", "needs_review"),
        strengths=strengths,
        growth_areas=growth_areas,
        transparency_notice=transparency_notice,
    )

    return {
        "candidate_id": candidate_id,
        "job_title": job_title,
        "strengths": strengths,
        "growth_areas": growth_areas,
        "decision_summary": decision_summary,
        "transparency_notice": transparency_notice,
        "feedback_email_draft": feedback_email_draft,
    }
