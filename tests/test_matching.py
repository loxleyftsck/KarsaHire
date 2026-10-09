"""Unit tests for lexical matching, scoring, PII redaction, and profile extraction."""

import unittest
import server


class TestLexicalMatching(unittest.TestCase):
    """Tests for lexical matching and candidate scoring logic."""

    def test_exact_match_direct(self):
        criterion = {"id": "c1", "label": "python", "weight": 2.0, "type": "required"}
        pages = [(1, "Senior Backend Engineer with extensive Python experience.")]
        result = server.match_criterion(criterion, pages)
        self.assertEqual(result["result"], "matched")
        self.assertEqual(result["confidence"], 1.0)
        self.assertIn("Python", result["snippet"])
        self.assertEqual(result["page_number"], 1)

    def test_exact_match_alias(self):
        # PostgreSQL has aliases: postgres, postgres db
        criterion = {"id": "c2", "label": "PostgreSQL", "weight": 2.0, "type": "required"}
        pages = [(2, "Architected relational schemas using postgres db on AWS.")]
        result = server.match_criterion(criterion, pages)
        self.assertEqual(result["result"], "matched")
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["page_number"], 2)

        # Cross-functional collaboration has aliases
        criterion_collab = {
            "id": "c3",
            "label": "cross-functional collaboration",
            "weight": 1.0,
            "type": "preferred",
        }
        pages_collab = [(1, "Successfully worked across teams to deliver features on schedule.")]
        result_collab = server.match_criterion(criterion_collab, pages_collab)
        self.assertEqual(result_collab["result"], "matched")
        self.assertEqual(result_collab["confidence"], 1.0)

    def test_partial_match(self):
        # Multi-token criterion where enough tokens match but no exact alias
        criterion = {
            "id": "c4",
            "label": "cloud native architecture",
            "weight": 1.0,
            "type": "preferred",
        }
        # Tokens: ['cloud', 'native', 'architecture'] (len=3, threshold=2)
        # Line has 'cloud' and 'architecture'
        pages = [(1, "Solid foundation in cloud architecture principles and design.")]
        result = server.match_criterion(criterion, pages)
        self.assertEqual(result["result"], "partial")
        self.assertEqual(result["confidence"], 0.5)
        self.assertIn("cloud architecture", result["snippet"].lower())
        self.assertEqual(result["page_number"], 1)

    def test_unknown_match(self):
        criterion = {
            "id": "c5",
            "label": "Kubernetes cluster administration",
            "weight": 1.0,
            "type": "preferred",
        }
        pages = [
            (1, "Experienced Python backend engineer."),
            (2, "Proficient with Docker and PostgreSQL."),
        ]
        result = server.match_criterion(criterion, pages)
        self.assertEqual(result["result"], "unknown")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["snippet"], "")
        self.assertIsNone(result["page_number"])

    def test_score_candidate_all_matched(self):
        criteria = [
            {"id": "c1", "label": "Python", "weight": 2.0, "type": "required"},
            {"id": "c2", "label": "Docker", "weight": 1.0, "type": "preferred"},
        ]
        pages = [(1, "Senior Developer skilled in Python and Docker.")]
        score, evidence = server.score_candidate(criteria, pages)
        self.assertEqual(score, 100.0)
        self.assertEqual(len(evidence), 2)
        for item in evidence:
            self.assertEqual(item["result"], "matched")
            self.assertEqual(item["confidence"], 1.0)

    def test_score_candidate_none_matched(self):
        criteria = [
            {"id": "c1", "label": "Rust", "weight": 2.0, "type": "required"},
            {"id": "c2", "label": "Kubernetes", "weight": 1.0, "type": "preferred"},
        ]
        pages = [(1, "Specialized in Python and Django.")]
        score, evidence = server.score_candidate(criteria, pages)
        self.assertEqual(score, 0.0)
        self.assertEqual(len(evidence), 2)
        for item in evidence:
            self.assertEqual(item["result"], "unknown")
            self.assertEqual(item["confidence"], 0.0)

    def test_score_candidate_weighted_mix(self):
        # c1 (weight 2.0): matched (1.0) -> contribution 2.0
        # c2 (weight 1.0): partial (0.5) -> contribution 0.5
        # c3 (weight 1.0): unknown (0.0) -> contribution 0.0
        # Total weight = 4.0. Total matched = 2.5 -> score = 100 * 2.5 / 4.0 = 62.5
        criteria = [
            {"id": "c1", "label": "python", "weight": 2.0, "type": "required"},
            {"id": "c2", "label": "cloud native architecture", "weight": 1.0, "type": "preferred"},
            {"id": "c3", "label": "kubernetes", "weight": 1.0, "type": "preferred"},
        ]
        pages = [(1, "Python expert with cloud architecture background.")]
        score, evidence = server.score_candidate(criteria, pages)
        self.assertEqual(score, 62.5)
        self.assertEqual(evidence[0]["result"], "matched")
        self.assertEqual(evidence[1]["result"], "partial")
        self.assertEqual(evidence[2]["result"], "unknown")


