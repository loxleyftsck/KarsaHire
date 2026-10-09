"""Unit and integration tests for Recruitment Analytics & Governance Service."""

import json
import sqlite3
import unittest

import analytics_service


class TestRecruitmentAnalytics(unittest.TestCase):
    """Comprehensive test suite for analytics_service with in-memory SQLite fixtures."""

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

    def tearDown(self):
        self.db.close()

    # -------------------------------------------------------------------------
    # 1. Job Funnel Analysis
    # -------------------------------------------------------------------------
    def test_job_funnel_distribution_and_scores(self):
        """Test calculation of status distribution, percentages, and score aggregates."""
        job_id = "job_funnel_test"
        criteria = [{"id": "c1", "label": "Python", "type": "required", "weight": 2.0}]
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, "Backend Dev", "Engineering", "Desc", json.dumps(criteria), "criteria_approved", "2026-10-01T00:00:00Z"),
        )

        # Insert 4 candidates: 2 advance, 1 needs_info, 1 not_selected
        candidates_data = [
            ("cand_1", job_id, "pdf", "{}", 90.0, "advance", "2026-10-01T01:00:00Z"),
            ("cand_2", job_id, "pdf", "{}", 80.0, "advance", "2026-10-01T02:00:00Z"),
            ("cand_3", job_id, "docx", "{}", 60.0, "needs_info", "2026-10-01T03:00:00Z"),
            ("cand_4", job_id, "txt", "{}", 50.0, "not_selected", "2026-10-01T04:00:00Z"),
        ]
        self.db.executemany("INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)", candidates_data)
        self.db.commit()

        funnel = analytics_service.get_job_funnel(self.db, job_id)

        self.assertEqual(funnel["job_id"], job_id)
        self.assertEqual(funnel["total_candidates"], 4)
        self.assertEqual(funnel["status_distribution"]["advance"], 2)
        self.assertEqual(funnel["status_distribution"]["needs_info"], 1)
        self.assertEqual(funnel["status_distribution"]["not_selected"], 1)
        self.assertEqual(funnel["status_distribution"]["needs_review"], 0)

        # Percentages: advance = 50%, needs_info = 25%, not_selected = 25%
        self.assertEqual(funnel["status_percentages"]["advance"], 50.0)
        self.assertEqual(funnel["status_percentages"]["needs_info"], 25.0)
        self.assertEqual(funnel["status_percentages"]["not_selected"], 25.0)

        # Scores: (90 + 80 + 60 + 50) / 4 = 70.0
        self.assertEqual(funnel["avg_score"], 70.0)
        self.assertEqual(funnel["min_score"], 50.0)
        self.assertEqual(funnel["max_score"], 90.0)

    def test_job_funnel_empty_candidates(self):
        """Requisition with no candidates should report 0 counts and 0.0 scores."""
        job_id = "job_empty"
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, "Dev", "Eng", "Desc", "[]", "criteria_approved", "2026-10-01T00:00:00Z"),
        )
        self.db.commit()

        funnel = analytics_service.get_job_funnel(self.db, job_id)
        self.assertEqual(funnel["total_candidates"], 0)
        self.assertEqual(funnel["avg_score"], 0.0)
        self.assertEqual(funnel["min_score"], 0.0)
        self.assertEqual(funnel["max_score"], 0.0)
        self.assertEqual(funnel["status_distribution"]["needs_review"], 0)

    def test_job_funnel_invalid_job_id_raises_value_error(self):
        """Querying funnel for non-existent job must raise ValueError."""
        with self.assertRaises(ValueError):
            analytics_service.get_job_funnel(self.db, "job_does_not_exist")

    # -------------------------------------------------------------------------
    # 2. Inter-Rater Agreement & Consensus Analysis
    # -------------------------------------------------------------------------
    def test_inter_rater_agreement_full_consensus(self):
        """When recruiter and hiring manager make identical decisions, consensus is 100%."""
        job_id = "job_agree_100"
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, "Title", "Dept", "Desc", "[]", "criteria_approved", "2026-10-01T00:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("cand_agree_1", job_id, "pdf", "{}", 85.0, "advance", "2026-10-01T01:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("cand_agree_2", job_id, "pdf", "{}", 40.0, "not_selected", "2026-10-01T02:00:00Z"),
        )

        # Reviews for cand_agree_1: both 'advance'
        self.db.execute("INSERT INTO reviews VALUES ('r1', 'cand_agree_1', 'Alice', 'recruiter', 'advance', '', '2026-10-01T03:00:00Z')")
        self.db.execute("INSERT INTO reviews VALUES ('r2', 'cand_agree_1', 'Bob', 'hiring_manager', 'advance', '', '2026-10-01T04:00:00Z')")

        # Reviews for cand_agree_2: both 'not_selected'
        self.db.execute("INSERT INTO reviews VALUES ('r3', 'cand_agree_2', 'Alice', 'recruiter', 'not_selected', '', '2026-10-01T05:00:00Z')")
        self.db.execute("INSERT INTO reviews VALUES ('r4', 'cand_agree_2', 'Bob', 'hiring_manager', 'not_selected', '', '2026-10-01T06:00:00Z')")
        self.db.commit()

        agreement = analytics_service.get_inter_rater_agreement(self.db, job_id)
        self.assertEqual(agreement["job_id"], job_id)
        self.assertEqual(agreement["total_candidates"], 2)
        self.assertEqual(agreement["dual_reviewed_count"], 2)
        self.assertEqual(agreement["consensus_count"], 2)
        self.assertEqual(agreement["consensus_rate"], 100.0)
        self.assertEqual(agreement["divergent_count"], 0)
        self.assertEqual(len(agreement["divergent_candidates"]), 0)

    def test_inter_rater_agreement_with_divergence(self):
        """When recruiter and hiring manager differ, candidate is placed in divergence list."""
        job_id = "job_diverge"
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, "Title", "Dept", "Desc", "[]", "criteria_approved", "2026-10-01T00:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("cand_div", job_id, "pdf", "{}", 75.0, "advance", "2026-10-01T01:00:00Z"),
        )

        # Recruiter says 'advance', Hiring Manager says 'needs_info'
        self.db.execute("INSERT INTO reviews VALUES ('r1', 'cand_div', 'Siti', 'recruiter', 'advance', 'CV cocok', '2026-10-01T02:00:00Z')")
        self.db.execute("INSERT INTO reviews VALUES ('r2', 'cand_div', 'Joko', 'hiring_manager', 'needs_info', 'Perlu cek portofolio', '2026-10-01T03:00:00Z')")
        self.db.commit()

        agreement = analytics_service.get_inter_rater_agreement(self.db, job_id)
        self.assertEqual(agreement["dual_reviewed_count"], 1)
        self.assertEqual(agreement["consensus_count"], 0)
        self.assertEqual(agreement["consensus_rate"], 0.0)
        self.assertEqual(agreement["divergent_count"], 1)

        divergence = agreement["divergent_candidates"][0]
        self.assertEqual(divergence["candidate_id"], "cand_div")
        self.assertEqual(divergence["recruiter_decision"], "advance")
        self.assertEqual(divergence["hiring_manager_decision"], "needs_info")
        self.assertEqual(divergence["recruiter"], "Siti")
        self.assertEqual(divergence["hiring_manager"], "Joko")
        self.assertEqual(divergence["recruiter_note"], "CV cocok")
        self.assertEqual(divergence["hiring_manager_note"], "Perlu cek portofolio")

    def test_inter_rater_agreement_single_reviewer_only(self):
        """Candidates reviewed by only one role are not counted in dual-review consensus."""
        job_id = "job_single_rev"
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, "Title", "Dept", "Desc", "[]", "criteria_approved", "2026-10-01T00:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("cand_single", job_id, "pdf", "{}", 70.0, "needs_review", "2026-10-01T01:00:00Z"),
        )
        # Only recruiter reviewed
        self.db.execute("INSERT INTO reviews VALUES ('r1', 'cand_single', 'Alice', 'recruiter', 'advance', '', '2026-10-01T02:00:00Z')")
        self.db.commit()

        agreement = analytics_service.get_inter_rater_agreement(self.db, job_id)
        self.assertEqual(agreement["total_candidates"], 1)
        self.assertEqual(agreement["dual_reviewed_count"], 0)
        self.assertEqual(agreement["consensus_count"], 0)
        self.assertEqual(agreement["consensus_rate"], 0.0)
        self.assertEqual(agreement["divergent_count"], 0)

    # -------------------------------------------------------------------------
    # 3. Criteria Health & Bottleneck Diagnostics
    # -------------------------------------------------------------------------
    def test_criteria_health_bottleneck_detection(self):
        """Criterion with > 80% unknown matches is flagged as bottleneck."""
        job_id = "job_health_test"
        criteria = [
            {"id": "crit_strict", "label": "Rust Embedded", "type": "required", "weight": 2.0},
            {"id": "crit_common", "label": "Communication", "type": "preferred", "weight": 1.0},
            {"id": "crit_balanced", "label": "Python", "type": "required", "weight": 2.0},
        ]
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, "Systems Eng", "Eng", "Desc", json.dumps(criteria), "criteria_approved", "2026-10-01T00:00:00Z"),
        )

        # Create 10 candidates
        for i in range(1, 11):
            cid = f"cand_{i}"
            self.db.execute(
                "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cid, job_id, "pdf", "{}", 70.0, "needs_review", "2026-10-01T01:00:00Z"),
            )
            # Strict criterion: 9 unknown, 1 matched -> 90% unknown (Bottleneck!)
            res_strict = "matched" if i == 1 else "unknown"
            self.db.execute(
                "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"ev_s_{i}", cid, "crit_strict", "Rust Embedded", "required", 2.0, res_strict, 1.0, "...", 1),
            )

            # Common criterion: 10 matched out of 10 -> 100% matched (Too common!)
            self.db.execute(
                "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"ev_c_{i}", cid, "crit_common", "Communication", "preferred", 1.0, "matched", 1.0, "...", 1),
            )

            # Balanced criterion: 5 matched, 3 partial, 2 unknown -> Healthy
            res_bal = "matched" if i <= 5 else "partial" if i <= 8 else "unknown"
            self.db.execute(
                "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"ev_b_{i}", cid, "crit_balanced", "Python", "required", 2.0, res_bal, 1.0, "...", 1),
            )

        self.db.commit()

        health_list = analytics_service.get_criteria_health(self.db, job_id)
        self.assertEqual(len(health_list), 3)

        health_by_id = {item["criterion_id"]: item for item in health_list}

        # Check strict / bottleneck criterion
        strict_item = health_by_id["crit_strict"]
        self.assertEqual(strict_item["unknown_percentage"], 90.0)
        self.assertTrue(strict_item["is_bottleneck"])
        self.assertFalse(strict_item["is_too_common"])
        self.assertEqual(strict_item["health_status"], "bottleneck")

        # Check too common criterion
        common_item = health_by_id["crit_common"]
        self.assertEqual(common_item["matched_percentage"], 100.0)
        self.assertFalse(common_item["is_bottleneck"])
        self.assertTrue(common_item["is_too_common"])
        self.assertEqual(common_item["health_status"], "too_common")

        # Check balanced / healthy criterion
        bal_item = health_by_id["crit_balanced"]
        self.assertEqual(bal_item["matched_percentage"], 50.0)
        self.assertEqual(bal_item["partial_percentage"], 30.0)
        self.assertEqual(bal_item["unknown_percentage"], 20.0)
        self.assertFalse(bal_item["is_bottleneck"])
        self.assertFalse(bal_item["is_too_common"])
        self.assertEqual(bal_item["health_status"], "healthy")

    def test_criteria_health_zero_evaluations(self):
        """Criterion with 0 evaluations defaults gracefully to 0.0% and healthy status."""
        job_id = "job_no_evi"
        criteria = [{"id": "c1", "label": "Go", "type": "required", "weight": 2.0}]
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, "Title", "Dept", "Desc", json.dumps(criteria), "criteria_approved", "2026-10-01T00:00:00Z"),
        )
        self.db.commit()

        health = analytics_service.get_criteria_health(self.db, job_id)
        self.assertEqual(len(health), 1)
        self.assertEqual(health[0]["total_evaluated"], 0)
        self.assertEqual(health[0]["matched_percentage"], 0.0)
        self.assertEqual(health[0]["partial_percentage"], 0.0)
        self.assertEqual(health[0]["unknown_percentage"], 0.0)
        self.assertFalse(health[0]["is_bottleneck"])
        self.assertFalse(health[0]["is_too_common"])

    # -------------------------------------------------------------------------
    # 4. Consolidated Summary
    # -------------------------------------------------------------------------
    def test_hiring_analytics_summary_bundle(self):
        """get_hiring_analytics_summary bundles funnel, agreement, and criteria health."""
        job_id = "job_summary_test"
        criteria = [{"id": "c1", "label": "SQL", "type": "required", "weight": 2.0}]
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, "Data Eng", "Data", "Desc", json.dumps(criteria), "criteria_approved", "2026-10-01T00:00:00Z"),
        )
        self.db.commit()

        summary = analytics_service.get_hiring_analytics_summary(self.db, job_id)
        self.assertIn("job_id", summary)
        self.assertIn("funnel", summary)
        self.assertIn("inter_rater_agreement", summary)
        self.assertIn("criteria_health", summary)
        self.assertIn("evidence_grounding", summary)
        self.assertIn("ranking_quality", summary)
        self.assertIn("fairness_audit", summary)
        self.assertIn("academic_performance_summary", summary)

    # -------------------------------------------------------------------------
    # 5. Academic & Industry Performance Metrics Tests
    # -------------------------------------------------------------------------
    def test_calculate_cohens_kappa_values(self):
        """Test Cohen's Kappa calculation on perfect, substantial, and empty agreement."""
        # Perfect agreement
        res_perfect = analytics_service.calculate_cohens_kappa(
            ["advance", "not_selected", "advance"],
            ["advance", "not_selected", "advance"],
        )
        self.assertEqual(res_perfect["kappa"], 1.0)
        self.assertIn("Hampir Sempurna", res_perfect["interpretation"])

        # Substantial / moderate agreement
        res_sub = analytics_service.calculate_cohens_kappa(
            ["advance", "advance", "not_selected", "needs_info"],
            ["advance", "advance", "not_selected", "not_selected"],
        )
        self.assertGreater(res_sub["kappa"], 0.5)
        self.assertLess(res_sub["kappa"], 1.0)

        # Empty data
        res_empty = analytics_service.calculate_cohens_kappa([], [])
        self.assertEqual(res_empty["kappa"], 0.0)

    def test_evidence_grounding_audit_faithfulness(self):
        """Test faithfulness and attribution metrics on evidence table records."""
        job_id = "job_grounding_test"
        self.db.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)", (job_id, "Title", "Dept", "Desc", "[]", "criteria_approved", "2026-10-01T00:00:00Z"))
        self.db.execute("INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)", ("c1", job_id, "pdf", "{}", 80.0, "needs_review", "2026-10-01T00:00:00Z"))

        # Insert 2 positive evidence with snippets and page numbers, and 1 unknown
        self.db.execute("INSERT INTO evidence VALUES ('e1', 'c1', 'crit1', 'Python', 'required', 1.0, 'matched', 1.0, 'Proficient in Python', 1)")
        self.db.execute("INSERT INTO evidence VALUES ('e2', 'c1', 'crit2', 'SQL', 'required', 1.0, 'partial', 0.5, 'Basic SQL knowledge', 2)")
        self.db.execute("INSERT INTO evidence VALUES ('e3', 'c1', 'crit3', 'Docker', 'required', 1.0, 'unknown', 0.0, '', NULL)")
        self.db.commit()

        audit = analytics_service.get_evidence_grounding_audit(self.db, job_id)
        self.assertEqual(audit["total_criteria_evaluations"], 3)
        self.assertEqual(audit["positive_matches_count"], 2)
        self.assertEqual(audit["grounded_matches_count"], 2)
        self.assertEqual(audit["faithfulness_score"], 100.0)
        self.assertEqual(audit["hallucination_rate"], 0.0)
        self.assertEqual(audit["attribution_precision"], 100.0)

    def test_ranking_quality_metrics_ndcg_and_mrr(self):
        """Test NDCG@K and MRR metrics comparing AI scores with human decisions."""
        job_id = "job_ranking_test"
        self.db.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)", (job_id, "Title", "Dept", "Desc", "[]", "criteria_approved", "2026-10-01T00:00:00Z"))

        # Candidate 1: Score 90.0, Decision 'advance' (rel=2)
        # Candidate 2: Score 80.0, Decision 'needs_info' (rel=1)
        # Candidate 3: Score 50.0, Decision 'not_selected' (rel=0)
        self.db.execute("INSERT INTO candidates VALUES ('c1', ?, 'pdf', '{}', 90.0, 'advance', '2026-10-01T00:00:00Z')", (job_id,))
        self.db.execute("INSERT INTO candidates VALUES ('c2', ?, 'pdf', '{}', 80.0, 'needs_info', '2026-10-01T00:00:00Z')", (job_id,))
        self.db.execute("INSERT INTO candidates VALUES ('c3', ?, 'pdf', '{}', 50.0, 'not_selected', '2026-10-01T00:00:00Z')", (job_id,))

        self.db.execute("INSERT INTO reviews VALUES ('r1', 'c1', 'Alice', 'recruiter', 'advance', '', '2026-10-01T01:00:00Z')")
        self.db.execute("INSERT INTO reviews VALUES ('r2', 'c2', 'Alice', 'recruiter', 'needs_info', '', '2026-10-01T02:00:00Z')")
        self.db.execute("INSERT INTO reviews VALUES ('r3', 'c3', 'Alice', 'recruiter', 'not_selected', '', '2026-10-01T03:00:00Z')")
        self.db.commit()

        ranking = analytics_service.get_ranking_quality_metrics(self.db, job_id, k_list=[3, 5])
        self.assertTrue(ranking["has_ground_truth"])
        self.assertEqual(ranking["total_candidates"], 3)
        # Perfectly sorted: score 90 (rel=2), 80 (rel=1), 50 (rel=0) -> NDCG = 1.0
        self.assertEqual(ranking["ndcg"]["ndcg_3"], 1.0)
        # First relevant candidate is at rank 1 -> MRR = 1.0
        self.assertEqual(ranking["mrr"], 1.0)
        # Precision@3: 2 out of 3 are relevant (rel >= 1) -> 2/3 = 0.667
        self.assertAlmostEqual(ranking["precision_at_k"]["p_3"], 0.667, places=2)

    def test_fairness_audit_metrics(self):
        """Test fairness audit metrics and PII compliance checking."""
        job_id = "job_fairness_test"
        self.db.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)", (job_id, "Title", "Dept", "Desc", "[]", "criteria_approved", "2026-10-01T00:00:00Z"))
        self.db.execute("INSERT INTO candidates VALUES ('c1', ?, 'pdf', '{}', 75.0, 'advance', '2026-10-01T00:00:00Z')", (job_id,))
        self.db.execute("INSERT INTO evidence VALUES ('e1', 'c1', 'crit1', 'Python', 'required', 1.0, 'matched', 1.0, 'Contact [email removed] for code', 1)")
        self.db.commit()

        fairness = analytics_service.get_fairness_audit_metrics(self.db, job_id)
        self.assertEqual(fairness["total_candidates"], 1)
        self.assertEqual(fairness["pii_compliance_rate"], 100.0)
        self.assertIn("COMPLIANT", fairness["pii_audit_status"])
        self.assertTrue(fairness["blind_review_supported"])


if __name__ == "__main__":
    unittest.main()
