"""Unit and integration tests for criteria_assistant and its HTTP server endpoints."""

import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import criteria_assistant
import server


class TestCriteriaAssistant(unittest.TestCase):
    """Test suite for criteria_assistant module functions."""

    def test_get_criteria_recommendations_counts_and_weights(self):
        """Verify recommendations return 4-6 items with standard 1.0 vs 0.8 weights."""
        test_roles = [
            ("Software Developer", "IT"),
            ("Network Administrator", "Infrastructure"),
            ("Accountant", "Finance"),
            ("HR Specialist", "People"),
            ("Data Analyst", "Data"),
            ("Cybersecurity Analyst", "Security"),
            ("DevOps Engineer", "Platform"),
            ("Frontend Developer", "Web"),
            ("Product Manager", "Product"),
            ("Non-existent Wild Position", "Unknown"),
            ("", ""),
        ]

        for title, dept in test_roles:
            recs = criteria_assistant.get_criteria_recommendations(title, dept)
            self.assertGreaterEqual(len(recs), 4, f"Failed for {title}")
            self.assertLessEqual(len(recs), 6, f"Failed for {title}")

            for item in recs:
                self.assertIn("label", item)
                self.assertIn("type", item)
                self.assertIn("weight", item)
                self.assertIn(item["type"], ("required", "preferred"))
                if item["type"] == "required":
                    self.assertEqual(item["weight"], 1.0)
                else:
                    self.assertEqual(item["weight"], 0.8)

    def test_audit_criteria_calibration_well_calibrated(self):
        """Verify healthy balanced criteria produce well_calibrated status."""
        recs = criteria_assistant.get_criteria_recommendations("Software Developer")
        audit = criteria_assistant.audit_criteria_calibration(recs)

        self.assertEqual(audit["status"], "well_calibrated")
        self.assertFalse(audit["has_monopoly_risk"])
        self.assertFalse(audit["monopoly_risk"])
        self.assertIsNone(audit["monopoly_criterion"])
        self.assertGreater(audit["required_weight"], audit["preferred_weight"])
        self.assertGreaterEqual(audit["criteria_count"], 4)
        self.assertIn("Terkalibrasi", audit["intake_notes"])
        self.assertTrue(len(audit["recommendations"]) > 0)

    def test_audit_criteria_calibration_too_strict(self):
        """Verify 100% required criteria trigger too_strict status."""
        strict_criteria = [
            {"label": "Python", "type": "required", "weight": 1.0},
            {"label": "FastAPI", "type": "required", "weight": 1.0},
            {"label": "PostgreSQL", "type": "required", "weight": 1.0},
            {"label": "Docker", "type": "required", "weight": 1.0},
        ]
        audit = criteria_assistant.audit_criteria_calibration(strict_criteria)

        self.assertEqual(audit["status"], "too_strict")
        self.assertEqual(audit["preferred_count"], 0)
        self.assertEqual(audit["preferred_weight"], 0.0)
        self.assertEqual(audit["required_ratio"], 1.0)
        self.assertTrue(any("purple squirrel" in r.lower() or "wajib" in r.lower() for r in audit["recommendations"]))

    def test_audit_criteria_calibration_monopoly_risk(self):
        """Verify criterion with > 40% of total weight triggers monopoly risk and unbalanced status."""
        monopoly_criteria = [
            {"label": "Core Mega Skill", "type": "required", "weight": 6.0},  # 6.0 / 8.8 = 68.2%
            {"label": "Minor Skill 1", "type": "required", "weight": 1.0},
            {"label": "Minor Skill 2", "type": "required", "weight": 1.0},
            {"label": "Pref Skill", "type": "preferred", "weight": 0.8},
        ]
        audit = criteria_assistant.audit_criteria_calibration(monopoly_criteria)

        self.assertEqual(audit["status"], "unbalanced")
        self.assertTrue(audit["has_monopoly_risk"])
        self.assertTrue(audit["monopoly_risk"])
        self.assertEqual(audit["monopoly_criterion"], "Core Mega Skill")
        self.assertIn("Core Mega Skill", audit["monopoly_criteria"])
        self.assertGreater(audit["max_weight_ratio"], 0.40)
        self.assertTrue(any("Core Mega Skill" in r for r in audit["recommendations"]))

    def test_audit_criteria_calibration_edge_cases(self):
        """Verify handling of empty list, zero weights, and preferred > required."""
        # Empty list
        empty_audit = criteria_assistant.audit_criteria_calibration([])
        self.assertEqual(empty_audit["status"], "unbalanced")
        self.assertEqual(empty_audit["criteria_count"], 0)

        # Preferred outweighs required
        unbalanced_criteria = [
            {"label": "Req 1", "type": "required", "weight": 1.0},
            {"label": "Pref 1", "type": "preferred", "weight": 2.0},
            {"label": "Pref 2", "type": "preferred", "weight": 2.0},
        ]
        unbal_audit = criteria_assistant.audit_criteria_calibration(unbalanced_criteria)
        self.assertEqual(unbal_audit["status"], "unbalanced")
        self.assertTrue(any("preferensi" in r.lower() for r in unbal_audit["recommendations"]))

    def test_generate_star_interview_guide_structure(self):
        """Verify STAR interview guide produces complete questions, probes, and anchors."""
        criteria = [
            {"label": "Programming", "type": "required", "weight": 1.0},
            {"label": "General Ledger", "type": "required", "weight": 1.0},
            {"label": "Custom Quantum Computing Skill", "type": "preferred", "weight": 0.8},
        ]
        guide = criteria_assistant.generate_star_interview_guide(criteria)

        self.assertEqual(len(guide), 3)

        for entry in guide:
            self.assertIn("criterion", entry)
            self.assertIn("question", entry)
            self.assertIn("star_probe", entry)
            probe = entry["star_probe"]
            self.assertIn("situation", probe)
            self.assertIn("task", probe)
            self.assertIn("action", probe)
            self.assertIn("result", probe)

            self.assertIn("look_for", entry)
            self.assertIsInstance(entry["look_for"], list)
            self.assertGreater(len(entry["look_for"]), 0)

            self.assertIn("red_flags", entry)
            self.assertIsInstance(entry["red_flags"], list)
            self.assertGreater(len(entry["red_flags"]), 0)

        # Verify custom skill probe contains the skill label
        custom_entry = guide[2]
        self.assertEqual(custom_entry["criterion"], "Custom Quantum Computing Skill")
        self.assertIn("Custom Quantum Computing Skill", custom_entry["question"])


