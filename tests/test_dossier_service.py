"""Unit and integration tests for Executive Dossier Service."""

import json
import sqlite3
import unittest

import dossier_service
import interview_service
import server


class TestDossierService(unittest.TestCase):
    """Test suite for generate_job_dossier_html and supporting dossier functions."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        server.migrate_to_v1(self.db)
        interview_service.init_interview_tables(self.db)

        # Seed Job Requisition
        self.job_id = "job_exec_001"
        self.job_title = "Principal Platform Engineer"
        self.department = "Enterprise Cloud Architecture"
        self.criteria = [
            {"id": "crit_1", "label": "Distributed Systems", "type": "required", "weight": 2.0},
            {"id": "crit_2", "label": "Go / Golang", "type": "required", "weight": 2.0},
            {"id": "crit_3", "label": "Kubernetes Architecture", "type": "required", "weight": 1.5},
            {"id": "crit_4", "label": "Observability & OpenTelemetry", "type": "preferred", "weight": 1.0},
        ]
        self.db.execute(
            "INSERT INTO jobs (id, title, department, description, criteria_json, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.job_id,
                self.job_title,
                self.department,
                "Lead cloud native transformation and resilience",
                json.dumps(self.criteria),
                "criteria_approved",
                "2026-10-01T08:00:00Z",
            ),
        )

        # Seed Dual-Approval (Recruiter & Hiring Manager)
        self.db.execute(
            "INSERT INTO approvals (id, job_id, reviewer, role, created_at) VALUES (?, ?, ?, ?, ?)",
            ("app_1", self.job_id, "Sarah Jenkins", "recruiter", "2026-10-01T09:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO approvals (id, job_id, reviewer, role, created_at) VALUES (?, ?, ?, ?, ?)",
            ("app_2", self.job_id, "Dr. Irwan Setiawan", "hiring_manager", "2026-10-01T09:30:00Z"),
        )

        # Seed Candidate A (Advanced)
        self.cand_a = "cand_alpha_01"
        self.db.execute(
            "INSERT INTO candidates (id, job_id, file_type, profile_json, score, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.cand_a,
                self.job_id,
                "pdf",
                json.dumps({"name": "Alpha Dev", "skills": ["Go", "Kubernetes", "Distributed Systems"]}),
                92.5,
                "advance",
                "2026-10-02T10:00:00Z",
            ),
        )

        # Seed Candidate B (Needs Review)
        self.cand_b = "cand_beta_02"
        self.db.execute(
            "INSERT INTO candidates (id, job_id, file_type, profile_json, score, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.cand_b,
                self.job_id,
                "docx",
                json.dumps({"name": "Beta Engineer", "skills": ["Go", "Docker"]}),
                68.0,
                "needs_review",
                "2026-10-02T11:00:00Z",
            ),
        )

        # Evidence for Candidate A
        self.db.executemany(
            "INSERT INTO evidence (id, candidate_id, criterion_id, criterion, requirement_type, weight, result, confidence, snippet, page_number) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("ev_a1", self.cand_a, "crit_1", "Distributed Systems", "required", 2.0, "matched", 0.95, "Designed high-throughput distributed message bus", 1),
                ("ev_a2", self.cand_a, "crit_2", "Go / Golang", "required", 2.0, "matched", 0.92, "7 years Go production microservices", 1),
                ("ev_a3", self.cand_a, "crit_3", "Kubernetes Architecture", "required", 1.5, "matched", 0.88, "Managed 50+ multi-region K8s clusters", 2),
                ("ev_a4", self.cand_a, "crit_4", "Observability & OpenTelemetry", "preferred", 1.0, "partial", 0.60, "Configured Prometheus metrics", 3),
            ],
        )

        # Evidence for Candidate B
        self.db.executemany(
            "INSERT INTO evidence (id, candidate_id, criterion_id, criterion, requirement_type, weight, result, confidence, snippet, page_number) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("ev_b1", self.cand_b, "crit_1", "Distributed Systems", "required", 2.0, "unknown", 0.0, "", None),
                ("ev_b2", self.cand_b, "crit_2", "Go / Golang", "required", 2.0, "matched", 0.85, "Built internal CLI tools in Go", 1),
                ("ev_b3", self.cand_b, "crit_3", "Kubernetes Architecture", "required", 1.5, "partial", 0.50, "Deployed Helm charts", 2),
                ("ev_b4", self.cand_b, "crit_4", "Observability & OpenTelemetry", "preferred", 1.0, "unknown", 0.0, "", None),
            ],
        )

        # Human Reviews
        self.db.executemany(
            "INSERT INTO reviews (id, candidate_id, reviewer, role, decision, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("rev_1", self.cand_a, "Sarah Jenkins", "recruiter", "advance", "Strong enterprise track record", "2026-10-03T08:00:00Z"),
                ("rev_2", self.cand_a, "Dr. Irwan Setiawan", "hiring_manager", "advance", "Excellent architectural depth", "2026-10-03T09:00:00Z"),
                ("rev_3", self.cand_b, "Sarah Jenkins", "recruiter", "needs_info", "Needs clarification on distributed systems", "2026-10-03T08:30:00Z"),
                ("rev_4", self.cand_b, "Dr. Irwan Setiawan", "hiring_manager", "not_selected", "Lacks required scale experience", "2026-10-03T09:45:00Z"),
            ],
        )

        # Interview Scorecard for Candidate A
        self.db.execute(
            "INSERT INTO interview_scorecards (id, job_id, candidate_id, reviewer, role, overall_recommendation, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("sc_1", self.job_id, self.cand_a, "Dr. Irwan Setiawan", "hiring_manager", "advance", "Solid STAR behavioral examples", "2026-10-04T10:00:00Z"),
        )
        self.db.executemany(
            "INSERT INTO interview_criterion_scores (id, scorecard_id, criterion_id, criterion_label, score, evidence_notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("ics_1", "sc_1", "crit_1", "Distributed Systems", 5, "Exemplary understanding of consensus algorithms"),
                ("ics_2", "sc_1", "crit_2", "Go / Golang", 4, "High proficiency and clean idioms"),
            ],
        )

        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_generate_job_dossier_html_full_generation(self):
        """Verify that generate_job_dossier_html produces complete HTML with all critical executive elements."""
        html_doc = dossier_service.generate_job_dossier_html(self.db, self.job_id)

        self.assertIsInstance(html_doc, str)
        self.assertGreater(len(html_doc), 2000)

        # 1. HTML document shell
        self.assertIn("<!DOCTYPE html>", html_doc)
        self.assertIn("<html", html_doc)
        self.assertIn("</html>", html_doc)

        # 2. Letterhead & Requisition Metadata
        self.assertIn("KarsaHire", html_doc)
        self.assertIn("Executive Hiring Dossier", html_doc)
        self.assertIn(self.job_title, html_doc)
        self.assertIn(self.department, html_doc)
        self.assertIn(self.job_id, html_doc)

        # 3. Dual-Approval Log with Seals
        self.assertIn("Sarah Jenkins", html_doc)
        self.assertIn("Dr. Irwan Setiawan", html_doc)
        self.assertIn("KRS-", html_doc)  # Verification seal format
        self.assertIn("Dual-Approval", html_doc)

        # 4. Pipeline Funnel & Score Metrics
        self.assertIn("Funnel", html_doc)
        self.assertIn("92.5", html_doc)  # Max / Candidate A score
        self.assertIn("68.0", html_doc)  # Candidate B score

        # 5. Reviewer Alignment / Agreement
        self.assertIn("Reviewer", html_doc)
        self.assertTrue(
            "Cohen" in html_doc or "Konsensus" in html_doc or "Agreement" in html_doc or "Divergensi" in html_doc
        )

        # 6. Candidate Comparison Matrix & Evidence
        self.assertIn("cand_alpha_01", html_doc)
        self.assertIn("Distributed Systems", html_doc)
        self.assertIn("advance", html_doc.lower())

        # 7. Regulatory Compliance (UU PDP, NYC LL144, EU AI Act)
        self.assertIn("UU PDP", html_doc)
        self.assertIn("27/2022", html_doc)
        self.assertIn("LL144", html_doc)
        self.assertIn("EU AI Act", html_doc)

        # 8. Modern Print CSS Styling
        self.assertIn("@media print", html_doc)
        self.assertIn("<style>", html_doc)

    def test_generate_job_dossier_html_single_approval(self):
        """Verify dossier renders cleanly when only single approval is present."""
        job_single_id = "job_single_app"
        self.db.execute(
            "INSERT INTO jobs (id, title, department, description, criteria_json, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_single_id, "DevOps Engineer", "Ops", "Desc", "[]", "awaiting_approval", "2026-10-01T08:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO approvals (id, job_id, reviewer, role, created_at) VALUES (?, ?, ?, ?, ?)",
            ("app_single", job_single_id, "Solo Recruiter", "recruiter", "2026-10-01T09:00:00Z"),
        )
        self.db.commit()

        html_doc = dossier_service.generate_job_dossier_html(self.db, job_single_id)
        self.assertIn("Solo Recruiter", html_doc)
        self.assertIn("DevOps Engineer", html_doc)

    def test_generate_job_dossier_html_empty_candidates(self):
        """Verify dossier renders cleanly without candidates and avoids division by zero."""
        job_empty_id = "job_empty_002"
        self.db.execute(
            "INSERT INTO jobs (id, title, department, description, criteria_json, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_empty_id, "Junior QA Analyst", "Quality", "Desc", "[]", "criteria_approved", "2026-10-01T08:00:00Z"),
        )
        self.db.commit()

        html_doc = dossier_service.generate_job_dossier_html(self.db, job_empty_id)
        self.assertIn("Junior QA Analyst", html_doc)
        self.assertIn("KarsaHire", html_doc)

    def test_generate_job_dossier_html_nonexistent_job_raises_value_error(self):
        """Attempting to generate dossier for non-existent job must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            dossier_service.generate_job_dossier_html(self.db, "job_ghost_404")
        self.assertIn("tidak ditemukan", str(ctx.exception).lower())

    def test_generate_digital_seal_deterministic(self):
        """Verify cryptographic digital seal is deterministic and follows KRS-XXXX format."""
        seal_1 = dossier_service._generate_digital_seal("job_1", "Alice", "recruiter", "2026-10-01T00:00:00Z")
        seal_2 = dossier_service._generate_digital_seal("job_1", "Alice", "recruiter", "2026-10-01T00:00:00Z")
        seal_3 = dossier_service._generate_digital_seal("job_1", "Bob", "hiring_manager", "2026-10-01T00:00:00Z")

        self.assertEqual(seal_1, seal_2)
        self.assertNotEqual(seal_1, seal_3)
        self.assertTrue(seal_1.startswith("KRS-"))
        parts = seal_1.split("-")
        self.assertEqual(len(parts), 4)


if __name__ == "__main__":
    unittest.main()
