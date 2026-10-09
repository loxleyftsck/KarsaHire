"""Unit and integration tests for Data Export & Audit Service."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import unittest
from pathlib import Path

import export_service


class TestExportService(unittest.TestCase):
    """Isolated test suite for export_service using in-memory SQLite fixtures."""

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

        # Seed sample job data
        self.job_id = "job_test_001"
        self.criteria = [
            {"id": "crit_1", "label": "Python", "type": "required", "weight": 2.0},
            {"id": "crit_2", "label": "Docker", "type": "preferred", "weight": 1.0},
        ]
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.job_id,
                "Senior Software Engineer",
                "Backend",
                "Scalable backend systems",
                json.dumps(self.criteria),
                "criteria_approved",
                "2026-09-01T00:00:00Z",
            ),
        )

        # Approvals
        self.db.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?)",
            ("apr_1", self.job_id, "Budi Recruiter", "recruiter", "2026-09-01T01:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?)",
            ("apr_2", self.job_id, "Dewi Manager", "hiring_manager", "2026-09-01T02:00:00Z"),
        )

        # Candidate 1: Dual reviews and evidence
        self.cand_1_id = "cand_001"
        profile_1 = {
            "skills": ["Python", "FastAPI"],
            "experience_years_mentioned": 5,
            "education_levels_mentioned": ["Bachelor's"],
        }
        self.db.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self.cand_1_id, self.job_id, "pdf", json.dumps(profile_1), 92.0, "advance", "2026-09-02T00:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ev_1", self.cand_1_id, "crit_1", "Python", "required", 2.0, "matched", 1.0, "Python developer 5 years", 1),
        )
        self.db.execute(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ev_2", self.cand_1_id, "crit_2", "Docker", "preferred", 1.0, "partial", 0.5, "Used docker containers", 2),
        )
        self.db.execute(
            "INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rev_1", self.cand_1_id, "Budi Recruiter", "recruiter", "advance", "Passed initial screen", "2026-09-02T10:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rev_2", self.cand_1_id, "Dewi Manager", "hiring_manager", "advance", "Impressive project history", "2026-09-02T11:00:00Z"),
        )

        # Candidate 2: No reviews, single evidence with None page_number
        self.cand_2_id = "cand_002"
        profile_2 = {
            "skills": ["Python"],
            "experience_years_mentioned": None,
            "education_levels_mentioned": [],
        }
        self.db.execute(
            "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self.cand_2_id, self.job_id, "docx", json.dumps(profile_2), 65.0, "needs_review", "2026-09-02T01:00:00Z"),
        )
        self.db.execute(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ev_3", self.cand_2_id, "crit_1", "Python", "required", 2.0, "matched", 1.0, "Junior Python dev", None),
        )

        # Audit events
        self.db.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "evt_1",
                self.job_id,
                self.cand_1_id,
                "Dewi Manager",
                "human_review_recorded",
                json.dumps({"role": "hiring_manager", "decision": "advance"}),
                "2026-09-02T11:00:00Z",
            ),
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_export_candidates_csv_structure_and_values(self):
        """Candidates CSV should include expected headers, scores, profiles, and combined reviewer notes."""
        csv_data = export_service.export_candidates_csv(self.db, self.job_id)
        rows = list(csv.reader(io.StringIO(csv_data)))

        expected_headers = [
            "candidate_id",
            "file_type",
            "score",
            "status",
            "skills",
            "experience_years",
            "education",
            "reviewer_decision",
            "reviewer_notes",
            "created_at",
        ]
        self.assertEqual(rows[0], expected_headers)
        self.assertEqual(len(rows), 3)  # header + 2 candidates

        # Row 1 corresponds to cand_001 (score 92.0 > 65.0)
        row_1 = rows[1]
        self.assertEqual(row_1[0], "cand_001")
        self.assertEqual(row_1[1], "pdf")
        self.assertEqual(float(row_1[2]), 92.0)
        self.assertEqual(row_1[3], "advance")
        self.assertEqual(row_1[4], "Python, FastAPI")
        self.assertEqual(row_1[5], "5")
        self.assertEqual(row_1[6], "Bachelor's")
        self.assertEqual(row_1[7], "advance")
        self.assertIn("Impressive project history", row_1[8])
        self.assertIn("Passed initial screen", row_1[8])
        self.assertIn(" | ", row_1[8])  # Notes joined by pipeline
        self.assertEqual(row_1[9], "2026-09-02T00:00:00Z")

        # Row 2 corresponds to cand_002 (no reviews)
        row_2 = rows[2]
        self.assertEqual(row_2[0], "cand_002")
        self.assertEqual(row_2[1], "docx")
        self.assertEqual(float(row_2[2]), 65.0)
        self.assertEqual(row_2[3], "needs_review")
        self.assertEqual(row_2[4], "Python")
        self.assertEqual(row_2[5], "")  # None experience
        self.assertEqual(row_2[6], "")  # Empty education
        self.assertEqual(row_2[7], "")  # No review decision, status is needs_review
        self.assertEqual(row_2[8], "")  # No review notes

    def test_export_evidence_csv_structure_and_values(self):
        """Evidence CSV should include expected headers, criteria, weights, results, and page numbers."""
        csv_data = export_service.export_evidence_csv(self.db, self.job_id)
        rows = list(csv.reader(io.StringIO(csv_data)))

        expected_headers = [
            "candidate_id",
            "criterion",
            "requirement_type",
            "weight",
            "result",
            "confidence",
            "snippet",
            "page_number",
        ]
        self.assertEqual(rows[0], expected_headers)
        self.assertEqual(len(rows), 4)  # header + 3 evidence records

        # Verify cand_001 evidence rows
        row_1 = rows[1]
        self.assertEqual(row_1[0], "cand_001")
        self.assertEqual(row_1[1], "Python")
        self.assertEqual(row_1[2], "required")
        self.assertEqual(float(row_1[3]), 2.0)
        self.assertEqual(row_1[4], "matched")
        self.assertEqual(float(row_1[5]), 1.0)
        self.assertEqual(row_1[6], "Python developer 5 years")
        self.assertEqual(row_1[7], "1")

        row_2 = rows[2]
        self.assertEqual(row_2[0], "cand_001")
        self.assertEqual(row_2[1], "Docker")
        self.assertEqual(row_2[2], "preferred")
        self.assertEqual(float(row_2[3]), 1.0)
        self.assertEqual(row_2[4], "partial")
        self.assertEqual(float(row_2[5]), 0.5)
        self.assertEqual(row_2[6], "Used docker containers")
        self.assertEqual(row_2[7], "2")

        # Verify cand_002 evidence row with None page_number
        row_3 = rows[3]
        self.assertEqual(row_3[0], "cand_002")
        self.assertEqual(row_3[1], "Python")
        self.assertEqual(row_3[7], "")  # None page_number becomes empty string

    def test_export_job_report_json_comprehensive(self):
        """Job report JSON should contain full metadata, criteria, approvers, candidates, and audit events."""
        report = export_service.export_job_report_json(self.db, self.job_id)
        self.assertIsInstance(report, dict)

        # Metadata
        self.assertEqual(report["job_id"], self.job_id)
        self.assertEqual(report["id"], self.job_id)
        self.assertEqual(report["title"], "Senior Software Engineer")
        self.assertEqual(report["department"], "Backend")
        self.assertEqual(report["status"], "criteria_approved")

        # Criteria & Approvers
        self.assertEqual(len(report["criteria"]), 2)
        self.assertEqual(report["approvers"]["recruiter"], "Budi Recruiter")
        self.assertEqual(report["approvers"]["hiring_manager"], "Dewi Manager")

        # Candidates with nested evidence and reviews
        self.assertEqual(report["candidate_count"], 2)
        cands = report["candidates"]
        self.assertEqual(len(cands), 2)

        c1 = cands[0]
        self.assertEqual(c1["candidate_id"], "cand_001")
        self.assertEqual(len(c1["evidence"]), 2)
        self.assertEqual(len(c1["reviews"]), 2)
        self.assertEqual(c1["reviews"][0]["reviewer"], "Dewi Manager")  # Most recent first

        c2 = cands[1]
        self.assertEqual(c2["candidate_id"], "cand_002")
        self.assertEqual(len(c2["evidence"]), 1)
        self.assertEqual(len(c2["reviews"]), 0)

        # Audit events
        self.assertEqual(report["audit_event_count"], 1)
        self.assertEqual(report["audit_events"][0]["actor"], "Dewi Manager")
        self.assertEqual(report["audit_events"][0]["event_type"], "human_review_recorded")

        # Must be fully JSON serializable
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertGreater(len(serialized), 0)

    def test_export_empty_job_scenarios(self):
        """Exporting for a job with zero candidates should yield clean empty sets."""
        empty_job_id = "job_empty_002"
        self.db.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (empty_job_id, "Product Manager", "Product", "", "[]", "awaiting_approval", "2026-09-01T00:00:00Z"),
        )
        self.db.commit()

        # Candidates CSV has only header row
        c_csv = export_service.export_candidates_csv(self.db, empty_job_id)
        c_rows = list(csv.reader(io.StringIO(c_csv)))
        self.assertEqual(len(c_rows), 1)

        # Evidence CSV has only header row
        e_csv = export_service.export_evidence_csv(self.db, empty_job_id)
        e_rows = list(csv.reader(io.StringIO(e_csv)))
        self.assertEqual(len(e_rows), 1)

        # JSON report has 0 candidates and 0 audit events
        report = export_service.export_job_report_json(self.db, empty_job_id)
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["candidates"], [])
        self.assertEqual(report["audit_event_count"], 0)
        self.assertEqual(report["audit_events"], [])

    def test_nonexistent_job_raises_value_error(self):
        """All export functions must raise ValueError when job ID does not exist."""
        invalid_id = "non_existent_job_999"
        with self.assertRaises(ValueError):
            export_service.export_candidates_csv(self.db, invalid_id)

        with self.assertRaises(ValueError):
            export_service.export_evidence_csv(self.db, invalid_id)

        with self.assertRaises(ValueError):
            export_service.export_job_report_json(self.db, invalid_id)

    def test_verify_exports_on_copilot_sqlite_if_exists(self):
        """If data/copilot.sqlite3 exists, verify_exports helper runs without errors."""
        db_path = Path("data/copilot.sqlite3")
        if not db_path.exists():
            self.skipTest("data/copilot.sqlite3 does not exist")

        conn = sqlite3.connect(db_path)
        try:
            job = conn.execute("SELECT id FROM jobs LIMIT 1").fetchone()
            if not job:
                self.skipTest("No jobs in data/copilot.sqlite3")
        finally:
            conn.close()

        result = export_service.verify_exports(db_path)
        self.assertEqual(result["status"], "OK")
        self.assertIn("job_id", result)
        self.assertIn("candidate_csv_rows", result)
        self.assertIn("evidence_csv_rows", result)


if __name__ == "__main__":
    unittest.main()
