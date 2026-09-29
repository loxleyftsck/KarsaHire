-- Canonical KarsaHire SQLite schema. The database file itself stays local.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    department TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    criteria_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'awaiting_approval',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    reviewer TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(job_id, role)
);

CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    file_type TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    score REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'needs_review',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
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

CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    reviewer TEXT NOT NULL,
    role TEXT NOT NULL,
    decision TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    candidate_id TEXT,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_approvals_job_id ON approvals(job_id);
CREATE INDEX IF NOT EXISTS idx_candidates_job_id ON candidates(job_id);
CREATE INDEX IF NOT EXISTS idx_evidence_candidate_id ON evidence(candidate_id);
CREATE INDEX IF NOT EXISTS idx_reviews_candidate_id ON reviews(candidate_id);
CREATE INDEX IF NOT EXISTS idx_audit_job_created ON audit_events(job_id, created_at);
