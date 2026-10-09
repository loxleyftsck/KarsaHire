"""Unit and integration tests for enterprise benchmark runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.benchmark_enterprise_corpus import (
    POSITION_TEMPLATES,
    percentile,
    run_enterprise_benchmark,
)


class TestEnterpriseBenchmark(unittest.TestCase):
    def test_percentile_calculation(self) -> None:
        data = [10.0, 20.0, 30.0, 40.0, 50.0]
        self.assertEqual(percentile(data, 0), 10.0)
        self.assertEqual(percentile(data, 50), 30.0)
        self.assertEqual(percentile(data, 100), 50.0)
        self.assertEqual(percentile([], 50), 0.0)

    def test_run_enterprise_benchmark_small_sample(self) -> None:
        # Create a small temporary CSV with realistic sample rows
        sample_csv_content = (
            "ID,Resume_str,Resume_html,Category\n"
            "c1,\"Experienced Software Engineer proficient in Python, SQL, REST API, Git, and automated testing.\",<html/>,INFORMATION-TECHNOLOGY\n"
            "c2,\"Senior Accountant with expertise in General ledger, accounts payable, bank reconciliation, and month-end close.\",<html/>,ACCOUNTANT\n"
            "c3,\"HR Specialist experienced in talent sourcing, screening candidates, structured interviewing, and employee relations.\",<html/>,HR\n"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_csv = Path(tmpdir) / "test_resumes.csv"
            tmp_csv.write_text(sample_csv_content, encoding="utf-8")
            tmp_output = Path(tmpdir) / "test_report.json"

            report = run_enterprise_benchmark(
                csv_path=tmp_csv,
                limit=3,
                output_path=tmp_output,
            )

            self.assertTrue(tmp_output.is_file())
            self.assertEqual(report["metadata"]["total_evaluated"], 3)
            self.assertEqual(report["coverage_metrics"]["total_candidates"], 3)
            self.assertGreater(report["coverage_metrics"]["skills_detected_count"], 0)

            # Check discriminatory scoring on small sample
            alignment = report["cross_domain_alignment_matrix"]
            self.assertIn("INFORMATION-TECHNOLOGY", alignment)
            self.assertIn("ACCOUNTANT", alignment)
            self.assertIn("HR", alignment)

            # Accountant should score highest on Accountant position
            acc_score_on_acc = alignment["ACCOUNTANT"]["Accountant & Financial Analyst"]
            acc_score_on_sd = alignment["ACCOUNTANT"]["Software Developer"]
            self.assertGreater(acc_score_on_acc, acc_score_on_sd)

            # IT should score highest on Software Dev
            it_score_on_sd = alignment["INFORMATION-TECHNOLOGY"]["Software Developer"]
            it_score_on_acc = alignment["INFORMATION-TECHNOLOGY"]["Accountant & Financial Analyst"]
            self.assertGreater(it_score_on_sd, it_score_on_acc)


if __name__ == "__main__":
    unittest.main()
