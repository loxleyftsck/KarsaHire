"""Unit tests for evaluate_synthetic.py benchmark runner."""

import json
from pathlib import Path
import unittest

import evaluate_synthetic


class TestEvaluateSynthetic(unittest.TestCase):
    """Test suite verifying synthetic CV evaluation and metrics aggregation."""

    def test_discover_samples(self):
        samples = evaluate_synthetic.discover_samples(evaluate_synthetic.DEFAULT_DATA_DIR)
        self.assertEqual(len(samples), 32)
        self.assertIn("r00003", samples)
        self.assertIn("r00420", samples)

    def test_build_criteria_for_position(self):
        criteria = evaluate_synthetic.build_criteria_for_position(["Python", "SQL"])
        self.assertEqual(len(criteria), 2)
        self.assertEqual(criteria[0]["label"], "Python")
        self.assertEqual(criteria[0]["weight"], 1.0)
        self.assertEqual(criteria[0]["type"], "required")

    def test_benchmark_run_and_report_generation(self):
        temp_output = evaluate_synthetic.ROOT_DIR / "data" / "test_eval_report.json"
        try:
            report = evaluate_synthetic.evaluate_synthetic_dataset(output_path=temp_output)
            self.assertEqual(report["metadata"]["total_samples"], 32)
            self.assertEqual(report["profile_extraction_metrics"]["candidates_with_skills_count"], 32)
            self.assertEqual(report["profile_extraction_metrics"]["candidates_with_skills_percentage"], 100.0)

            # Check positions present in report
            pos_dist = report["position_matching_distribution"]
            self.assertIn("Software Developer", pos_dist)
            self.assertIn("Network & Systems Administrator", pos_dist)
            self.assertIn("Accountant", pos_dist)

            # Check top 10 skills
            top_10 = report["profile_extraction_metrics"]["top_10_skills"]
            self.assertEqual(len(top_10), 10)

            # Verify saved file exists and matches
            self.assertTrue(temp_output.is_file())
            loaded = json.loads(temp_output.read_text(encoding="utf-8"))
            self.assertEqual(loaded["metadata"]["total_samples"], 32)
        finally:
            if temp_output.is_file():
                temp_output.unlink()


if __name__ == "__main__":
    unittest.main()