class TestCriteriaAssistantEndpoints(unittest.TestCase):
    """Integration test suite for STAR and criteria recommendation HTTP endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.orig_db_path = server.DB_PATH
        cls.orig_data_dir = server.DATA
        cls.orig_manual_uploads = server.MANUAL_UPLOADS_ENABLED

        test_data_dir = Path(cls.temp_dir.name)
        server.DATA = test_data_dir
        server.DB_PATH = test_data_dir / "test_criteria_copilot.sqlite3"
        server.MANUAL_UPLOADS_ENABLED = True
        server.init_db()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.server_thread.join(timeout=2.0)

        server.DB_PATH = cls.orig_db_path
        server.DATA = cls.orig_data_dir
        server.MANUAL_UPLOADS_ENABLED = cls.orig_manual_uploads
        cls.temp_dir.cleanup()

    def setUp(self):
        with server.connect() as db:
            db.execute("PRAGMA foreign_keys = OFF")
            for table in [
                "interview_criterion_scores", "interview_scorecards", "reviews",
                "evidence", "candidates", "approvals", "audit_events", "jobs",
            ]:
                db.execute(f"DROP TABLE IF EXISTS {table}")
            db.execute("PRAGMA user_version = 0")
            db.execute("PRAGMA foreign_keys = ON")
        server.init_db()

    def get(self, path: str) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.status, data
        except urllib.error.HTTPError as exc:
            data = json.loads(exc.read().decode("utf-8"))
            return exc.code, data

    def post_json(self, path: str, payload: dict) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Origin": f"http://127.0.0.1:{self.port}",
                "X-KarsaHire-Request": "same-origin-ui",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.status, data
        except urllib.error.HTTPError as exc:
            data = json.loads(exc.read().decode("utf-8"))
            return exc.code, data

    def test_post_criteria_recommendations_success(self):
        """POST /api/criteria-recommendations should return recommended criteria and audit."""
        payload = {"title": "Software Developer", "department": "Engineering"}
        code, resp = self.post_json("/api/criteria-recommendations", payload)

        self.assertEqual(code, 200)
        self.assertEqual(resp["title"], "Software Developer")
        self.assertEqual(resp["department"], "Engineering")
        self.assertIn("recommendations", resp)
        self.assertIn("calibration", resp)
        self.assertGreaterEqual(len(resp["recommendations"]), 4)
        self.assertEqual(resp["calibration"]["status"], "well_calibrated")

    def test_post_criteria_recommendations_missing_title(self):
        """POST /api/criteria-recommendations without title should return 400 error."""
        payload = {"title": "", "department": "Engineering"}
        code, resp = self.post_json("/api/criteria-recommendations", payload)

        self.assertEqual(code, 400)
        self.assertIn("error", resp)

    def test_get_star_questions_approved_job(self):
        """GET /api/jobs/{id}/star-questions should return guide when criteria approved."""
        # 1. Create job
        create_payload = {
            "title": "Backend Engineer",
            "department": "Engineering",
            "description": "Backend API development",
            "criteria": [
                {"label": "Python", "type": "required"},
                {"label": "PostgreSQL", "type": "required"},
                {"label": "Docker", "type": "preferred"},
            ],
        }
        c_code, c_resp = self.post_json("/api/jobs", create_payload)
        self.assertEqual(c_code, 201)
        job_id = c_resp["id"]

        # 2. Before approval, star-questions must return 409
        unapproved_code, unapproved_resp = self.get(f"/api/jobs/{job_id}/star-questions")
        self.assertEqual(unapproved_code, 409)
        self.assertIn("error", unapproved_resp)

        # 3. Recruiter approval
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Recruiter Alice", "role": "recruiter"})
        # 4. Hiring Manager approval
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "HM Bob", "role": "hiring_manager"})

        # 5. After dual approval, star-questions must return 200
        approved_code, approved_resp = self.get(f"/api/jobs/{job_id}/star-questions")
        self.assertEqual(approved_code, 200)
        self.assertEqual(approved_resp["job_id"], job_id)
        self.assertEqual(approved_resp["status"], "criteria_approved")
        self.assertIn("star_questions", approved_resp)
        self.assertIn("calibration", approved_resp)

        questions = approved_resp["star_questions"]
        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[0]["criterion"], "Python")
        self.assertIn("star_probe", questions[0])
        self.assertIn("look_for", questions[0])
        self.assertIn("red_flags", questions[0])

    def test_get_star_questions_nonexistent_job(self):
        """GET /api/jobs/{id}/star-questions for nonexistent job returns 404."""
        code, resp = self.get("/api/jobs/job_nonexistent_999/star-questions")
        self.assertEqual(code, 404)
        self.assertIn("error", resp)


if __name__ == "__main__":
    unittest.main()
