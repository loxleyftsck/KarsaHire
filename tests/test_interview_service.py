"""Unit and integration tests for interview_service.py."""

import json
import sqlite3
import unittest

import interview_service


class TestInterviewService(unittest.TestCase):
    """Test suite for structured interview scorecards and rubrics."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        interview_service.init_interview_tables(self.db)

    def tearDown(self):
        self.db.close()

    def test_init_interview_tables_idempotent(self):
        # Should be able to call again without errors
        interview_service.init_interview_tables(self.db)
        cur = self.db.cursor()
        tables = {
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("interview_scorecards", tables)
        self.assertIn("interview_criterion_scores", tables)
        self.assertIn("audit_events", tables)

    def test_record_and_get_scorecard_valid(self):
        data = {
            "job_id": "job_101",
            "candidate_id": "cand_202",
            "reviewer": "Siti Recruiter",
            "role": "recruiter",
            "overall_recommendation": "hire",
            "notes": "Kandidat memiliki komunikasi yang sangat baik dan latar belakang solid.",
            "criterion_scores": [
                {
                    "criterion_id": "crit_python",
                    "criterion_label": "Python & Backend Skills",
                    "score": 4,
                    "evidence_notes": "Menguasai typing, pytest, dan async dengan baik.",
                },
                {
                    "criterion_id": "crit_communication",
                    "criterion_label": "Komunikasi & Kolaborasi",
                    "score": 5,
                    "evidence_notes": "Jawaban terstruktur dengan metode STAR.",
                },
            ],
        }

        sc_id = interview_service.record_scorecard(self.db, data)
        self.assertTrue(sc_id.startswith("sc_"))

        # Verify scorecards retrieved for candidate
        scorecards = interview_service.get_candidate_scorecards(self.db, "cand_202")
        self.assertEqual(len(scorecards), 1)

        sc = scorecards[0]
        self.assertEqual(sc["id"], sc_id)
        self.assertEqual(sc["job_id"], "job_101")
        self.assertEqual(sc["candidate_id"], "cand_202")
        self.assertEqual(sc["reviewer"], "Siti Recruiter")
        self.assertEqual(sc["role"], "recruiter")
        self.assertEqual(sc["overall_recommendation"], "hire")
        self.assertEqual(sc["average_score"], 4.5)
        self.assertEqual(len(sc["criterion_scores"]), 2)

        crit_1 = sc["criterion_scores"][0]
        self.assertEqual(crit_1["criterion_id"], "crit_python")
        self.assertEqual(crit_1["score"], 4)
        self.assertEqual(crit_1["score_label"], "Kuat")

        crit_2 = sc["criterion_scores"][1]
        self.assertEqual(crit_2["criterion_id"], "crit_communication")
        self.assertEqual(crit_2["score"], 5)
        self.assertEqual(crit_2["score_label"], "Luar biasa")

        # Verify audit event
        cur = self.db.cursor()
        cur.execute("SELECT * FROM audit_events WHERE candidate_id = ?", ("cand_202",))
        audit_rows = cur.fetchall()
        self.assertEqual(len(audit_rows), 1)
        audit_row = audit_rows[0]
        self.assertEqual(audit_row[1], "job_101")  # job_id
        self.assertEqual(audit_row[2], "cand_202")  # candidate_id
        self.assertEqual(audit_row[3], "Siti Recruiter")  # actor
        self.assertEqual(audit_row[4], "interview_scorecard_recorded")  # event_type

        details = json.loads(audit_row[5])
        self.assertEqual(details["scorecard_id"], sc_id)
        self.assertEqual(details["role"], "recruiter")
        self.assertEqual(details["criterion_count"], 2)
        self.assertEqual(details["average_score"], 4.5)

        # Single scorecard lookup
        single_sc = interview_service.get_scorecard(self.db, sc_id)
        self.assertIsNotNone(single_sc)
        self.assertEqual(single_sc["id"], sc_id)

    def test_record_scorecard_validation_errors(self):
        # Missing job_id
        with self.assertRaises(ValueError):
            interview_service.record_scorecard(self.db, {
                "candidate_id": "c1",
                "reviewer": "Alice",
                "role": "recruiter",
                "overall_recommendation": "hire",
            })

        # Missing candidate_id
        with self.assertRaises(ValueError):
            interview_service.record_scorecard(self.db, {
                "job_id": "j1",
                "reviewer": "Alice",
                "role": "recruiter",
                "overall_recommendation": "hire",
            })

        # Missing reviewer
        with self.assertRaises(ValueError):
            interview_service.record_scorecard(self.db, {
                "job_id": "j1",
                "candidate_id": "c1",
                "role": "recruiter",
                "overall_recommendation": "hire",
            })

        # Missing role
        with self.assertRaises(ValueError):
            interview_service.record_scorecard(self.db, {
                "job_id": "j1",
                "candidate_id": "c1",
                "reviewer": "Alice",
                "overall_recommendation": "hire",
            })

        # Missing overall_recommendation
        with self.assertRaises(ValueError):
            interview_service.record_scorecard(self.db, {
                "job_id": "j1",
                "candidate_id": "c1",
                "reviewer": "Alice",
                "role": "recruiter",
            })

        # Invalid score: 0 (below 1)
        with self.assertRaises(ValueError):
            interview_service.record_scorecard(self.db, {
                "job_id": "j1",
                "candidate_id": "c1",
                "reviewer": "Alice",
                "role": "recruiter",
                "overall_recommendation": "hire",
                "criterion_scores": [
                    {"criterion_id": "crit_1", "score": 0}
                ]
            })

        # Invalid score: 6 (above 5)
        with self.assertRaises(ValueError):
            interview_service.record_scorecard(self.db, {
                "job_id": "j1",
                "candidate_id": "c1",
                "reviewer": "Alice",
                "role": "recruiter",
                "overall_recommendation": "hire",
                "criterion_scores": [
                    {"criterion_id": "crit_1", "score": 6}
                ]
            })

        # Non-numeric score
        with self.assertRaises(ValueError):
            interview_service.record_scorecard(self.db, {
                "job_id": "j1",
                "candidate_id": "c1",
                "reviewer": "Alice",
                "role": "recruiter",
                "overall_recommendation": "hire",
                "criterion_scores": [
                    {"criterion_id": "crit_1", "score": "bad_score"}
                ]
            })

    def test_summary_recruiter_vs_hiring_manager(self):
        cand_id = "cand_multi"
        job_id = "job_303"

        # 1. Recruiter submits scorecard
        interview_service.record_scorecard(self.db, {
            "job_id": job_id,
            "candidate_id": cand_id,
            "reviewer": "Rina Recruiter",
            "role": "Recruiter",  # tests case-insensitivity
            "overall_recommendation": "hire",
            "notes": "Good baseline culture and tech fit.",
            "scores": [
                {"criterion_id": "python", "criterion_label": "Python", "score": 3, "evidence_notes": "Meets basic expectations"},
                {"criterion_id": "fastapi", "criterion_label": "FastAPI", "score": 4, "evidence_notes": "Built several services"},
                {"criterion_id": "teamwork", "criterion_label": "Team Collaboration", "score": 5, "evidence_notes": "Great teamwork mindset"},
            ]
        })

        # Recruiter averages: (3 + 4 + 5) / 3 = 4.0

        # 2. Hiring Manager submits scorecard
        interview_service.record_scorecard(self.db, {
            "job_id": job_id,
            "candidate_id": cand_id,
            "reviewer": "Bambang Manager",
            "role": "hiring_manager",
            "overall_recommendation": "strong_hire",
            "notes": "Deep technical knowledge in distributed systems.",
            "scores": [
                {"criterion_id": "python", "criterion_label": "Python", "score": 4, "evidence_notes": "Strong concurrency understanding"},
                {"criterion_id": "fastapi", "criterion_label": "FastAPI", "score": 5, "evidence_notes": "Mastery in async endpoints and middleware"},
                {"criterion_id": "architecture", "criterion_label": "System Architecture", "score": 4, "evidence_notes": "Solid design trade-offs"},
            ]
        })

        # Hiring manager averages: (4 + 5 + 4) / 3 = 4.33

        summary = interview_service.get_candidate_interview_summary(self.db, cand_id)

        self.assertEqual(summary["candidate_id"], cand_id)
        self.assertEqual(summary["total_scorecards"], 2)
        self.assertEqual(summary["recruiter_average"], 4.0)
        self.assertEqual(summary["hiring_manager_average"], 4.33)
        self.assertEqual(summary["overall_average_score"], 4.17)

        # Check by_role breakdown
        self.assertEqual(summary["by_role"]["recruiter"]["scorecard_count"], 1)
        self.assertEqual(summary["by_role"]["recruiter"]["reviewers"], ["Rina Recruiter"])
        self.assertEqual(summary["by_role"]["recruiter"]["recommendations"], ["hire"])
        self.assertEqual(summary["by_role"]["recruiter"]["by_criterion"]["python"]["average_score"], 3.0)
        self.assertEqual(summary["by_role"]["recruiter"]["by_criterion"]["fastapi"]["average_score"], 4.0)
        self.assertEqual(summary["by_role"]["recruiter"]["by_criterion"]["teamwork"]["average_score"], 5.0)

        self.assertEqual(summary["by_role"]["hiring_manager"]["scorecard_count"], 1)
        self.assertEqual(summary["by_role"]["hiring_manager"]["reviewers"], ["Bambang Manager"])
        self.assertEqual(summary["by_role"]["hiring_manager"]["recommendations"], ["strong_hire"])
        self.assertEqual(summary["by_role"]["hiring_manager"]["by_criterion"]["python"]["average_score"], 4.0)
        self.assertEqual(summary["by_role"]["hiring_manager"]["by_criterion"]["fastapi"]["average_score"], 5.0)
        self.assertEqual(summary["by_role"]["hiring_manager"]["by_criterion"]["architecture"]["average_score"], 4.0)

        # Check by_criterion breakdown across roles
        # python: scores 3 and 4 -> avg = 3.5
        python_crit = summary["by_criterion"]["python"]
        self.assertEqual(python_crit["average_score"], 3.5)
        self.assertEqual(python_crit["count"], 2)
        self.assertEqual(python_crit["role_averages"]["recruiter"], 3.0)
        self.assertEqual(python_crit["role_averages"]["hiring_manager"], 4.0)

        # fastapi: scores 4 and 5 -> avg = 4.5
        fastapi_crit = summary["by_criterion"]["fastapi"]
        self.assertEqual(fastapi_crit["average_score"], 4.5)
        self.assertEqual(fastapi_crit["count"], 2)
        self.assertEqual(fastapi_crit["role_averages"]["recruiter"], 4.0)
        self.assertEqual(fastapi_crit["role_averages"]["hiring_manager"], 5.0)

    def test_empty_candidate_summary(self):
        summary = interview_service.get_candidate_interview_summary(self.db, "cand_non_existent")
        self.assertEqual(summary["candidate_id"], "cand_non_existent")
        self.assertEqual(summary["total_scorecards"], 0)
        self.assertIsNone(summary["overall_average_score"])
        self.assertIsNone(summary["recruiter_average"])
        self.assertIsNone(summary["hiring_manager_average"])
        self.assertEqual(summary["by_role"]["recruiter"]["scorecard_count"], 0)
        self.assertEqual(summary["by_role"]["hiring_manager"]["scorecard_count"], 0)
        self.assertEqual(summary["by_criterion"], {})
        self.assertEqual(summary["scorecards"], [])


if __name__ == "__main__":
    unittest.main()
