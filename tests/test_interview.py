"""Unit and integration tests for Structured Interview Rubrics & Scorecard service."""

import json
import sqlite3
import unittest

import interview_service


class TestInterviewScorecards(unittest.TestCase):
    """Comprehensive test suite for interview_service."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        interview_service.init_interview_tables(self.db)

    def tearDown(self):
        self.db.close()

    # -------------------------------------------------------------------------
    # 1. Table Initialization & Idempotency
    # -------------------------------------------------------------------------
    def test_init_tables_creates_expected_schema(self):
        """Verify tables and indexes are created properly."""
        cur = self.db.cursor()
        tables = [
            row[0]
            for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        self.assertIn("interview_scorecards", tables)
        self.assertIn("interview_criterion_scores", tables)
        self.assertIn("audit_events", tables)

        indexes = [
            row[0]
            for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        ]
        self.assertIn("idx_interview_scorecards_candidate", indexes)
        self.assertIn("idx_criterion_scores_scorecard", indexes)

    def test_init_tables_is_idempotent(self):
        """Calling init_interview_tables multiple times must not raise errors."""
        try:
            interview_service.init_interview_tables(self.db)
            interview_service.init_interview_tables(self.db)
        except Exception as exc:
            self.fail(f"init_interview_tables failed on repeat call: {exc}")

    # -------------------------------------------------------------------------
    # 2. Score & Rubric Validation
    # -------------------------------------------------------------------------
    def test_validate_score_valid_values(self):
        """Scores 1 through 5 (including numeric strings) must validate successfully."""
        for s in (1, 2, 3, 4, 5):
            self.assertEqual(interview_service.validate_score(s), s)
        for s_str in ("1", "2", "3", "4", "5"):
            self.assertEqual(interview_service.validate_score(s_str), int(s_str))

    def test_validate_score_invalid_values(self):
        """Scores out of 1-5 or non-integers must raise ValueError."""
        invalid_scores = [0, 6, -1, 10, "abc", None, "3.5", ""]
        for val in invalid_scores:
            with self.assertRaises(ValueError):
                interview_service.validate_score(val)

    def test_score_rubric_descriptions(self):
        """Verify standard 1-5 rubric descriptions."""
        self.assertEqual(interview_service.SCORE_RUBRIC[1], "Tidak memadai")
        self.assertEqual(interview_service.SCORE_RUBRIC[2], "Kurang")
        self.assertEqual(interview_service.SCORE_RUBRIC[3], "Memenuhi syarat")
        self.assertEqual(interview_service.SCORE_RUBRIC[4], "Kuat")
        self.assertEqual(interview_service.SCORE_RUBRIC[5], "Luar biasa")

    # -------------------------------------------------------------------------
    # 3. Recording Scorecard & Audit Trail
    # -------------------------------------------------------------------------
    def test_record_scorecard_success_and_audit(self):
        """Recording a valid scorecard persists records and writes an audit event."""
        payload = {
            "job_id": "job_backend_01",
            "candidate_id": "cand_101",
            "reviewer": "Budi Santoso",
            "role": "Recruiter",
            "overall_recommendation": "advance",
            "notes": "Kandidat sangat komunikatif dan terstruktur.",
            "criterion_scores": [
                {
                    "criterion_id": "crit_python",
                    "criterion_label": "Python & Backend API",
                    "score": 4,
                    "evidence_notes": "Menguasai FastAPI dan asyncio dengan baik.",
                },
                {
                    "criterion_id": "crit_collab",
                    "criterion_label": "Kolaborasi Tim",
                    "score": 3,
                    "evidence_notes": "Berpengalaman dalam sprint scrum standar.",
                },
            ],
        }

        sc_id = interview_service.record_scorecard(self.db, payload)
        self.assertTrue(sc_id.startswith("sc_") or len(sc_id) > 0)

        # Check scorecard in DB
        cur = self.db.cursor()
        sc_row = cur.execute(
            "SELECT * FROM interview_scorecards WHERE id = ?", (sc_id,)
        ).fetchone()
        self.assertIsNotNone(sc_row)
        self.assertEqual(sc_row["candidate_id"], "cand_101")
        self.assertEqual(sc_row["reviewer"], "Budi Santoso")
        self.assertEqual(sc_row["role"], "recruiter")  # normalized
        self.assertEqual(sc_row["overall_recommendation"], "advance")

        # Check criterion scores in DB
        cs_rows = cur.execute(
            "SELECT * FROM interview_criterion_scores WHERE scorecard_id = ? ORDER BY criterion_id",
            (sc_id,),
        ).fetchall()
        self.assertEqual(len(cs_rows), 2)
        self.assertEqual(cs_rows[0]["criterion_id"], "crit_collab")
        self.assertEqual(cs_rows[0]["score"], 3)
        self.assertEqual(cs_rows[1]["criterion_id"], "crit_python")
        self.assertEqual(cs_rows[1]["score"], 4)

        # Check audit event in DB
        audit_row = cur.execute(
            "SELECT * FROM audit_events WHERE candidate_id = ? AND event_type = ?",
            ("cand_101", "interview_scorecard_recorded"),
        ).fetchone()
        self.assertIsNotNone(audit_row)
        self.assertEqual(audit_row["actor"], "Budi Santoso")
        details = json.loads(audit_row["details_json"])
        self.assertEqual(details["scorecard_id"], sc_id)
        self.assertEqual(details["average_score"], 3.5)
        self.assertEqual(details["criterion_count"], 2)

    def test_record_scorecard_validation_missing_fields(self):
        """Missing required fields in record_scorecard must raise ValueError."""
        base = {
            "job_id": "job_01",
            "candidate_id": "cand_01",
            "reviewer": "Reviewer 1",
            "role": "hiring_manager",
            "overall_recommendation": "hire",
        }

        for field in ("job_id", "candidate_id", "reviewer", "role", "overall_recommendation"):
            invalid_data = dict(base)
            invalid_data[field] = ""
            with self.assertRaises(ValueError):
                interview_service.record_scorecard(self.db, invalid_data)

    def test_record_scorecard_invalid_score_rolls_back(self):
        """An invalid score must cause an error and roll back the whole transaction."""
        payload = {
            "job_id": "job_01",
            "candidate_id": "cand_fail",
            "reviewer": "Siti",
            "role": "recruiter",
            "overall_recommendation": "advance",
            "criterion_scores": [
                {"criterion_id": "crit_1", "score": 4},
                {"criterion_id": "crit_2", "score": 99},  # Invalid score
            ],
        }

        with self.assertRaises(ValueError):
            interview_service.record_scorecard(self.db, payload)

        cur = self.db.cursor()
        count = cur.execute(
            "SELECT COUNT(*) FROM interview_scorecards WHERE candidate_id = 'cand_fail'"
        ).fetchone()[0]
        self.assertEqual(count, 0)

    # -------------------------------------------------------------------------
    # 4. Scorecard Retrieval & Calculations
    # -------------------------------------------------------------------------
    def test_get_candidate_scorecards(self):
        """Verify retrieval of scorecards and attached criteria."""
        payload = {
            "job_id": "job_01",
            "candidate_id": "cand_retrieval",
            "reviewer": "Dewi",
            "role": "recruiter",
            "overall_recommendation": "advance",
            "criterion_scores": [
                {"criterion_id": "c1", "criterion_label": "Crit 1", "score": 5},
                {"criterion_id": "c2", "criterion_label": "Crit 2", "score": 3},
            ],
        }
        sc_id = interview_service.record_scorecard(self.db, payload)

        scorecards = interview_service.get_candidate_scorecards(self.db, "cand_retrieval")
        self.assertEqual(len(scorecards), 1)
        self.assertEqual(scorecards[0]["id"], sc_id)
        self.assertEqual(scorecards[0]["average_score"], 4.0)
        self.assertEqual(len(scorecards[0]["criterion_scores"]), 2)

        # Single scorecard fetch
        single = interview_service.get_scorecard(self.db, sc_id)
        self.assertIsNotNone(single)
        self.assertEqual(single["id"], sc_id)
        self.assertEqual(single["average_score"], 4.0)

        # Nonexistent single fetch
        self.assertIsNone(interview_service.get_scorecard(self.db, "non_existent"))

    # -------------------------------------------------------------------------
    # 5. Dual-Role Scorecard Summary & Calculations
    # -------------------------------------------------------------------------
    def test_candidate_interview_summary_dual_role(self):
        """Verify calculation of averages across recruiter and hiring manager roles."""
        cand_id = "cand_dual"

        # 1. Recruiter evaluation
        interview_service.record_scorecard(
            self.db,
            {
                "job_id": "job_dev",
                "candidate_id": cand_id,
                "reviewer": "Recruiter Alice",
                "role": "recruiter",
                "overall_recommendation": "advance",
                "criterion_scores": [
                    {"criterion_id": "crit_tech", "criterion_label": "Teknikal", "score": 4},
                    {"criterion_id": "crit_soft", "criterion_label": "Komunikasi", "score": 3},
                ],
            },
        )

        # 2. Hiring Manager evaluation
        interview_service.record_scorecard(
            self.db,
            {
                "job_id": "job_dev",
                "candidate_id": cand_id,
                "reviewer": "HM Bob",
                "role": "hiring_manager",
                "overall_recommendation": "advance",
                "criterion_scores": [
                    {"criterion_id": "crit_tech", "criterion_label": "Teknikal", "score": 5},
                    {"criterion_id": "crit_soft", "criterion_label": "Komunikasi", "score": 4},
                ],
            },
        )

        summary = interview_service.get_candidate_interview_summary(self.db, cand_id)

        self.assertEqual(summary["candidate_id"], cand_id)
        self.assertEqual(summary["total_scorecards"], 2)

        # Recruiter avg: (4 + 3) / 2 = 3.5
        self.assertEqual(summary["recruiter_average"], 3.5)

        # Hiring manager avg: (5 + 4) / 2 = 4.5
        self.assertEqual(summary["hiring_manager_average"], 4.5)

        # Overall avg across all evaluations: (4 + 3 + 5 + 4) / 4 = 4.0
        self.assertEqual(summary["overall_average_score"], 4.0)

        # Criteria breakdown
        tech_summary = summary["by_criterion"]["crit_tech"]
        self.assertEqual(tech_summary["average_score"], 4.5)  # (4 + 5) / 2
        self.assertEqual(tech_summary["count"], 2)

        soft_summary = summary["by_criterion"]["crit_soft"]
        self.assertEqual(soft_summary["average_score"], 3.5)  # (3 + 4) / 2
        self.assertEqual(soft_summary["count"], 2)

        # Role breakdown
        rec_role = summary["by_role"]["recruiter"]
        self.assertEqual(rec_role["scorecard_count"], 1)
        self.assertIn("Recruiter Alice", rec_role["reviewers"])
        self.assertEqual(rec_role["average_score"], 3.5)

        hm_role = summary["by_role"]["hiring_manager"]
        self.assertEqual(hm_role["scorecard_count"], 1)
        self.assertIn("HM Bob", hm_role["reviewers"])
        self.assertEqual(hm_role["average_score"], 4.5)

    def test_candidate_interview_summary_no_scorecards(self):
        """Candidate without evaluations returns structured empty summary with None averages."""
        summary = interview_service.get_candidate_interview_summary(self.db, "cand_empty")
        self.assertEqual(summary["candidate_id"], "cand_empty")
        self.assertEqual(summary["total_scorecards"], 0)
        self.assertIsNone(summary["overall_average_score"])
        self.assertIsNone(summary["recruiter_average"])
        self.assertIsNone(summary["hiring_manager_average"])
        self.assertEqual(summary["scorecards"], [])


if __name__ == "__main__":
    unittest.main()
