"""Unit tests for rag_service.py internal RAG and retrieval engine."""

from __future__ import annotations

import unittest
from typing import Any

import rag_service


class TestRagService(unittest.TestCase):
    """Test suite for weighted BM25/TF-IDF retrieval over job requisition documents."""

    def setUp(self):
        self.sample_job: dict[str, Any] = {
            "id": "job_sample_01",
            "title": "Senior Backend Engineer",
            "department": "Engineering",
            "description": (
                "Kami mencari Senior Backend Engineer yang bertanggung jawab merancang arsitektur microservices. "
                "Kandidat ideal memiliki rekam jejak dalam pengembangan sistem terdistribusi dengan performa tinggi. "
                "Tugas harian meliputi perancangan REST API, optimasi database, dan kolaborasi lintas tim."
            ),
            "criteria_json": [
                {"id": "c1", "label": "FastAPI", "type": "required", "weight": 2.0},
                {"id": "c2", "label": "PostgreSQL", "type": "required", "weight": 2.0},
                {"id": "c3", "label": "Docker", "type": "preferred", "weight": 1.0},
            ],
        }

        self.hr_finance_job: dict[str, Any] = {
            "id": "job_sample_02",
            "title": "Talent & Finance Specialist",
            "department": "People & Operations",
            "description": (
                "Bertanggung jawab atas talent acquisition dan audit kepatuhan internal. "
                "Memimpin inisiatif talent sourcing untuk posisi kritikal dan menyiapkan laporan keuangan periodik."
            ),
            "criteria_json": [
                {"id": "c4", "label": "Sourcing", "type": "required", "weight": 2.0},
                {"id": "c5", "label": "Audit", "type": "required", "weight": 2.0},
                {"id": "c6", "label": "Tax Reporting", "type": "preferred", "weight": 1.0},
            ],
        }

    def test_tokenization_and_technical_terms(self):
        """Verify that technical terms, symbols, and languages are preserved while stop words are filtered."""
        text = "Membangun sistem dengan FastAPI, PostgreSQL, CI/CD, C++, dan .NET untuk backend."
        tokens = rag_service.tokenize(text, filter_stopwords=True)

        self.assertIn("fastapi", tokens)
        self.assertIn("postgresql", tokens)
        self.assertIn("ci/cd", tokens)
        self.assertIn("c++", tokens)
        self.assertIn(".net", tokens)
        self.assertIn("backend", tokens)
        # Indonesian stop words filtered
        self.assertNotIn("dengan", tokens)
        self.assertNotIn("dan", tokens)
        self.assertNotIn("untuk", tokens)

    def test_retrieve_fastapi_and_postgresql(self):
        """Test technical terms retrieval for FastAPI and PostgreSQL."""
        query = "FastAPI dan PostgreSQL"
        result = rag_service.retrieve_job_context(query, self.sample_job)

        self.assertIn("answer", result)
        self.assertIn("sources", result)
        self.assertEqual(result["query"], query)
        self.assertGreater(result["total_sources_evaluated"], 0)
        self.assertGreater(len(result["sources"]), 0)

        # Check sources schema
        for src in result["sources"]:
            self.assertIn("source", src)
            self.assertIn("text", src)
            self.assertIn("score", src)
            self.assertIn("matched_tokens", src)
            self.assertIsInstance(src["score"], float)
            self.assertIsInstance(src["matched_tokens"], list)

        # Top source should match FastAPI or PostgreSQL criteria or rubrics
        top_tokens = [token for src in result["sources"] for token in src["matched_tokens"]]
        self.assertTrue(any(t in ("fastapi", "postgresql") for t in top_tokens))

    def test_technical_terms_audit_and_sourcing(self):
        """Test technical overlap ranking for Audit and Sourcing."""
        query = "Strategi sourcing kandidat dan pelaksanaan audit internal"
        result = rag_service.retrieve_job_context(query, self.hr_finance_job)

        self.assertGreater(len(result["sources"]), 0)
        matched_all = set()
        for src in result["sources"]:
            matched_all.update(src["matched_tokens"])

        self.assertIn("sourcing", matched_all)
        self.assertIn("audit", matched_all)

    def test_exact_phrase_match_bonus(self):
        """Sentences containing exact phrase matches should rank higher than single token matches."""
        query = "merancang arsitektur microservices"
        result = rag_service.retrieve_job_context(query, self.sample_job)

        self.assertGreater(len(result["sources"]), 0)
        top_source = result["sources"][0]
        self.assertIn("microservices", top_source["text"].lower())
        self.assertIn("arsitektur", top_source["text"].lower())

    def test_mandatory_criteria_weight_higher_than_preferred(self):
        """Mandatory (Required) criteria should receive higher score than preferred criteria."""
        job = {
            "title": "Software Engineer",
            "criteria_json": [
                {"id": "c1", "label": "Python", "type": "required", "weight": 2.0},
                {"id": "c2", "label": "Docker", "type": "preferred", "weight": 1.0},
            ],
            "description": "Posisi software engineer dengan Python dan Docker.",
        }

        # Query Python (required) vs Docker (preferred)
        res_req = rag_service.retrieve_job_context("Python", job)
        res_pref = rag_service.retrieve_job_context("Docker", job)

        self.assertGreater(len(res_req["sources"]), 0)
        self.assertGreater(len(res_pref["sources"]), 0)

        # Top required criterion should have high score due to weight 2.0 multiplier
        score_req = res_req["sources"][0]["score"]
        score_pref = res_pref["sources"][0]["score"]
        self.assertGreater(score_req, score_pref)

    def test_interview_rubrics_retrieval(self):
        """Querying interview guidelines or rubrics returns interview rubric sources."""
        query = "bagaimana panduan dan rubrik wawancara terstruktur?"
        result = rag_service.retrieve_job_context(query, self.sample_job)

        self.assertGreater(len(result["sources"]), 0)
        rubric_sources = [s for s in result["sources"] if "rubrik" in s["source"].lower() or "panduan" in s["source"].lower()]
        self.assertGreater(len(rubric_sources), 0)

    def test_custom_knowledge_retrieval(self):
        """Custom knowledge base should be evaluated and retrieved when relevant."""
        custom_kb = [
            {
                "source": "Kebijakan Internal SLA Rekrutmen",
                "text": "SLA wawancara kandidat adalah 5 hari kerja dari tahap screening.",
                "weight": 1.5,
            },
            {
                "source": "Standar Keamanan Sistem",
                "text": "Setiap engineer wajib mematuhi standar enkripsi AES-256.",
                "weight": 1.0,
            },
        ]
        query = "Berapa hari SLA wawancara kandidat?"
        result = rag_service.retrieve_job_context(query, self.sample_job, custom_knowledge=custom_kb)

        self.assertGreater(len(result["sources"]), 0)
        top_source = result["sources"][0]
        self.assertEqual(top_source["source"], "Kebijakan Internal SLA Rekrutmen")
        self.assertIn("sla", top_source["matched_tokens"])

    def test_top_k_limiting(self):
        """Retrieval should strictly respect the top_k parameter."""
        query = "engineer"
        result = rag_service.retrieve_job_context(query, self.sample_job, top_k=2)
        self.assertLessEqual(len(result["sources"]), 2)

    def test_empty_query_and_irrelevant_query(self):
        """Empty queries and irrelevant queries should return clean responses without errors."""
        res_empty = rag_service.retrieve_job_context("", self.sample_job)
        self.assertEqual(len(res_empty["sources"]), 0)
        self.assertIn("kosong", res_empty["answer"])

        res_irrelevant = rag_service.retrieve_job_context("astronomi bintang teleskop galaksi", self.sample_job)
        self.assertEqual(len(res_irrelevant["sources"]), 0)
        self.assertIn("Tidak ditemukan", res_irrelevant["answer"])

    def test_empty_job_dict(self):
        """Empty job dictionary should be handled gracefully without exceptions."""
        result = rag_service.retrieve_job_context("Python", {})
        self.assertEqual(result["total_sources_evaluated"], 4)  # 4 general interview guidelines
        self.assertEqual(len(result["sources"]), 0)


if __name__ == "__main__":
    unittest.main()