class TestPiiRedaction(unittest.TestCase):
    """Tests for PII redaction (redact_for_evidence)."""

    def test_redact_email(self):
        raw = "Reach out at candidate.john@example.com or recruiting+test@startup.co.id."
        redacted = server.redact_for_evidence(raw)
        self.assertNotIn("candidate.john@example.com", redacted)
        self.assertNotIn("recruiting+test@startup.co.id", redacted)
        self.assertIn("[email removed]", redacted)

    def test_redact_phone(self):
        # International and mobile phone numbers with >= 10 digits
        raw1 = "Contact phone: +62 812-3456-7890 for direct inquiries."
        redacted1 = server.redact_for_evidence(raw1)
        self.assertNotIn("+62 812-3456-7890", redacted1)
        self.assertIn("[phone removed]", redacted1)

        raw2 = "Direct line (555) 234-5678 reachable during work hours."
        redacted2 = server.redact_for_evidence(raw2)
        self.assertNotIn("(555) 234-5678", redacted2)
        self.assertIn("[phone removed]", redacted2)

    def test_preserve_years_and_date_ranges(self):
        # Crucial check: date ranges such as 2019 - 2023 must NOT be confused with phone numbers
        raw = "Backend Engineer at Acme Corp (2019 - 2023). Graduated in 2018."
        redacted = server.redact_for_evidence(raw)
        self.assertIn("2019 - 2023", redacted)
        self.assertIn("2018", redacted)
        self.assertNotIn("[phone removed]", redacted)

        # Another range variation
        raw_range = "Project Lead from 2015 - 2020 and 2021 - 2024."
        redacted_range = server.redact_for_evidence(raw_range)
        self.assertIn("2015 - 2020", redacted_range)
        self.assertIn("2021 - 2024", redacted_range)
        self.assertNotIn("[phone removed]", redacted_range)

    def test_redact_date_of_birth(self):
        # Mid-line date of birth
        raw = "Personal Information: DOB: 15/01/1990, Indonesian citizen."
        redacted = server.redact_for_evidence(raw)
        self.assertNotIn("15/01/1990", redacted)
        self.assertIn("[birth date removed]", redacted)

        raw2 = "Candidate details: Date of birth - October 24, 1995; healthy."
        redacted2 = server.redact_for_evidence(raw2)
        self.assertNotIn("October 24, 1995", redacted2)
        self.assertIn("[birth date removed]", redacted2)

    def test_skip_sensitive_header_lines(self):
        raw = (
            "Full Name: Jane Doe\n"
            "Email: jane.doe@example.com\n"
            "Phone: +62 812-9876-5432\n"
            "Address: Jl. Jendral Sudirman No. 10, Jakarta\n"
            "Professional Summary:\n"
            "Experienced software engineer with 4 years in Python development."
        )
        redacted = server.redact_for_evidence(raw)
        self.assertNotIn("Jane Doe", redacted)
        self.assertNotIn("Sudirman", redacted)
        self.assertNotIn("+62 812-9876-5432", redacted)
        self.assertIn("Experienced software engineer with 4 years in Python development.", redacted)

    def test_character_truncation(self):
        long_text = "Proficient in Python and distributed systems. " * 30
        redacted = server.redact_for_evidence(long_text)
        self.assertLessEqual(len(redacted), 700)


