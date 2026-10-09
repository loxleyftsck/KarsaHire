"""Unit and integration tests for Candidate Feedback & Transparency Service."""

import json
import sqlite3
import unittest

import feedback_service
import server
from tests.test_server import ServerTestCase


class TestFeedbackService(unittest.TestCase):
    """Test suite for feedback_service module using in-memory SQLite fixtures."""

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
        """)

        # Seed fixture: Job
        self.job_id = "job_test_01"
        self.job_title = "Senior Backend Engineer"
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self.job_id, self.job_title, "Engineering", "Build scalable APIs", "[]", "criteria_approved", "2026-10-01T00:00:00Z"),
        )

        # Seed fixture: Candidate
        self.candidate_id = "cand_test_01"
        self.db.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self.candidate_id, self.job_id, "pdf", json.dumps({"skills": ["python", "docker"]}), 75.0, "needs_review", "2026-10-01T01:00:00Z"),
        )

        # Seed fixture: Evidence (matched, partial, unknown)
        self.evidence_data = [
            ("ev_1", self.candidate_id, "crit_py", "Python", "required", 2.0, "matched", 1.0, "Proficient in Python and FastAPI", 1),
            ("ev_2", self.candidate_id, "crit_doc", "Docker", "preferred", 1.0, "partial", 0.5, "Used Docker in staging deployment", 2),
            ("ev_3", self.candidate_id, "crit_k8s", "Kubernetes", "required", 2.0, "unknown", 0.0, "", None),
        ]
        self.db.executemany("INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", self.evidence_data)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_generate_feedback_structure_and_keys(self):
        """Feedback payload must return all canonical required keys and types."""
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)

        self.assertIsInstance(feedback, dict)
        expected_keys = {
            "candidate_id",
            "job_title",
            "strengths",
            "growth_areas",
            "decision_summary",
            "transparency_notice",
            "feedback_email_draft",
        }
        self.assertEqual(set(feedback.keys()), expected_keys)
        self.assertEqual(feedback["candidate_id"], self.candidate_id)
        self.assertEqual(feedback["job_title"], self.job_title)

    def test_strengths_categorization(self):
        """Criteria with 'matched' and 'partial' must appear in strengths with explanations."""
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        strengths = feedback["strengths"]

        self.assertEqual(len(strengths), 2)
        criteria_names = [s["criterion"] for s in strengths]
        self.assertIn("Python", criteria_names)
        self.assertIn("Docker", criteria_names)

        py_item = next(s for s in strengths if s["criterion"] == "Python")
        self.assertEqual(py_item["result"], "matched")
        self.assertEqual(py_item["snippet"], "Proficient in Python and FastAPI")
        self.assertIn("terverifikasi", py_item["explanation"].lower())

        doc_item = next(s for s in strengths if s["criterion"] == "Docker")
        self.assertEqual(doc_item["result"], "partial")
        self.assertIn("sebagian", doc_item["explanation"].lower())

    def test_growth_areas_categorization(self):
        """Criteria with 'unknown' must appear in growth_areas with constructive recommendations."""
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        growth_areas = feedback["growth_areas"]

        self.assertEqual(len(growth_areas), 1)
        k8s_item = growth_areas[0]
        self.assertEqual(k8s_item["criterion"], "Kubernetes")
        self.assertEqual(k8s_item["result"], "unknown")
        self.assertIn("belum ditemukan atau belum terverifikasi", k8s_item["explanation"].lower())
        self.assertIn("portofolio", k8s_item["recommendation"].lower())

    def test_decision_summary_with_human_reviews(self):
        """Decision summary must reflect human reviewer decisions and notes."""
        self.db.execute(
            "INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rev_1", self.candidate_id, "Budi HR", "recruiter", "advance", "Kandidat memiliki fondasi teknis kuat.", "2026-10-01T02:00:00Z"),
        )
        self.db.execute("UPDATE candidates SET status='advance' WHERE id=?", (self.candidate_id,))
        self.db.commit()

        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        summary = feedback["decision_summary"]

        self.assertIn("Advance", summary)
        self.assertIn("Budi HR", summary)
        self.assertIn("Kandidat memiliki fondasi teknis kuat", summary)

    def test_decision_summary_pending_review(self):
        """Decision summary when candidate is awaiting review (needs_review)."""
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        summary = feedback["decision_summary"]
        self.assertIn("Needs Review", summary)

    def test_transparency_notice_uu_pdp_compliance(self):
        """Transparency notice must explicitly reference UU PDP No. 27/2022 Pasal 40 and HITL."""
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        notice = feedback["transparency_notice"]

        self.assertIn("UU No. 27", notice)
        self.assertIn("2022", notice)
        self.assertIn("Pasal 40", notice)
        self.assertIn("Human-in-the-Loop", notice)
        self.assertIn("penolakan otomatis", notice)

    def test_feedback_email_draft_polite_and_actionable(self):
        """Email draft must be personalized, polite, constructive, and actionable."""
        feedback = feedback_service.generate_candidate_feedback(self.db, self.candidate_id)
        email = feedback["feedback_email_draft"]

        self.assertIn("Subjek:", email)
        self.assertIn(self.job_title, email)
        self.assertIn("Python", email)
        self.assertIn("Kubernetes", email)
        self.assertIn("UU Pelindungan Data Pribadi", email)
        self.assertIn("Salam hangat", email)

    def test_candidate_not_found_raises_value_error(self):
        """Calling with non-existent candidate_id must raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            feedback_service.generate_candidate_feedback(self.db, "cand_non_existent")
        self.assertIn("tidak ditemukan", str(ctx.exception).lower())

    def test_empty_candidate_id_raises_value_error(self):
        """Calling with empty candidate_id must raise ValueError."""
        with self.assertRaises(ValueError):
            feedback_service.generate_candidate_feedback(self.db, "")


class TestCandidateFeedbackEndpoint(ServerTestCase):
    """Test HTTP API endpoint GET /api/candidates/{id}/feedback."""

    def test_get_candidate_feedback_success(self):
        # 1. Create and approve job
        _, job = self.post_json("/api/jobs", {
            "title": "Cloud Platform Engineer",
            "criteria": [
                {"label": "python", "type": "required"},
                {"label": "docker", "type": "preferred"},
            ],
        })
        job_id = job["id"]
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Recruiter A", "role": "recruiter"})
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Manager B", "role": "hiring_manager"})

        # 2. Upload candidate
        status, cand = self.post_multipart(
            f"/api/jobs/{job_id}/candidates",
            "resume.txt",
            "Experienced Python developer with 5 years experience.",
        )
        self.assertEqual(status, 201)
        cand_id = cand["id"]

        # 3. Request feedback endpoint
        status, feedback = self.get(f"/api/candidates/{cand_id}/feedback")
        self.assertEqual(status, 200)
        self.assertEqual(feedback["candidate_id"], cand_id)
        self.assertEqual(feedback["job_title"], "Cloud Platform Engineer")
        self.assertIsInstance(feedback["strengths"], list)
        self.assertIsInstance(feedback["growth_areas"], list)
        self.assertIsInstance(feedback["decision_summary"], str)
        self.assertIsInstance(feedback["transparency_notice"], str)
        self.assertIsInstance(feedback["feedback_email_draft"], str)

        # Check UU PDP transparency
        self.assertIn("UU No. 27", feedback["transparency_notice"])
        self.assertIn("Pasal 40", feedback["transparency_notice"])

    def test_get_candidate_feedback_not_found(self):
        status, data = self.get("/api/candidates/cand_invalid_9999/feedback")
        self.assertEqual(status, 404)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
