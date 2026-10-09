"""Unit and regression test suite for academic and scientific evaluation metrics.

Tests evaluate_academic_metrics.py functions in full isolation without external dependencies:
1. Information Retrieval Ranking metrics (DCG, NDCG@K, MRR).
2. Faithfulness, Groundedness, and Attribution Precision metrics.
3. Counterfactual Fairness & Demographic Invariance tests (Delta Score == 0.0).
4. End-to-end evaluation runner with in-memory / temporary mock datasets.
"""

from __future__ import annotations

import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import matching
from scripts.evaluate_academic_metrics import (
    COUNTERFACTUAL_INJECTIONS,
    REQUISITION_TEMPLATES,
    calculate_dcg,
    calculate_ndcg,
    calculate_reciprocal_rank,
    evaluate_academic_metrics,
    print_executive_summary,
)


class TestInformationRetrievalMetrics(unittest.TestCase):
    """Test Information Retrieval (IR) ranking metrics: DCG, NDCG, MRR."""

    def test_calculate_dcg_known_values(self) -> None:
        """DCG calculates standard discounted cumulative gain correctly."""
        # Single element at rank 1: (2^2 - 1) / log2(2) = 3.0 / 1.0 = 3.0
        self.assertAlmostEqual(calculate_dcg([2.0], k=1), 3.0, places=4)

        # Two elements: rank 1 rel=2.0 (3.0), rank 2 rel=1.0 ((2^1 - 1) / log2(3) = 1.0 / 1.58496 = 0.6309)
        expected_2 = 3.0 + (1.0 / math.log2(3))
        self.assertAlmostEqual(calculate_dcg([2.0, 1.0], k=2), expected_2, places=4)

        # Truncation at k: elements past k must not affect result
        self.assertAlmostEqual(
            calculate_dcg([2.0, 1.0, 3.0, 4.0], k=2),
            calculate_dcg([2.0, 1.0], k=2),
            places=4,
        )

        # Zero relevances return 0.0
        self.assertEqual(calculate_dcg([0.0, 0.0, 0.0], k=3), 0.0)
        self.assertEqual(calculate_dcg([], k=5), 0.0)

    def test_calculate_ndcg_perfect_ranking(self) -> None:
        """NDCG of a perfectly ordered ranking must be 1.0."""
        relevances = [2.0, 2.0, 1.0, 0.0, 0.0]
        ideal = [2.0, 2.0, 1.0, 0.0, 0.0]

        ndcg_5 = calculate_ndcg(relevances, ideal, k=5)
        self.assertEqual(ndcg_5, 1.0)

        ndcg_3 = calculate_ndcg(relevances, ideal, k=3)
        self.assertEqual(ndcg_3, 1.0)

    def test_calculate_ndcg_suboptimal_and_reversed_ranking(self) -> None:
        """NDCG of suboptimal or reversed ranking must be strictly between 0.0 and 1.0."""
        ranked = [0.0, 0.0, 1.0, 2.0, 2.0]
        ideal = [2.0, 2.0, 1.0, 0.0, 0.0]

        ndcg_5 = calculate_ndcg(ranked, ideal, k=5)
        self.assertGreater(ndcg_5, 0.0)
        self.assertLess(ndcg_5, 1.0)

        # Better ranking must produce higher NDCG than worse ranking
        better_ranked = [2.0, 1.0, 2.0, 0.0, 0.0]
        ndcg_better = calculate_ndcg(better_ranked, ideal, k=5)
        self.assertGreater(ndcg_better, ndcg_5)

    def test_calculate_ndcg_edge_cases(self) -> None:
        """Edge cases: empty lists, zero IDCG, and out-of-range k."""
        # Empty relevances
        self.assertEqual(calculate_ndcg([], [], k=5), 0.0)

        # All relevances zero (IDCG <= 0)
        self.assertEqual(calculate_ndcg([0.0, 0.0], [0.0, 0.0], k=5), 0.0)

        # k larger than available candidates
        ranked = [2.0, 1.0]
        ideal = [2.0, 1.0]
        self.assertEqual(calculate_ndcg(ranked, ideal, k=100), 1.0)

    def test_calculate_reciprocal_rank(self) -> None:
        """MRR calculates reciprocal rank based on first relevant item."""
        # First item relevant (rank 1) -> 1/1 = 1.0
        self.assertEqual(calculate_reciprocal_rank([2.0, 0.0, 0.0]), 1.0)

        # Second item relevant (rank 2) -> 1/2 = 0.5
        self.assertEqual(calculate_reciprocal_rank([0.0, 1.0, 0.0]), 0.5)

        # Third item relevant (rank 3) -> 1/3 ~ 0.3333
        self.assertAlmostEqual(calculate_reciprocal_rank([0.0, 0.0, 1.0]), 0.3333, places=4)

        # No item relevant -> 0.0
        self.assertEqual(calculate_reciprocal_rank([0.0, 0.0, 0.0]), 0.0)
        self.assertEqual(calculate_reciprocal_rank([]), 0.0)

        # Custom threshold testing
        self.assertEqual(calculate_reciprocal_rank([1.0, 2.0, 0.0], threshold=2.0), 0.5)
        self.assertEqual(calculate_reciprocal_rank([1.0, 1.0, 0.0], threshold=2.0), 0.0)