class TestProfileExtraction(unittest.TestCase):
    """Tests for profile extraction (skills, years of experience, degrees)."""

    def test_extract_skills(self):
        text = (
            "Senior Developer experienced in Python, FastAPI, Docker, and PostgreSQL. "
            "Also familiar with React and Redis."
        )
        profile = server.profile_from_text(text)
        skills = profile["skills"]
        self.assertIn("python", skills)
        self.assertIn("fastapi", skills)
        self.assertIn("docker", skills)
        self.assertIn("postgresql", skills)
        self.assertIn("react", skills)
        self.assertIn("redis", skills)
        self.assertNotIn("kubernetes", skills)
        self.assertNotIn("rust", skills)

    def test_extract_years_of_experience(self):
        # Should pick maximum years mentioned
        text = "Over 6 years of experience in backend systems and 2 years in machine learning."
        profile = server.profile_from_text(text)
        self.assertEqual(profile["experience_years_mentioned"], 6)

        # Pattern with '+' sign
        text_plus = "Lead Engineer with 8+ years experience in enterprise applications."
        profile_plus = server.profile_from_text(text_plus)
        self.assertEqual(profile_plus["experience_years_mentioned"], 8)

        # No years mentioned
        text_none = "Passionate junior software developer eager to learn."
        profile_none = server.profile_from_text(text_none)
        self.assertIsNone(profile_none["experience_years_mentioned"])

    def test_extract_degrees(self):
        # Bachelor's degree
        text_bachelor = "Graduated with a Bachelor's Degree in Computer Engineering."
        profile_bachelor = server.profile_from_text(text_bachelor)
        self.assertTrue(any("bachelor" in d.lower() for d in profile_bachelor["education_levels_mentioned"]))

        # Master's degree & MBA
        text_master = "Holds a Master's degree in Software Systems and an MBA."
        profile_master = server.profile_from_text(text_master)
        self.assertTrue(any("master" in d.lower() for d in profile_master["education_levels_mentioned"]))

        # Doctorate / Ph.D
        text_doc = "Doctorate in Artificial Intelligence and Neural Networks."
        profile_doc = server.profile_from_text(text_doc)
        self.assertTrue(any("doctor" in d.lower() for d in profile_doc["education_levels_mentioned"]))

        # Associate's degree
        text_assoc = "Completed an Associate's degree in Web Technology."
        profile_assoc = server.profile_from_text(text_assoc)
        self.assertTrue(any("associate" in d.lower() for d in profile_assoc["education_levels_mentioned"]))

        # No degree mentioned
        text_no_deg = "Self-taught programmer with extensive open-source contributions."
        profile_no_deg = server.profile_from_text(text_no_deg)
        self.assertEqual(profile_no_deg["education_levels_mentioned"], [])


class TestMatchingModule(unittest.TestCase):
    """Tests for modular matching.py engine if available."""

    def setUp(self):
        try:
            import matching
            self.matching = matching
        except ImportError:
            self.skipTest("matching.py module not available")

    def test_matching_module_scoring(self):
        crit_exact = {"id": "c1", "label": "python", "weight": 2.0, "type": "required"}
        crit_part = {"id": "c2", "label": "cloud native architecture", "weight": 1.0, "type": "preferred"}
        crit_unk = {"id": "c3", "label": "kubernetes", "weight": 1.0, "type": "preferred"}

        pages = [(1, "Python engineer with cloud architecture experience.")]

        res_exact = self.matching.match_criterion(crit_exact, pages)
        self.assertEqual(res_exact["result"], "matched")
        self.assertEqual(res_exact["confidence"], 1.0)

        res_part = self.matching.match_criterion(crit_part, pages)
        self.assertEqual(res_part["result"], "partial")
        self.assertEqual(res_part["confidence"], 0.5)

        res_unk = self.matching.match_criterion(crit_unk, pages)
        self.assertEqual(res_unk["result"], "unknown")
        self.assertEqual(res_unk["confidence"], 0.0)

        score, evidence = self.matching.score_candidate([crit_exact, crit_part, crit_unk], pages)
        self.assertEqual(score, 62.5)

    def test_matching_module_bilingual_redaction(self):
        raw = (
            "Nama Lengkap: Budi Santoso\n"
            "No HP: 081234567890\n"
            "Email: budi.santoso@example.com\n"
            "Tanggal Lahir: 15 Januari 1990\n"
            "Software Engineer at Tokopedia (2019 - 2023)\n"
            "Contact: budi@test.com, Phone: +62 811-2345-6789\n"
        )
        redacted = self.matching.redact_for_evidence(raw)
        self.assertNotIn("Budi Santoso", redacted)
        self.assertNotIn("budi.santoso@example.com", redacted)
        self.assertNotIn("budi@test.com", redacted)
        self.assertNotIn("+62 811-2345-6789", redacted)
        self.assertIn("2019 - 2023", redacted)
        self.assertIn("[phone removed]", redacted)
        self.assertIn("[email removed]", redacted)

    def test_matching_module_profile_extraction(self):
        text = "Backend developer dengan 4 tahun pengalaman, lulusan S1 Teknik Informatika. Mahir Python dan Docker."
        profile = self.matching.profile_from_text(text)
        self.assertIn("python", profile["skills"])
        self.assertIn("docker", profile["skills"])
        self.assertEqual(profile["experience_years_mentioned"], 4)
        self.assertIn("Bachelor's", profile["education_levels_mentioned"])


if __name__ == "__main__":
    unittest.main()
