"""Matching and evidence extraction module for KarsaHire.

Provides lexical evidence-first matching, candidate scoring, and requisition retrieval.
Powered by the domain skill taxonomy and bilingual dictionaries in taxonomy.py.
"""

from __future__ import annotations

import json
import re
from typing import Any

from taxonomy import (
    ALIASES,
    EDUCATION_LEVEL_PATTERNS,
    EXPERIENCE_YEARS_PATTERNS,
    SKILLS,
    extract_experience_years,
    match_education_levels,
)

# ---------------------------------------------------------------------------
# PII Redaction Regexes
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)")
SENSITIVE_LINE_RE = re.compile(
    r"^\s*(?:full\s+name|candidate\s+name|name|nama\s+lengkap|nama|"
    r"email|e-mail|phone|mobile|telepon|no(?:mor)?\s*(?:hp|telepon|telp)|"
    r"date\s+of\s+birth|dob|birthday|tanggal\s+lahir|tgl\s+lahir|"
    r"address|home\s+address|alamat(?: rumah)?)\s*[:|–-]",
    re.IGNORECASE,
)


def normalize(value: str) -> str:
    """Normalize text by folding case, normalizing dashes, and stripping whitespace."""
    return re.sub(r"\s+", " ", value.casefold().replace("–", "-")).strip()


def redact_for_evidence(value: str) -> str:
    """Remove common direct identifiers before evidence is written to SQLite."""
    def redact_phone(match: re.Match[str]) -> str:
        # Avoid mistaking common date ranges such as 2019 - 2023 for phone numbers.
        digits = re.sub(r"\D", "", match.group(0))
        return "[phone removed]" if len(digits) >= 10 else match.group(0)

    lines = []
    for line in value.splitlines():
        if SENSITIVE_LINE_RE.match(line):
            continue
        line = EMAIL_RE.sub("[email removed]", line)
        line = PHONE_RE.sub(redact_phone, line)
        line = re.sub(
            r"\b(?:DOB|date of birth|birthday|tanggal lahir|tgl lahir)\s*[:|-]?\s*[^,;|]+",
            "[birth date removed]", line, flags=re.IGNORECASE,
        )
        lines.append(line)
    return " ".join(" ".join(lines).split())[:700]


def profile_from_text(text: str) -> dict:
    """Extract candidate profile summary including matched skills, experience years, and education."""
    ntext = normalize(text)
    skills = [skill for skill in SKILLS if re.search(rf"(?<!\w){re.escape(skill)}(?!\w)", ntext)]
    years = extract_experience_years(ntext)
    degrees = match_education_levels(ntext)
    return {
        "skills": skills,
        "experience_years_mentioned": years,
        "education_levels_mentioned": degrees,
    }


def criterion_aliases(label: str) -> list[str]:
    """Retrieve all alias variants, acronyms, and bilingual synonyms for a criterion label."""
    base = normalize(label)
    found = [base]
    if base in ALIASES:
        found.extend(ALIASES[base])
    for key, aliases in ALIASES.items():
        if base == key or base in aliases:
            found.extend(aliases)

    # Support compound / slash expressions like "Bookkeeping / Pembukuan" or "Accounts Payable (AP)"
    for part in re.split(r"[/|&()]", label):
        norm_part = normalize(part)
        if norm_part and norm_part != base:
            found.append(norm_part)
            if norm_part in ALIASES:
                found.extend(ALIASES[norm_part])
            for key, aliases in ALIASES.items():
                if norm_part == key or norm_part in aliases:
                    found.extend(aliases)

    return list(dict.fromkeys(term for term in found if term))


def match_criterion(criterion: dict, pages: list[tuple[int | None, str]]) -> dict:
    """Match a single criterion against document lines, returning status, confidence, snippet, and page."""
    aliases = criterion_aliases(criterion["label"])
    tokens = [t for t in re.findall(r"[a-z0-9+#.]+", normalize(criterion["label"])) if len(t) > 1]
    exact: list[tuple[int | None, str]] = []
    partial: list[tuple[int | None, str]] = []

    for page_num, line in pages:
        normalized_line = normalize(line)
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized_line) for alias in aliases):
            exact.append((page_num, line))
            continue
        present = sum(1 for token in tokens if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", normalized_line))
        if len(tokens) >= 2 and present >= max(2, (len(tokens) + 1) // 2):
            partial.append((page_num, line))

    if exact:
        page_num, line = exact[0]
        # This value encodes lexical match strength only; it is not a probability.
        return {
            "result": "matched",
            "confidence": 1.0,
            "snippet": redact_for_evidence(line),
            "page_number": page_num,
        }
    if partial:
        page_num, line = partial[0]
        return {
            "result": "partial",
            "confidence": 0.5,
            "snippet": redact_for_evidence(line),
            "page_number": page_num,
        }
    return {"result": "unknown", "confidence": 0.0, "snippet": "", "page_number": None}


def score_candidate(criteria: list[dict], pages: list[tuple[int | None, str]]) -> tuple[float, list[dict]]:
    """Score a candidate across all criteria and return overall percentage and per-criterion evidence rows."""
    total_weight = sum(float(c.get("weight", 1.0)) for c in criteria) or 1.0
    matched_total = 0.0
    evidence_rows = []
    for criterion in criteria:
        result = match_criterion(criterion, pages)
        match_value = {"matched": 1.0, "partial": 0.5, "unknown": 0.0}[result["result"]]
        matched_total += match_value * float(criterion.get("weight", 1.0))
        evidence_rows.append({**criterion, **result})
    return round(100 * matched_total / total_weight, 1), evidence_rows


def rank_retrieval(query: str, job: dict[str, Any]) -> list[dict]:
    """Retrieval-only RAG over approved requisition content powered by rag_service."""
    try:
        from rag_service import retrieve_job_context
        return retrieve_job_context(query, job)["sources"]
    except Exception:
        criteria_raw = job.get("criteria_json", "[]")
        if isinstance(criteria_raw, str):
            try:
                criteria = json.loads(criteria_raw)
            except Exception:
                criteria = []
        elif isinstance(criteria_raw, list):
            criteria = criteria_raw
        else:
            criteria = []

        sources = [
            {"source": "Deskripsi lowongan", "text": job.get("description") or ""},
            *[
                {"source": f"Kriteria: {c['label']}", "text": c.get("label", "")}
                for c in criteria
                if isinstance(c, dict) and "label" in c
            ],
        ]
        terms = set(re.findall(r"[a-z0-9+#.]{2,}", normalize(query)))
        ranked = []
        for entry in sources:
            text = entry["text"]
            if not text:
                continue
            sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
            for sentence in sentences:
                overlap = terms.intersection(re.findall(r"[a-z0-9+#.]{2,}", normalize(sentence)))
                if overlap:
                    ranked.append({**entry, "text": sentence.strip(), "overlap": len(overlap)})
        ranked.sort(key=lambda x: x["overlap"], reverse=True)
        return ranked[:5]