class TestFaithfulnessAndGroundedness(unittest.TestCase):
    """Test evidence groundedness, faithfulness score, and anti-hallucination guarantees."""

    def setUp(self) -> None:
        self.criteria = [
            {"id": "c1", "label": "Python", "weight": 1.0, "type": "required"},
            {"id": "c2", "label": "SQL", "weight": 1.0, "type": "required"},
            {"id": "c3", "label": "Kubernetes", "weight": 1.0, "type": "preferred"},
        ]

    def test_verbatim_evidence_grounding_guarantee(self) -> None:
        """KarsaHire lexical matcher provides 100% faithful and traceable snippets."""
        doc_lines = [
            (1, "Senior Backend Engineer with 5+ years of experience."),
            (2, "Strong expertise in Python programming and microservices."),
            (3, "Designed relational database schemas using PostgreSQL and SQL queries."),
            (4, "Education: Bachelor of Science in Computer Science."),
        ]

        score, evidence_rows = matching.score_candidate(self.criteria, doc_lines)
        self.assertGreater(score, 0.0)

        matched_rows = [r for r in evidence_rows if r["result"] in ("matched", "partial")]
        self.assertGreater(len(matched_rows), 0)

        for row in matched_rows:
            snippet = row["snippet"]
            page_num = row["page_number"]

            # Grounding check 1: Snippet must not be empty or generic hallucination
            self.assertTrue(snippet and len(snippet) > 0)

            # Grounding check 2: Page/line number must be valid
            self.assertIsNotNone(page_num)
            self.assertTrue(1 <= page_num <= len(doc_lines))

            # Grounding check 3: Snippet must match the verbatim source line after redaction
            original_line = doc_lines[page_num - 1][1]
            expected_snippet = matching.redact_for_evidence(original_line)
            self.assertEqual(snippet, expected_snippet)

    def test_zero_hallucination_on_unmatched_criteria(self) -> None:
        """Unknown/unmatched criteria must have empty snippet and no fabricated citations."""
        doc_lines = [
            (1, "Accountant specializing in general ledger and tax reconciliation."),
        ]

        _, evidence_rows = matching.score_candidate(self.criteria, doc_lines)
        unknown_rows = [r for r in evidence_rows if r["result"] == "unknown"]
        self.assertEqual(len(unknown_rows), 3)

        for row in unknown_rows:
            self.assertEqual(row["snippet"], "")
            self.assertIsNone(row["page_number"])
            self.assertEqual(row["confidence"], 0.0)


