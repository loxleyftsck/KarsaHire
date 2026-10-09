"""Unit tests for feedback_service module using in-memory SQLite database."""

import json
import sqlite3
import unittest

import feedback_service


class TestFeedbackService(unittest.TestCase):
    """Test suite for candidate feedback generation with in-memory SQLite."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            department TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            criteria_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'criteria_approved',
            created_at TEXT NOT NULL
        );

        CREATE TABLE candidates (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            file_type TEXT NOT NULL,
            profile_json TEXT NOT NULL DEFAULT '{}',
            score REAL NOT NULL DEFAULT 0.0,
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
        """)

        # Fixture: Job Requisition
        self.job_id = "job_dev_101"
        self.job_title = "Lead Backend Engineer"
        self.db.execute(
            "INSERT INTO jobs (id, title, department, description, criteria_json, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.job_id,
                self.job_title,
                "Platform Engineering",
                "High scale microservices development",
                json.dumps([
                    {"id": "crit_py", "label": "Python", "type": "required", "weight": 2.0},
                    {"id": "crit_fastapi", "label": "FastAPI", "type": "required", "weight": 1.5},
                    {"id": "crit_k8s", "label": "Kubernetes", "type": "required", "weight": 2.0},
                    {"id": "crit_doc", "label": "Docker", "type": "preferred", "weight": 1.0},
                    {"id": "crit_aws", "label": "AWS Cloud", "type": "preferred", "weight": 1.0},
                ]),
                "criteria_approved",
                "2026-10-01T08:00:00Z",
            ),
        )

        # Fixture: Candidate
        self.candidate_id = "cand_verified_42"
        self.db.execute(
            "INSERT INTO candidates (id, job_id, file_type, profile_json, score, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.candidate_id,
                self.job_id,
                "pdf",
                json.dumps({"skills": ["Python", "FastAPI", "Docker"]}),
                78.5,
                "needs_review",
                "2026-10-02T09:30:00Z",
            ),
        )

        # Fixture: Evidence with matched, partial, and unknown items
        self.evidence_rows = [
            ("ev_1", self.candidate_id, "crit_py", "Python", "required", 2.0, "matched", 0.95, "Over 5 years building scalable Python services", 1),
            ("ev_2", self.candidate_id, "crit_doc", "Docker", "preferred", 1.0, "matched", 0.90, "Containerized microservices using Docker", 2),
            ("ev_3", self.candidate_id, "crit_fastapi", "FastAPI", "required", 1.5, "partial", 0.65, "Hands-on exploration with FastAPI endpoints", 2),
            ("ev_4", self.candidate_id, "crit_k8s", "Kubernetes", "required", 2.0, "unknown", 0.0, "", None),
            ("ev_5", self.candidate_id, "crit_aws", "AWS Cloud", "preferred", 1.0, "unknown", 0.0, "", None),
        ]
        self.db.executemany(
            "INSERT INTO evidence (id, candidate_id, criterion_id, criterion, requirement_type, weight, result, confidence, snippet, page_number) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            self.evidence_rows,
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_generate_candidate_feedback_structure(self):
        """Verify feedback payload returns all expected canonical fields and correct types."""
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)

        self.assertIsInstance(feedback, dict)
        self.assertEqual(feedback["candidate_id"], self.candidate_id)
        self.assertEqual(feedback["job_title"], self.job_title)

        required_keys = {
            "candidate_id",
            "job_title",
            "strengths",
            "growth_areas",
            "decision_summary",
            "transparency_notice",
            "feedback_email_draft",
        }
        self.assertTrue(required_keys.issubset(set(feedback.keys())))
        self.assertIsInstance(feedback["strengths"], list)
        self.assertIsInstance(feedback["growth_areas"], list)
        self.assertIsInstance(feedback["decision_summary"], str)
        self.assertIsInstance(feedback["transparency_notice"], str)
        self.assertIsInstance(feedback["feedback_email_draft"], str)

    def test_strengths_categorization_matched_and_partial(self):
        """Verify matched and partial evidence are correctly placed into strengths."""
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        strengths = feedback["strengths"]

        # Python, Docker, FastAPI should be in strengths
        self.assertEqual(len(strengths), 3)
        crit_names = [s["criterion"] for s in strengths]
        self.assertIn("Python", crit_names)
        self.assertIn("Docker", crit_names)
        self.assertIn("FastAPI", crit_names)

        # Check matched item explanation
        py_item = next(s for s in strengths if s["criterion"] == "Python")
        self.assertEqual(py_item["result"], "matched")
        self.assertEqual(py_item["snippet"], "Over 5 years building scalable Python services")
        self.assertIn("terverifikasi", py_item["explanation"].lower())

        # Check partial item explanation
        fastapi_item = next(s for s in strengths if s["criterion"] == "FastAPI")
        self.assertEqual(fastapi_item["result"], "partial")
        self.assertIn("sebagian", fastapi_item["explanation"].lower())

    def test_growth_areas_categorization_unknown(self):
        """Verify unknown criteria are routed to growth_areas with constructive career recommendations."""
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        growth_areas = feedback["growth_areas"]

        # Kubernetes and AWS Cloud should be in growth_areas
        self.assertEqual(len(growth_areas), 2)
        growth_names = [g["criterion"] for g in growth_areas]
        self.assertIn("Kubernetes", growth_names)
        self.assertIn("AWS Cloud", growth_names)

        for g in growth_areas:
            self.assertEqual(g["result"], "unknown")
            self.assertIn("belum ditemukan atau belum terverifikasi", g["explanation"].lower())
            self.assertTrue(len(g["recommendation"]) > 10)
            self.assertIn("portofolio", g["recommendation"].lower())

    def test_decision_summary_advance_status_with_reviewers(self):
        """Verify decision summary synthesis when human reviewers recommend advance."""
        self.db.execute(
            "INSERT INTO reviews (id, candidate_id, reviewer, role, decision, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rev_1", self.candidate_id, "Citra HR", "recruiter", "advance", "Kandidat sangat potensial untuk backend", "2026-10-02T10:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO reviews (id, candidate_id, reviewer, role, decision, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rev_2", self.candidate_id, "Doni Tech Lead", "hiring_manager", "advance", "Pengalaman Python sangat solid", "2026-10-02T10:30:00Z"),
        )
        self.db.execute("UPDATE candidates SET status = 'advance' WHERE id = ?", (self.candidate_id,))
        self.db.commit()

        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        summary = feedback["decision_summary"]

        self.assertIn("Advance", summary)
        self.assertIn("Citra HR", summary)
        self.assertIn("Doni Tech Lead", summary)
        self.assertIn("Pengalaman Python sangat solid", summary)

    def test_decision_summary_not_selected_and_needs_info(self):
        """Verify decision summary for not_selected and needs_info statuses."""
        # Test not_selected
        self.db.execute("UPDATE candidates SET status = 'not_selected' WHERE id = ?", (self.candidate_id,))
        self.db.commit()
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        self.assertIn("Not Selected", feedback["decision_summary"])

        # Test needs_info
        self.db.execute("UPDATE candidates SET status = 'needs_info' WHERE id = ?", (self.candidate_id,))
        self.db.commit()
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        self.assertIn("Needs Info", feedback["decision_summary"])

    def test_transparency_notice_pdp_compliance(self):
        """Verify legal compliance notice covers UU PDP No. 27/2022 Pasal 40, HITL, and no black-box."""
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        notice = feedback["transparency_notice"]

        self.assertIn("UU No. 27", notice)
        self.assertIn("2022", notice)
        self.assertIn("Pasal 40", notice)
        self.assertIn("Human-in-the-Loop", notice)
        self.assertIn("penolakan otomatis", notice)

    def test_feedback_email_draft_structure(self):
        """Verify feedback email draft contains respectful tone, strengths, growth areas, and transparency."""
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        email = feedback["feedback_email_draft"]

        self.assertIn("Subjek:", email)
        self.assertIn(self.job_title, email)
        self.assertIn("Python", email)
        self.assertIn("Kubernetes", email)
        self.assertIn("UU Pelindungan Data Pribadi", email)
        self.assertIn("Salam hangat", email)
        self.assertIn("KarsaHire", email)

    def test_nonexistent_candidate_raises_value_error(self):
        """Attempting to generate feedback for non-existent candidate must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            feedback_service.generate_candidate_feedback(self.db, "cand_ghost_999")
        self.assertIn("tidak ditemukan", str(ctx.exception).lower())

    def test_empty_candidate_id_raises_value_error(self):
        """Attempting to generate feedback with blank candidate_id must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            feedback_service.generate_candidate_feedback(self.db, "   ")
        self.assertIn("tidak boleh kosong", str(ctx.exception).lower())

    def test_candidate_without_evidence_handles_gracefully(self):
        """Candidate with no evidence rows should produce valid empty strengths and growth lists."""
        empty_cand_id = "cand_empty_99"
        self.db.execute(
            "INSERT INTO candidates (id, job_id, file_type, profile_json, score, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (empty_cand_id, self.job_id, "pdf", "{}", 0.0, "needs_review", "2026-10-02T11:00:00Z"),
        )
        self.db.commit()

        feedback = feedback_service.generate_candidate_feedback(self.db, empty_cand_id)
        self.assertEqual(feedback["candidate_id"], empty_cand_id)
        self.assertEqual(feedback["strengths"], [])
        self.assertEqual(feedback["growth_areas"], [])
        self.assertIsInstance(feedback["feedback_email_draft"], str)


if __name__ == "__main__":
    unittest.main()
