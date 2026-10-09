"""Unit tests for Executive Dossier Service (dossier_service.py)."""

from __future__ import annotations

import json
import sqlite3
import unittest

import dossier_service
import interview_service


class TestDossierService(unittest.TestCase):
    """Test suite for generate_job_dossier_html and helper functions."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            department TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            criteria_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'awaiting_approval',
            created_at TEXT NOT NULL
        );

        CREATE TABLE approvals (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            reviewer TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE candidates (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            file_type TEXT NOT NULL,
            profile_json TEXT NOT NULL,
            score REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'needs_review',
            created_at TEXT NOT NULL
        );

        CREATE TABLE evidence (
            id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            criterion_id TEXT NOT NULL,
            criterion TEXT NOT NULL,
            requirement_type TEXT NOT NULL,
            weight REAL NOT NULL,
            result TEXT NOT NULL,
            confidence REAL NOT NULL,
            snippet TEXT NOT NULL,
            page_number INTEGER
        );

        CREATE TABLE reviews (
            id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            reviewer TEXT NOT NULL,
            role TEXT NOT NULL,
            decision TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE audit_events (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            candidate_id TEXT,
            actor TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        interview_service.init_interview_tables(self.db)

        # Seed test job
        self.job_id = "job_dev_100"
        self.criteria = [
            {"id": "crit_py", "label": "Python", "type": "required", "weight": 2.0},
            {"id": "crit_fastapi", "label": "FastAPI", "type": "required", "weight": 2.0},
            {"id": "crit_docker", "label": "Docker", "type": "preferred", "weight": 1.0},
        ]
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.job_id,
                "Lead Backend Architect",
                "Core Engineering",
                "Mendesain sistem terdistribusi skala besar.",
                json.dumps(self.criteria),
                "criteria_approved",
                "2026-09-15T08:00:00Z",
            ),
        )

    def tearDown(self):
        self.db.close()

    def test_job_not_found_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            dossier_service.generate_job_dossier_html(self.db, "job_nonexistent_999")
        self.assertIn("tidak ditemukan", str(ctx.exception))

    def test_empty_job_dossier(self):
        """Job with no approvals and no candidates should render without errors."""
        html_out = dossier_service.generate_job_dossier_html(self.db, self.job_id)
        self.assertIn("<!DOCTYPE html>", html_out)
        self.assertIn("Lead Backend Architect", html_out)
        self.assertIn("Core Engineering", html_out)
        self.assertIn("MENUNGGU TANDA TANGAN", html_out)
        self.assertIn("Belum ada pelamar yang terdaftar", html_out)
        self.assertIn("UU PDP No. 27/2022", html_out)
        self.assertIn("@media print", html_out)

    def test_complete_dossier_with_dual_approval_and_candidates(self):
        # 1. Add dual approvals
        self.db.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?)",
            ("apr_1", self.job_id, "Sarah Recruiter", "recruiter", "2026-09-16T09:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?)",
            ("apr_2", self.job_id, "Budi Engineering Head", "hiring_manager", "2026-09-16T10:00:00Z"),
        )

        # 2. Add candidates
        c1_id = "cand_alpha_01"
        c1_prof = {"skills": ["Python", "FastAPI", "Docker"], "experience_years_mentioned": 6, "education": ["S1 Teknik Informatika"]}
        self.db.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
            (c1_id, self.job_id, "pdf", json.dumps(c1_prof), 95.0, "advance", "2026-09-17T11:00:00Z"),
        )

        c2_id = "cand_beta_02"
        c2_prof = {"skills": ["Python"], "experience_years_mentioned": 2, "education": ["D3 Komputer"]}
        self.db.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
            (c2_id, self.job_id, "docx", json.dumps(c2_prof), 45.0, "needs_review", "2026-09-17T12:00:00Z"),
        )

        # Evidence for candidate 1
        self.db.execute(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ev_1", c1_id, "crit_py", "Python", "required", 2.0, "matched", 0.95, "Pengalaman 6 tahun Python", 1),
        )
        self.db.execute(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ev_2", c1_id, "crit_fastapi", "FastAPI", "required", 2.0, "matched", 0.90, "Membangun API dengan FastAPI", 2),
        )

        # Reviews for candidate 1 (Consensus: advance)
        self.db.execute(
            "INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rev_1", c1_id, "Sarah Recruiter", "recruiter", "advance", "Kandidat sangat solid", "2026-09-18T10:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rev_2", c1_id, "Budi Engineering Head", "hiring_manager", "advance", "Direkomendasikan lanjut", "2026-09-18T11:00:00Z"),
        )

        # Interview scorecard for candidate 1
        sc_id = interview_service.record_scorecard(self.db, {
            "job_id": self.job_id,
            "candidate_id": c1_id,
            "reviewer": "Budi Engineering Head",
            "role": "hiring_manager",
            "overall_recommendation": "strong_hire",
            "notes": "Pemahaman arsitektur sangat mendalam.",
            "criterion_scores": [
                {"criterion_id": "crit_py", "criterion_label": "Python", "score": 5},
                {"criterion_id": "crit_fastapi", "criterion_label": "FastAPI", "score": 4},
            ],
        })
        self.assertIsNotNone(sc_id)

        # Generate HTML Dossier
        html_out = dossier_service.generate_job_dossier_html(self.db, self.job_id)

        # Validations
        self.assertIn("PT KARSA HIRE NUSANTARA", html_out)
        self.assertIn("EXECUTIVE HIRING DOSSIER", html_out)
        self.assertIn("TERVERIFIKASI SAH", html_out)
        self.assertIn("Sarah Recruiter", html_out)
        self.assertIn("Budi Engineering Head", html_out)
        self.assertIn("KRS-", html_out)  # Digital integrity seal
        self.assertIn("Status Dual-Sign-Off Sah & Lengkap", html_out)

        # Funnel validations
        self.assertIn("Total Kandidat", html_out)
        self.assertIn("Skor Rata-Rata", html_out)
        self.assertIn("70.0", html_out)  # (95 + 45) / 2 = 70.0

        # Reviewer alignment
        self.assertIn("Tingkat Konsensus", html_out)
        self.assertIn("Cohen's Kappa", html_out)
        self.assertIn("Nihil Divergensi", html_out)

        # Top candidate table
        self.assertIn("Matriks Komparasi Kandidat Unggulan", html_out)
        self.assertIn("Kandidat &middot; A_01", html_out)
        self.assertIn("Advance", html_out)
        self.assertIn("4.5 / 5.0", html_out)  # (5 + 4)/2 = 4.5 average interview scorecard

        # Regulatory compliance notes
        self.assertIn("UU PDP No. 27/2022", html_out)
        self.assertIn("NYC LL144 Anti-Bias Audit", html_out)
        self.assertIn("EU AI Act Art. 14 (Oversight)", html_out)

        # Sign-off sheet
        self.assertIn("Lembar Pengesahan Risalah Rapat Komite", html_out)
        self.assertIn("Talent Acquisition Lead", html_out)

    def test_divergence_reporting_in_dossier(self):
        """When Recruiter and HM disagree on a candidate, divergence table must appear."""
        cid = "cand_div_99"
        self.db.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cid, self.job_id, "pdf", "{}", 80.0, "needs_review", "2026-09-17T11:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rev_d1", cid, "Recruiter One", "recruiter", "advance", "Pengalaman relevan", "2026-09-18T10:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rev_d2", cid, "HM One", "hiring_manager", "not_selected", "Kurang sesuai ekspektasi", "2026-09-18T11:00:00Z"),
        )

        html_out = dossier_service.generate_job_dossier_html(self.db, self.job_id)
        self.assertIn("Perlu Kalibrasi", html_out)
        self.assertIn("Pengalaman relevan", html_out)
        self.assertIn("Kurang sesuai ekspektasi", html_out)
        self.assertIn("1 Kasus", html_out)

    def test_xss_escaping_in_dossier(self):
        """Ensure potential script injections in titles or notes are safely escaped."""
        evil_job_id = "job_xss_test"
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                evil_job_id,
                '<script>alert("hacked")</script>',
                'Dept <img src=x onerror=alert(1)>',
                'Desc & "quotes"',
                json.dumps([{"id": "c1", "label": "<b style='color:red'>Bold</b>", "type": "required"}]),
                "open",
                "2026-09-01T00:00:00Z",
            ),
        )

        html_out = dossier_service.generate_job_dossier_html(self.db, evil_job_id)
        self.assertNotIn('<script>alert("hacked")</script>', html_out)
        self.assertIn('&lt;script&gt;alert(&quot;hacked&quot;)&lt;/script&gt;', html_out)
        self.assertNotIn('<img src=x onerror=alert(1)>', html_out)


if __name__ == "__main__":
    unittest.main()