class TestCounterfactualFairness(unittest.TestCase):
    """Test Counterfactual Fairness & Demographic Invariance (Delta Score == 0.0)."""

    def setUp(self) -> None:
        self.base_cv_text = (
            "Professional Summary:\n"
            "Software engineer with 6 years experience in Python, SQL, REST API, Git, and automated testing.\n"
            "Demonstrated proficiency in building scalable backend services and distributed systems.\n"
            "Education: Bachelor of Science in Computer Science.\n"
        )
        self.base_lines = [(i + 1, line) for i, line in enumerate(self.base_cv_text.splitlines()) if line.strip()]

    def test_counterfactual_name_swap_western(self) -> None:
        """Perturbing Western names (Male vs Female) produces Delta Score = 0.0."""
        cfg = REQUISITION_TEMPLATES["Software Developer"]
        base_score, _ = matching.score_candidate(cfg["criteria"], self.base_lines)

        western_variants = [
            "John Doe\nEmail: john.doe@example.com\n",
            "Jane Doe\nEmail: jane.doe@example.com\n",
            "Michael Brown\nEmail: michael.brown@example.com\n",
            "Sarah Smith\nEmail: sarah.smith@example.com\n",
        ]

        for variant in western_variants:
            pert_text = variant + self.base_cv_text
            pert_lines = [(i + 1, l.strip()) for i, l in enumerate(pert_text.splitlines()) if l.strip()]
            pert_score, _ = matching.score_candidate(cfg["criteria"], pert_lines)

            delta = abs(pert_score - base_score)
            self.assertEqual(delta, 0.0, f"Score changed by {delta} for variant: {variant.strip()}")

    def test_counterfactual_name_swap_indonesian(self) -> None:
        """Perturbing Indonesian names (Male vs Female) produces Delta Score = 0.0."""
        cfg = REQUISITION_TEMPLATES["Software Developer"]
        base_score, _ = matching.score_candidate(cfg["criteria"], self.base_lines)

        indonesian_variants = [
            "Budi Santoso\nNama Lengkap: Budi Santoso\n",
            "Siti Rahmawati\nNama Lengkap: Siti Rahmawati\n",
            "Ahmad Fauzi\nNama Lengkap: Ahmad Fauzi\n",
            "Dewi Lestari\nNama Lengkap: Dewi Lestari\n",
        ]

        for variant in indonesian_variants:
            pert_text = variant + self.base_cv_text
            pert_lines = [(i + 1, l.strip()) for i, l in enumerate(pert_text.splitlines()) if l.strip()]
            pert_score, _ = matching.score_candidate(cfg["criteria"], pert_lines)

            delta = abs(pert_score - base_score)
            self.assertEqual(delta, 0.0, f"Score changed by {delta} for variant: {variant.strip()}")

    def test_counterfactual_demographic_metadata_invariance(self) -> None:
        """Injecting non-job demographic metadata (age, religion, marital, ethnicity) yields Delta = 0.0."""
        demographic_variants = [
            "Gender: Female / Wanita\nPronouns: She/Her\n",
            "Gender: Male / Pria\nPronouns: He/Him\n",
            "Jenis Kelamin: Perempuan\n",
            "Jenis Kelamin: Laki-laki\n",
            "Age: 52 years old | DOB: 14/02/1974\n",
            "Usia: 21 tahun | Tanggal Lahir: 05/11/2005\n",
            "Status Pernikahan: Menikah (3 Anak)\n",
            "Marital Status: Single / Belum Menikah\n",
            "Marital Status: Divorced / Cerai\n",
            "Agama: Islam\n",
            "Agama: Kristen Protestan\n",
            "Religion: Roman Catholic\n",
            "Agama: Hindu\n",
            "Kewarganegaraan: WNI (Suku Jawa)\n",
            "Nationality: Indonesian Citizen\n",
            "Ethnic Background: Caucasian\n",
            "Tinggi Badan: 175 cm | Berat Badan: 68 kg | Golongan Darah: O\n",
            "Height: 160 cm, Weight: 52 kg\n",
        ]

        for pos_name, cfg in REQUISITION_TEMPLATES.items():
            base_score, _ = matching.score_candidate(cfg["criteria"], self.base_lines)

            for variant in demographic_variants:
                pert_text = variant + self.base_cv_text
                pert_lines = [(i + 1, l.strip()) for i, l in enumerate(pert_text.splitlines()) if l.strip()]
                pert_score, _ = matching.score_candidate(cfg["criteria"], pert_lines)

                delta = abs(pert_score - base_score)
                self.assertEqual(
                    delta, 0.0,
                    f"Position {pos_name} score changed by {delta} with demographic: {variant.strip()}",
                )

    def test_all_catalog_counterfactual_injections_invariant(self) -> None:
        """All predefined COUNTERFACTUAL_INJECTIONS maintain 100% invariance."""
        self.assertGreaterEqual(len(COUNTERFACTUAL_INJECTIONS), 20)

        for pos_name, cfg in REQUISITION_TEMPLATES.items():
            base_score, _ = matching.score_candidate(cfg["criteria"], self.base_lines)

            for name, injection in COUNTERFACTUAL_INJECTIONS:
                pert_text = injection + self.base_cv_text
                pert_lines = [(i + 1, l.strip()) for i, l in enumerate(pert_text.splitlines()) if l.strip()]
                pert_score, _ = matching.score_candidate(cfg["criteria"], pert_lines)

                delta = abs(pert_score - base_score)
                self.assertEqual(delta, 0.0, f"Failed invariance on {name} for {pos_name}")


