"""Unit and integration tests for Internal RAG & Retrieval Service."""

import unittest

import rag_service


class TestRAGRetrieval(unittest.TestCase):
    """Comprehensive test suite for rag_service.retrieve_job_context."""

    def setUp(self):
        self.sample_job = {
            "id": "job_sample_01",
            "title": "Backend Software Engineer",
            "department": "Engineering / Platform",
            "description": (
                "Bertanggung jawab merancang arsitektur microservices performa tinggi "
                "menggunakan Python dan FastAPI. Mengelola database relasional PostgreSQL "
                "serta orkestrasi kontainer menggunakan Docker dan Kubernetes. "
                "Bekerja sama dalam tim lintas fungsi dengan metode Agile Scrum."
            ),
            "criteria": [
                {
                    "id": "crit_python",
                    "label": "Python & FastAPI",
                    "type": "required",
                    "weight": 2.0,
                },
                {
                    "id": "crit_postgres",
                    "label": "PostgreSQL Database",
                    "type": "required",
                    "weight": 2.0,
                },
                {
                    "id": "crit_k8s",
                    "label": "Kubernetes & Docker",
                    "type": "required",
                    "weight": 2.0,
                },
                {
                    "id": "crit_figma",
                    "label": "Figma & UI Prototyping",
                    "type": "preferred",
                    "weight": 1.0,
                },
            ],
        }

    # -------------------------------------------------------------------------
    # 1. Tokenization, Normalization, & Technical Term Recognition
    # -------------------------------------------------------------------------
    def test_tokenize_preserves_technical_identifiers(self):
        """Punctuation-heavy technical terms like C++, .NET, CI/CD, and Node.js must be preserved."""
        text = "Menguasai C++, .NET, CI/CD pipeline, Node.js, dan FastAPI."
        tokens = rag_service.tokenize(text, filter_stopwords=False)
        self.assertIn("c++", tokens)
        self.assertIn(".net", tokens)
        self.assertIn("ci/cd", tokens)
        self.assertIn("node.js", tokens)
        self.assertIn("fastapi", tokens)

    def test_tokenize_filters_bilingual_stopwords(self):
        """Common Indonesian and English stop words are filtered out while keywords remain."""
        text = "Yang ada di dalam kriteria wajib untuk posisi backend software engineer"
        tokens = rag_service.tokenize(text, filter_stopwords=True)
        # 'yang', 'ada', 'di', 'dalam', 'untuk' should be filtered
        self.assertNotIn("yang", tokens)
        self.assertNotIn("ada", tokens)
        self.assertNotIn("di", tokens)
        self.assertNotIn("dalam", tokens)
        self.assertNotIn("untuk", tokens)
        # 'wajib', 'kriteria', 'backend' should be preserved
        self.assertIn("wajib", tokens)
        self.assertIn("kriteria", tokens)
        self.assertIn("backend", tokens)

    def test_is_technical_term(self):
        """Technical skills from taxonomy or canonical list must be identified as technical terms."""
        self.assertTrue(rag_service.is_technical_term("fastapi"))
        self.assertTrue(rag_service.is_technical_term("postgresql"))
        self.assertTrue(rag_service.is_technical_term("docker"))
        self.assertFalse(rag_service.is_technical_term("wawancara"))
        self.assertFalse(rag_service.is_technical_term("perusahaan"))

    # -------------------------------------------------------------------------
    # 2. Token Search & Matching
    # -------------------------------------------------------------------------
    def test_retrieve_token_search_single_keyword(self):
        """Querying a single technical term returns matching sources and matched_tokens."""
        result = rag_service.retrieve_job_context("FastAPI", self.sample_job)
        self.assertIn("sources", result)
        self.assertIn("answer", result)
        self.assertGreater(len(result["sources"]), 0)

        # Check structure of top source
        top_source = result["sources"][0]
        self.assertIn("source", top_source)
        self.assertIn("text", top_source)
        self.assertIn("score", top_source)
        self.assertIn("matched_tokens", top_source)
        self.assertIn("fastapi", [t.lower() for t in top_source["matched_tokens"]])
        self.assertGreater(top_source["score"], 0.0)

    def test_retrieve_token_search_multi_terms(self):
        """Querying multiple technical terms finds sources mentioning both or either."""
        result = rag_service.retrieve_job_context("PostgreSQL Docker", self.sample_job)
        self.assertGreater(len(result["sources"]), 0)
        found_tokens = set()
        for s in result["sources"]:
            found_tokens.update(s["matched_tokens"])
        self.assertTrue("postgresql" in found_tokens or "docker" in found_tokens)

    # -------------------------------------------------------------------------
    # 3. Mandatory (Required) Criteria Weighting
    # -------------------------------------------------------------------------
    def test_required_criteria_weighted_higher_than_preferred(self):
        """Required criteria with weight 2.0 receive higher relevance score than preferred criteria."""
        # Query matching required criterion 'Python & FastAPI'
        res_req = rag_service.retrieve_job_context("Python", self.sample_job)
        # Query matching preferred criterion 'Figma & UI Prototyping'
        res_pref = rag_service.retrieve_job_context("Figma", self.sample_job)

        self.assertGreater(len(res_req["sources"]), 0)
        self.assertGreater(len(res_pref["sources"]), 0)

        top_req_score = res_req["sources"][0]["score"]
        top_pref_score = res_pref["sources"][0]["score"]

        # Required criteria should score noticeably higher due to required weight multiplier
        self.assertGreater(top_req_score, top_pref_score)

    def test_query_with_wajib_boosts_required_criteria(self):
        """Queries containing signal word 'wajib' prioritize required criteria."""
        result = rag_service.retrieve_job_context("kriteria wajib yang harus dipenuhi", self.sample_job)
        self.assertGreater(len(result["sources"]), 0)
        # Top source should be a required criterion or guidelines
        top_source_name = result["sources"][0]["source"].lower()
        self.assertTrue("wajib" in top_source_name or "kriteria" in top_source_name)

    # -------------------------------------------------------------------------
    # 4. Empty Query & No Relevant Results Handling
    # -------------------------------------------------------------------------
    def test_empty_and_whitespace_query(self):
        """Empty or whitespace-only query returns informative response with zero sources."""
        for q in ("", "   ", "\t\n"):
            res = rag_service.retrieve_job_context(q, self.sample_job)
            self.assertEqual(len(res["sources"]), 0)
            self.assertIn("kosong", res["answer"].lower())
            self.assertEqual(res["query"], q)
            self.assertGreater(res["total_sources_evaluated"], 0)

    def test_no_relevant_results(self):
        """Query with completely unrelated terms returns clean response with zero sources."""
        unrelated_query = "astronomi teleskop galaksi planet mars roket"
        res = rag_service.retrieve_job_context(unrelated_query, self.sample_job)
        self.assertEqual(len(res["sources"]), 0)
        self.assertIn("tidak ditemukan rujukan", res["answer"].lower())
        self.assertEqual(res["query"], unrelated_query)
        self.assertGreater(res["total_sources_evaluated"], 0)

    def test_empty_job_data(self):
        """Job with no description or criteria is handled safely without exception."""
        empty_job = {"id": "empty", "title": "", "description": "", "criteria": []}
        res = rag_service.retrieve_job_context("Python", empty_job)
        self.assertIsInstance(res, dict)
        self.assertIn("answer", res)
        self.assertIn("sources", res)

    # -------------------------------------------------------------------------
    # 5. Top-K Parameter & Custom Knowledge
    # -------------------------------------------------------------------------
    def test_top_k_parameter_limits_output(self):
        """Parameter top_k limits the maximum number of returned sources."""
        res_default = rag_service.retrieve_job_context("Python", self.sample_job, top_k=5)
        res_limited = rag_service.retrieve_job_context("Python", self.sample_job, top_k=2)

        self.assertLessEqual(len(res_limited["sources"]), 2)
        if len(res_default["sources"]) > 2:
            self.assertEqual(len(res_limited["sources"]), 2)

    def test_custom_knowledge_integration(self):
        """Custom knowledge sources can be provided and retrieved accurately."""
        custom_docs = [
            {
                "source": "SOP Rekrutmen Korporat: Tahap Wawancara",
                "text": "Setiap pelamar posisi senior wajib melalui dua tahap wawancara teknis dan satu HR debrief.",
                "weight": 1.5,
            },
            {
                "source": "Kebijakan Kompensasi & Benefit",
                "text": "Struktur gaji pokok dan tunjangan kesehatan ditetapkan berdasarkan grade pekerjaan.",
                "weight": 1.0,
            },
        ]

        res = rag_service.retrieve_job_context(
            "berapa tahap wawancara teknis", self.sample_job, custom_knowledge=custom_docs
        )
        self.assertGreater(len(res["sources"]), 0)
        sources_found = [s["source"] for s in res["sources"]]
        self.assertTrue(any("SOP Rekrutmen Korporat" in s for s in sources_found))


if __name__ == "__main__":
    unittest.main()