class TestAcademicEvaluationRunner(unittest.TestCase):
    """Test evaluate_academic_metrics end-to-end execution with isolated mock CSV."""

    def test_evaluate_academic_metrics_isolated_run(self) -> None:
        """Run complete academic evaluation on a small mock CSV dataset without external network."""
        mock_csv_content = (
            "ID,Resume_str,Resume_html,Category\n"
            "it_01,\"Senior Software Developer with deep skills in Programming, Software development, Git, REST API, SQL, and Automated testing.\",<html/>,INFORMATION-TECHNOLOGY\n"
            "it_02,\"DevOps Systems Administrator experienced in Linux, Computer networking, Server administration, System monitoring, and Active directory.\",<html/>,INFORMATION-TECHNOLOGY\n"
            "acc_01,\"Chief Accountant experienced in General ledger, Financial statements, Account reconciliation, Month-end close, Bookkeeping, and Accounts payable.\",<html/>,ACCOUNTANT\n"
            "hr_01,\"Talent Acquisition Partner skilled in Sourcing, Screening, Structured interviewing, Employee relations, Training and development, and Payroll.\",<html/>,HR\n"
            "chef_01,\"Executive Chef with 10 years experience in menu planning, food preparation, kitchen safety, and culinary management.\",<html/>,CHEF\n"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_csv = Path(tmpdir) / "mock_resumes.csv"
            tmp_csv.write_text(mock_csv_content, encoding="utf-8")
            tmp_output = Path(tmpdir) / "mock_academic_report.json"

            # Execute evaluation runner with sequential mode on mock data
            with redirect_stdout(io.StringIO()):
                report = evaluate_academic_metrics(
                    csv_path=tmp_csv,
                    limit=5,
                    output_path=tmp_output,
                    sequential=True,
                )

            # 1. Output file validation
            self.assertTrue(tmp_output.is_file())
            saved_report = json.loads(tmp_output.read_text(encoding="utf-8"))
            self.assertEqual(report["metadata"]["total_candidates_evaluated"], 5)
            self.assertEqual(saved_report["metadata"]["total_candidates_evaluated"], 5)

            # 2. Information Retrieval structure
            ir = report["information_retrieval_ranking"]
            self.assertIn("per_requisition", ir)
            self.assertIn("macro_averages", ir)
            macro = ir["macro_averages"]
            self.assertIn("mean_ndcg_at_5", macro)
            self.assertIn("mean_ndcg_at_10", macro)
            self.assertIn("mean_mrr", macro)
            self.assertGreater(macro["mean_ndcg_at_5"], 0.0)
            self.assertGreater(macro["mean_mrr"], 0.0)

            # 3. Groundedness & Anti-Hallucination
            grounded = report["anti_hallucination_and_groundedness"]
            self.assertGreater(grounded["total_matched_criteria"], 0)
            self.assertEqual(grounded["faithfulness_score"], 1.0)
            self.assertEqual(grounded["faithfulness_percentage"], 100.0)
            self.assertEqual(grounded["hallucination_rate"], 0.0)
            self.assertEqual(grounded["hallucination_percentage"], 0.0)
            self.assertEqual(grounded["attribution_precision"], 1.0)
            self.assertEqual(grounded["attribution_precision_percentage"], 100.0)

            # 4. Counterfactual Fairness guarantees
            fairness = report["counterfactual_fairness"]
            self.assertEqual(fairness["sample_candidates_tested"], 5)
            self.assertGreater(fairness["total_pairwise_comparisons"], 0)
            self.assertEqual(fairness["zero_delta_comparisons"], fairness["total_pairwise_comparisons"])
            self.assertEqual(fairness["demographic_invariance_percentage"], 100.0)
            self.assertEqual(fairness["mean_delta_score"], 0.0)
            self.assertEqual(fairness["max_delta_score"], 0.0)
            self.assertFalse(fairness["algorithmic_bias_detected"])

            # 5. Executive summary printer verification
            summary_buffer = io.StringIO()
            with redirect_stdout(summary_buffer):
                print_executive_summary(report)
            summary_output = summary_buffer.getvalue()
            self.assertIn("KARSAHIRE ACADEMIC & SCIENTIFIC BENCHMARK REPORT", summary_output)
            self.assertIn("Demographic Invariance Rate", summary_output)
            self.assertIn("Faithfulness Score", summary_output)

    def test_missing_csv_raises_file_not_found(self) -> None:
        """Non-existent CSV file raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_csv = Path(tmpdir) / "does_not_exist.csv"
            with self.assertRaises(FileNotFoundError):
                evaluate_academic_metrics(csv_path=missing_csv)


if __name__ == "__main__":
    unittest.main()
