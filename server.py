"""Local, evidence-first recruitment copilot prototype.

Uses standard-library HTTP/SQLite plus document packages. OCR runs locally with
PaddleOCR by default; an internal OCR API is an optional alternative. No public
LLM endpoint is called.
Matching is lexical and keeps unknown evidence separate from a negative human decision.
"""

from __future__ import annotations

import base64
import csv
import ctypes
import hashlib
import http.client
import importlib.util
import io
import ipaddress
import json
import os
import platform
import re
import signal
import sqlite3
import socket
import subprocess
import sys
from contextlib import contextmanager
from collections.abc import Callable, Iterator
import zipfile
import threading
import time
import uuid
import urllib.error
import urllib.request
from collections import Counter, deque
from datetime import datetime, timezone
from email import policy
from email.parser import BytesHeaderParser, BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version as installed_package_version
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA = ROOT / "data"
DB_PATH_ENV = "RECRUITMENT_COPILOT_DB_PATH"
MANUAL_UPLOADS_ENV = "RECRUITMENT_COPILOT_MANUAL_UPLOADS_ENABLED"


def manual_uploads_enabled_from_env(raw_value: str | None = None) -> bool:
    configured = os.environ.get(MANUAL_UPLOADS_ENV, "") if raw_value is None else raw_value
    normalized = configured.strip().casefold()
    if not normalized or normalized in {"0", "false", "no", "off"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True
    raise SystemExit(f"{MANUAL_UPLOADS_ENV} harus bernilai true atau false.")


MANUAL_UPLOADS_ENABLED = manual_uploads_enabled_from_env()


def database_path_from_env(raw_path: str | None = None) -> Path:
    configured_path = os.environ.get(DB_PATH_ENV, "") if raw_path is None else raw_path
    configured_path = configured_path.strip()
    if not configured_path:
        return DATA / "copilot.sqlite3"
    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        raise SystemExit(f"{DB_PATH_ENV} harus berupa path absolut.")
    return path


DB_PATH = database_path_from_env()
SYNTHETIC_DATASET_ID = "sukhrobnurali/resume-parsing-vision"
SYNTHETIC_DATASET_DIR = DATA / "synthetic-cv-32"
SYNTHETIC_DATASET_KEY_PREFIX = f"hf:{SYNTHETIC_DATASET_ID}:"
SYNTHETIC_DATASET_SIZE = 32
BUILTIN_DEMO_SOURCE_KEY = "demo:backend-engineer:v1"
BUILTIN_DEMO_TEXT = (
    "Candidate Demo 001\nSUMMARY\nBackend engineer with 4 years of experience building API services.\n"
    "SKILLS\nPython, FastAPI, PostgreSQL, Docker, Git\nEXPERIENCE\n"
    "Built FastAPI services backed by PostgreSQL and deployed containers with Docker.\n"
    "Worked across product, data, and infrastructure teams to launch customer-facing APIs.\n"
    "EDUCATION\nBachelor of Science in Computer Science"
)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SHUTDOWN_GRACE_ENV = "RECRUITMENT_COPILOT_SHUTDOWN_GRACE_SECONDS"
DEFAULT_SHUTDOWN_GRACE_SECONDS = 5
MAX_SHUTDOWN_GRACE_SECONDS = 120
SCHEMA_VERSION = 1
CANDIDATE_ORDER_BY_SQL = "score DESC, created_at ASC, id ASC"
PIPELINE_VERSION_ENV = "RECRUITMENT_COPILOT_PIPELINE_VERSION"
PIPELINE_VERSION_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_BODY_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024
MAX_BODY_READ_SECONDS = 60
BODY_READ_IDLE_TIMEOUT_SECONDS = 5
REQUEST_HEADER_IDLE_TIMEOUT_SECONDS = 5
REQUEST_HEADER_TOTAL_TIMEOUT_SECONDS = 15
MAX_REQUEST_HEADER_BYTES = 64 * 1024
BODY_READ_CHUNK_BYTES = 64 * 1024
MAX_CONCURRENT_UPLOADS = 2
UPLOAD_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_UPLOADS)
MAX_CONCURRENT_HTTP_HANDLERS = 32
MAX_MULTIPART_HEADER_BYTES = 16 * 1024
MAX_MULTIPART_HEADER_LINES = 64
MAX_EXTRACTED_TEXT_CHARACTERS = 1_000_000
MAX_EXTRACTED_NONEMPTY_LINES = 20_000
DOCUMENT_LINE_BREAK_RE = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
PROCESS_STARTED_AT = time.monotonic()
METRICS_LOCK = threading.Lock()
HTTP_REQUEST_COUNTS: Counter[tuple[str, str, int | None]] = Counter()
HTTP_RESPONSE_BYTES_TOTAL = 0
UPLOADS_ACTIVE = 0
UPLOAD_BUSY_REJECTIONS_TOTAL = 0
HTTP_HANDLERS_ACTIVE = 0
HTTP_HANDLER_REJECTIONS_TOTAL = 0
DRAINING = threading.Event()
MAX_PDF_PAGES = 40
MAX_PDF_WORKER_MEMORY_BYTES = 256 * 1024 * 1024
MAX_PDF_WORKER_SECONDS = 30
MAX_PDF_WORKER_RESULT_BYTES = 48 * 1024 * 1024
MAX_PDF_OCR_IMAGES_TOTAL_BYTES = 32 * 1024 * 1024
MAX_PDF_DECODED_STREAM_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_DOCX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_DOCX_ZIP_MEMBERS = 2_000
OCR_KEY_ENV = "RECRUITMENT_COPILOT_OCR_API_KEY"
OCR_URL_ENV = "RECRUITMENT_COPILOT_OCR_API_URL"
OCR_ALLOWED_ORIGINS_ENV = "RECRUITMENT_COPILOT_OCR_ALLOWED_ORIGINS"
OCR_MODEL = os.environ.get("RECRUITMENT_COPILOT_OCR_MODEL", "ocr-lighton")
OCR_BACKEND = os.environ.get("RECRUITMENT_COPILOT_OCR_BACKEND", "paddle").strip().lower()
OCR_URL_ENV = "RECRUITMENT_COPILOT_OCR_API_URL"
OCR_REQUESTS_PER_MINUTE = 6
MAX_OCR_IMAGES_PER_PDF = 6
MAX_OCR_RESPONSE_BYTES = 1024 * 1024
OCR_CALLS: deque[float] = deque()
OCR_LOCK = threading.Lock()
OCR_SEMAPHORE = threading.BoundedSemaphore(5)


class RequestBodyTimeout(TimeoutError):
    """Raised when a client does not finish sending a bounded request body in time."""


class RequestHeadReader:
    """Read HTTP headers with idle and absolute deadlines and a byte cap."""

    def __init__(self, connection: socket.socket):
        self.connection = connection
        self.buffer = bytearray()
        self.original_timeout = REQUEST_HEADER_IDLE_TIMEOUT_SECONDS
        self.header_deadline = 0.0
        self.header_bytes = 0
        self.request_line_seen = False
        self.in_headers = False

    def begin_request(self) -> None:
        self.original_timeout = self.connection.gettimeout()
        self.header_deadline = time.monotonic() + REQUEST_HEADER_TOTAL_TIMEOUT_SECONDS
        self.header_bytes = 0
        self.request_line_seen = False
        self.in_headers = True

    def _end_headers(self) -> None:
        self.in_headers = False
        self.connection.settimeout(self.original_timeout)

    def _receive(self, size: int) -> bytes:
        if self.in_headers:
            remaining = self.header_deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("request headers exceeded the total time limit")
            idle_timeout = REQUEST_HEADER_IDLE_TIMEOUT_SECONDS
            if self.original_timeout is not None:
                idle_timeout = min(idle_timeout, self.original_timeout)
            self.connection.settimeout(min(idle_timeout, remaining))
        chunk = self.connection.recv(size)
        if not chunk and self.in_headers:
            self._end_headers()
        return chunk

    def _take(self, size: int) -> bytes:
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def readline(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        while True:
            newline = self.buffer.find(b"\n")
            if newline >= 0:
                count = newline + 1
                if size >= 0:
                    count = min(count, size)
                break
            if size >= 0 and len(self.buffer) >= size:
                count = size
                break
            receive_size = 4096 if size < 0 else min(4096, size - len(self.buffer))
            chunk = self._receive(max(1, receive_size))
            if not chunk:
                count = len(self.buffer)
                break
            self.buffer.extend(chunk)

        line = self._take(count)
        if self.in_headers:
            if not self.request_line_seen:
                self.request_line_seen = True
            else:
                self.header_bytes += len(line)
                if self.header_bytes > MAX_REQUEST_HEADER_BYTES:
                    raise http.client.HTTPException(
                        "aggregate request headers exceed the configured byte limit"
                    )
                if line in (b"", b"\r\n", b"\n"):
                    self._end_headers()
        return line

    def read(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        if size < 0:
            raise ValueError("request reader only supports bounded body reads")
        while len(self.buffer) < size:
            chunk = self._receive(min(64 * 1024, size - len(self.buffer)))
            if not chunk:
                break
            self.buffer.extend(chunk)
        return self._take(min(size, len(self.buffer)))

    def close(self) -> None:
        # The HTTP server owns and closes the socket after the handler returns.
        return None


def read_request_body(handler: BaseHTTPRequestHandler, length: int) -> bytes:
    """Read a declared, bounded body with idle and total time limits."""
    original_timeout = handler.connection.gettimeout()
    deadline = time.monotonic() + MAX_BODY_READ_SECONDS
    body = bytearray()
    try:
        while len(body) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                handler.close_connection = True
                raise RequestBodyTimeout("Batas waktu pengiriman body permintaan terlampaui.")
            handler.connection.settimeout(min(BODY_READ_IDLE_TIMEOUT_SECONDS, remaining))
            try:
                chunk = handler.rfile.read(min(BODY_READ_CHUNK_BYTES, length - len(body)))
            except socket.timeout as exc:
                handler.close_connection = True
                raise RequestBodyTimeout("Pengiriman body permintaan berhenti terlalu lama.") from exc
            if not chunk:
                handler.close_connection = True
                raise ValueError("Body permintaan terputus sebelum lengkap.")
            body.extend(chunk)
            if time.monotonic() >= deadline:
                handler.close_connection = True
                raise RequestBodyTimeout("Batas waktu pengiriman body permintaan terlampaui.")
        return bytes(body)
    finally:
        try:
            handler.connection.settimeout(original_timeout)
        except OSError:
            handler.close_connection = True


def request_content_length(handler: BaseHTTPRequestHandler) -> int:
    """Accept one decimal Content-Length and reject unsupported transfer framing."""
    content_lengths = handler.headers.get_all("Content-Length", [])
    transfer_encodings = handler.headers.get_all("Transfer-Encoding", [])
    if transfer_encodings or len(content_lengths) > 1:
        handler.close_connection = True
        raise ValueError("Framing body permintaan tidak didukung.")
    if not content_lengths:
        return 0
    raw_length = content_lengths[0].strip()
    if len(raw_length) > 20 or not raw_length.isascii() or not raw_length.isdecimal():
        handler.close_connection = True
        raise ValueError("Content-Length tidak valid.")
    return int(raw_length)


class _RejectOCRRedirects(urllib.request.HTTPRedirectHandler):
    """Keep OCR credentials scoped to the configured endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirects are disabled for OCR", headers, fp)


EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)")
AGE_VALUE_RE = re.compile(
    r"\b(?:age|usia|umur)\s*[:=|–-]?\s*\d{1,3}\b|"
    r"\b(?:aged?|berusia)\s+\d{1,3}(?:\s+tahun)?\b|"
    r"\b\d{1,3}\s*(?:years?\s+old|years?\s+of\s+age)\b",
    re.IGNORECASE,
)
SENSITIVE_LINE_RE = re.compile(
    r"^\s*(?:full\s+name|candidate\s+name|nama(?:\s+(?:lengkap|kandidat))?|name|"
    r"email|e-mail|surel|phone|mobile|ponsel|telepon|no\.?\s*(?:hp|telepon|ktp|nik|identitas)|"
    r"nomor(?:\s+(?:hp|telepon|ktp|nik|identitas|induk\s+kependudukan))?|hp|"
    r"nik|ktp|paspor|passport|national\s+id|id\s+number|identity\s+(?:number|card)|"
    r"social\s+security(?:\s+number)?|ssn|photo|foto|pasfoto|"
    r"date\s+of\s+birth|tempat(?:\s*,\s*|\s*/\s*|\s+)tanggal\s+lahir|"
    r"tempat\s+lahir|tanggal\s+lahir|tgl\.?\s*lahir|ttl|dob|birthday|"
    r"address|home\s+address|alamat(?:\s+(?:rumah|domisili|lengkap))?|"
    r"age|usia|umur|gender|sex|jenis\s+kelamin|religion|agama|"
    r"marital\s+status|status\s+(?:perkawinan|pernikahan|menikah)|race|ethnicity|suku|etnis|"
    r"disability|disabilitas|"
    r"nationality|kewarganegaraan)\s*[:|–-]",
    re.IGNORECASE,
)
PROFILE_SECTION_HEADING_RE = re.compile(
    r"\b(?:(?:technical\s+)?skills|keahlian|kemampuan|"
    r"(?:professional\s+|work\s+)?experience|pengalaman(?:\s+kerja)?|"
    r"riwayat\s+pekerjaan|employment|education|pendidikan|projects?|proyek|"
    r"certificates?|certifications?|sertifikat|sertifikasi|languages|bahasa|"
    r"summary|ringkasan|profile|profil|objective|tujuan)\b",
    re.IGNORECASE,
)


def profile_text_without_labeled_sensitive_lines(text: str) -> str:
    """Drop labeled PII lines while recovering a section merged onto the same PDF line."""
    profile_lines = []
    for line in text.splitlines():
        sensitive_label = SENSITIVE_LINE_RE.match(line)
        if sensitive_label is None:
            profile_lines.append(line)
            continue
        tail = line[sensitive_label.end():]
        recovery_starts = []
        sentence_boundary = re.search(r"[.!?]\s+(?=[A-Z])", tail)
        if sentence_boundary:
            recovery_starts.append(sentence_boundary.end())
        section_heading = PROFILE_SECTION_HEADING_RE.search(tail)
        if section_heading:
            recovery_starts.append(section_heading.start())
        if recovery_starts:
            profile_lines.append(tail[min(recovery_starts):])
    return "\n".join(profile_lines)


EXPERIENCE_DURATION_RE = re.compile(
    r"\b(?:(?:more than|over|nearly|close to|roughly|about|around|"
    r"kurang lebih|lebih dari|sekitar|hampir|selama)\s+)?"
    r"(?P<amount>a couple of|couple of|a few|few|several|"
    r"dua puluh|sembilan belas|delapan belas|tujuh belas|enam belas|"
    r"lima belas|empat belas|tiga belas|dua belas|sebelas|a|an|\d{1,2}(?:[.,]\d{1,2})?\+?|"
    r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"satu|dua|tiga|empat|lima|enam|tujuh|delapan|sembilan|sepuluh)\s+"
    r"(?P<unit>years?|yrs?|decades?|tahun|thn)\b",
    re.IGNORECASE,
)
EXPERIENCE_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
    "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
    "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10,
    "sebelas": 11, "dua belas": 12, "tiga belas": 13, "empat belas": 14,
    "lima belas": 15, "enam belas": 16, "tujuh belas": 17,
    "delapan belas": 18, "sembilan belas": 19, "dua puluh": 20,
}
AGE_DURATION_PREFIX_RE = re.compile(
    r"\b(?:aged|age|usia|umur|berusia|berumur)\s*"
    r"(?:(?:is|of|saya)\s*)?[:=]?\s*$",
    re.IGNORECASE,
)
AGE_DURATION_SUFFIX_RE = re.compile(r"^\s*(?:old\b|of\s+age\b)", re.IGNORECASE)
NEGATION_CUE_RE = re.compile(
    r"\b(?:no|not|never|without|lack(?:s|ed|ing)?|avoid(?:s|ed|ing)?|"
    r"don't|doesn't|didn't|tidak|belum|tanpa|kurang|bukan|jarang)\b",
    re.IGNORECASE,
)

SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "golang",
    "rust", "sql", "postgresql", "mysql", "mongodb", "redis", "fastapi", "django",
    "flask", "react", "react.js", "node.js", "node", "next.js", "vue", "angular",
    "html", "css", "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
    "linux", "git", "machine learning", "deep learning", "pytorch", "tensorflow",
    "scikit-learn", "nlp", "llm", "rag", "data analysis", "pandas", "spark",
    "airflow", "tableau", "power bi", "project management", "agile", "scrum",
    "stakeholder management", "cross-functional collaboration", "communication",
]

ALIASES = {
    "python": ["python", "python3"],
    "javascript": ["javascript", "js", "ecmascript"],
    "typescript": ["typescript", "ts"],
    "postgresql": ["postgresql", "postgres", "postgres db"],
    "fastapi": ["fastapi", "fast api"],
    "react": ["react", "react.js", "reactjs"],
    "node.js": ["node.js", "nodejs", "node"],
    "machine learning": ["machine learning", "ml"],
    "deep learning": ["deep learning", "dl"],
    "cross-functional collaboration": [
        "cross-functional collaboration", "cross functional collaboration",
        "worked across teams", "cross-functional team",
    ],
}

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _local_pipeline_version() -> str:
    digest = hashlib.sha256()
    for path in (ROOT / "server.py", ROOT / "requirements.txt"):
        try:
            contents = path.read_bytes().replace(b"\r\n", b"\n")
        except OSError:
            continue
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(contents)
        digest.update(b"\0")
    digest.update(f"python={platform.python_implementation()}-{platform.python_version()}".encode("utf-8"))
    for distribution in ("pypdf", "python-docx", "Pillow", "lxml", "typing-extensions"):
        try:
            installed_version = installed_package_version(distribution)
        except PackageNotFoundError:
            installed_version = "missing"
        digest.update(f"{distribution}={installed_version}".encode("utf-8"))
        digest.update(b"\0")
    digest.update(f"ocr_model={OCR_MODEL}".encode("utf-8"))
    return f"local-{digest.hexdigest()[:58]}"


LOCAL_PIPELINE_VERSION = _local_pipeline_version()


def pipeline_version() -> str:
    configured = os.environ.get(PIPELINE_VERSION_ENV)
    if configured is not None:
        value = configured.strip()
        return value if PIPELINE_VERSION_RE.fullmatch(value) else "unversioned"
    return LOCAL_PIPELINE_VERSION


def local_bind_config() -> tuple[str, int]:
    """Keep the unauthenticated prototype on IPv4 loopback and validate its port."""
    host = os.environ.get("RECRUITMENT_COPILOT_HOST", DEFAULT_HOST).strip()
    if host != DEFAULT_HOST:
        raise SystemExit(
            "MVP lokal hanya boleh bind ke 127.0.0.1; autentikasi dan kontrol akses jaringan belum tersedia."
        )
    raw_port = os.environ.get("RECRUITMENT_COPILOT_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("RECRUITMENT_COPILOT_PORT harus berupa angka 1–65535.") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("RECRUITMENT_COPILOT_PORT harus berupa angka 1–65535.")
    return DEFAULT_HOST, port


def shutdown_grace_config() -> int:
    raw = os.environ.get(SHUTDOWN_GRACE_ENV, str(DEFAULT_SHUTDOWN_GRACE_SECONDS)).strip()
    try:
        seconds = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{SHUTDOWN_GRACE_ENV} harus berupa angka 0–{MAX_SHUTDOWN_GRACE_SECONDS}.") from exc
    if not 0 <= seconds <= MAX_SHUTDOWN_GRACE_SECONDS:
        raise SystemExit(f"{SHUTDOWN_GRACE_ENV} harus berupa angka 0–{MAX_SHUTDOWN_GRACE_SECONDS}.")
    return seconds


def begin_graceful_shutdown(http_server: ThreadingHTTPServer, grace_seconds: int) -> bool:
    """Fail readiness, allow probes to observe drain, then stop accepting requests."""
    if DRAINING.is_set():
        return False
    DRAINING.set()

    def stop_after_grace() -> None:
        if grace_seconds:
            time.sleep(grace_seconds)
        http_server.shutdown()

    threading.Thread(target=stop_after_grace, name="http-shutdown", daemon=True).start()
    return True


def request_shutdown_for_signal(
    http_server: ThreadingHTTPServer,
    grace_seconds: int,
    signum: int,
) -> bool:
    """Apply the registered signal callback's logging and drain behavior."""
    signal_name = signal.Signals(signum).name
    print(
        f"\n{signal_name} diterima; readiness dimatikan selama drain "
        f"{grace_seconds} detik sebelum listener berhenti menerima request."
    )
    return begin_graceful_shutdown(http_server, grace_seconds)


def register_shutdown_signal_handlers(
    http_server: ThreadingHTTPServer,
    grace_seconds: int,
) -> None:
    """Register the same drain callback for the process stop signals."""
    def handle_shutdown_signal(signum: int, _frame: object) -> None:
        request_shutdown_for_signal(http_server, grace_seconds, signum)

    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    signal.signal(signal.SIGINT, handle_shutdown_signal)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate_to_v1(db: sqlite3.Connection) -> None:
    """Create the MVP schema and upgrade its original jobs table in place."""
    statements = (
        """CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            department TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            criteria_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'awaiting_approval',
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            reviewer TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(job_id, role)
        )""",
        """CREATE TABLE IF NOT EXISTS candidates (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            file_type TEXT NOT NULL,
            profile_json TEXT NOT NULL,
            score REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'needs_review',
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS evidence (
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
        )""",
        """CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
            reviewer TEXT NOT NULL,
            role TEXT NOT NULL,
            decision TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            candidate_id TEXT,
            actor TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
    )
    for statement in statements:
        db.execute(statement)
    job_columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
    if "status" not in job_columns:
        db.execute("ALTER TABLE jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'awaiting_approval'")
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_approvals_job_id ON approvals(job_id)",
        "CREATE INDEX IF NOT EXISTS idx_candidates_job_id ON candidates(job_id)",
        "CREATE INDEX IF NOT EXISTS idx_evidence_candidate_id ON evidence(candidate_id)",
        "CREATE INDEX IF NOT EXISTS idx_reviews_candidate_id ON reviews(candidate_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_job_created ON audit_events(job_id, created_at)",
    ):
        db.execute(statement)


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {1: migrate_to_v1}


def init_db() -> None:
    with connect() as db:
        version = int(db.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema {version} is newer than this app supports ({SCHEMA_VERSION})."
            )
        while version < SCHEMA_VERSION:
            target_version = version + 1
            migration = MIGRATIONS.get(target_version)
            if migration is None:
                raise RuntimeError(f"Migration database v{target_version} tidak tersedia.")
            db.execute("BEGIN IMMEDIATE")
            try:
                migration(db)
                db.execute(f"PRAGMA user_version = {target_version}")
                db.commit()
            except BaseException:
                db.rollback()
                raise
            version = target_version
        try:
            from interview_service import init_interview_tables
            init_interview_tables(db)
        except Exception:
            pass


def database_readiness() -> tuple[bool, int | None]:
    """Check that the database answers a query and matches this app's schema."""
    try:
        with connect() as db:
            version = int(db.execute("PRAGMA user_version").fetchone()[0])
            query_ok = db.execute("SELECT 1").fetchone()[0] == 1
            return version == SCHEMA_VERSION and query_ok, version
    except (OSError, sqlite3.Error):
        return False, None


def metrics_snapshot() -> dict:
    with METRICS_LOCK:
        requests = [
            {"method": method, "route": route, "status": status, "count": count}
            for (method, route, status), count in sorted(
                HTTP_REQUEST_COUNTS.items(),
                key=lambda item: (item[0][0], item[0][1], item[0][2] or 0),
            )
        ]
        response_bytes = HTTP_RESPONSE_BYTES_TOTAL
        uploads_active = UPLOADS_ACTIVE
        upload_busy_rejections = UPLOAD_BUSY_REJECTIONS_TOTAL
        http_handlers_active = HTTP_HANDLERS_ACTIVE
        http_handler_rejections = HTTP_HANDLER_REJECTIONS_TOTAL
    return {
        "scope": "process",
        "uptime_seconds": max(0, int(time.monotonic() - PROCESS_STARTED_AT)),
        "http_requests_total": requests,
        "http_response_bytes_total": response_bytes,
        "uploads_active": uploads_active,
        "upload_busy_rejections_total": upload_busy_rejections,
        "http_handlers_active": http_handlers_active,
        "http_handler_rejections_total": http_handler_rejections,
        "http_handlers_limit": MAX_CONCURRENT_HTTP_HANDLERS,
    }


def audit(db: sqlite3.Connection, job_id: str, actor: str, event_type: str,
          candidate_id: str | None = None, details: dict | None = None) -> None:
    db.execute(
        "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_id("evt"), job_id, candidate_id, actor, event_type,
         json.dumps(details or {}, ensure_ascii=False), now()),
    )


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("–", "-")).strip()


EDUCATION_MENTION_RE = re.compile(
    r"(?<!\w)(?:"
    r"doctor(?:ate|al)?(?:\s+of\s+(?:philosophy|medicine|education))?|"
    r"ph\.?\s*d\.?|dphil|"
    r"master(?:['’]s(?:\s+degree)?|\s+degree|\s+(?:of|in)\s+(?:arts|science|engineering|education|business\s+administration))|"
    r"m\.?\s*s\.?|m\.?\s*sc\.?|m\.?\s*a\.?|m\.?\s*eng\.?|mba|"
    r"bachelor(?:'s)?(?:\s+(?:degree|of\s+(?:arts|science|engineering|education|business\s+administration)))?|"
    r"b\.?\s*s\.?|b\.?\s*sc\.?|b\.?\s*a\.?|b\.?\s*eng\.?|bsc|"
    r"associate\s+diploma|associate(?:['’]s(?:\s+degree)?|\s+degree|\s+of\s+(?:arts|science|engineering))|"
    r"(?:(?:professional|foundation|associate|secondary\s+vocational|higher)\s+)?"
    r"diploma(?:\s+of\s+higher\s+education)?|"
    r"(?:(?:foundation|higher\s+secondary|vocational)\s+)?"
    r"foundation\s+certificate|higher\s+secondary\s+certificate|vocational\s+certificate|"
    r"certificate\s+of\s+completion|"
    r"sarjana(?:\s+terapan)?|magister|doktor|s[1-3]|d[1-4]"
    r")(?![\w])",
    re.IGNORECASE,
)


def education_mentions(text: str) -> list[str]:
    """Return recognized credential wording as written, without equating systems."""
    mentions: list[tuple[int, int, str]] = []
    for match in EDUCATION_MENTION_RE.finditer(text):
        start, end = match.span()
        # Prefer the longer phrase when a short credential token is contained in it.
        if any(start >= prior_start and end <= prior_end for prior_start, prior_end, _ in mentions):
            continue
        mentions = [
            prior for prior in mentions
            if not (prior[0] >= start and prior[1] <= end)
        ]
        mentions.append((start, end, re.sub(r"\s+", " ", match.group(0)).strip()))
    return [mention for _, _, mention in sorted(mentions)]


def redact_for_evidence(value: str, focus_terms: list[str] | None = None) -> str:
    """Redact direct identifiers and keep long evidence excerpts near matched terms."""
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
        line = AGE_VALUE_RE.sub("[age removed]", line)
        line = re.sub(
            r"\b(?:DOB|date of birth|birthday|(?:tempat\s*[,/]\s*)?tanggal\s+lahir|"
            r"tempat\s+lahir|tgl\.?\s*lahir|TTL)\s*[:|-]?\s*[^;|]+",
            "[birth date removed]", line, flags=re.IGNORECASE,
        )
        lines.append(line)
    flattened = " ".join(" ".join(lines).split())
    if len(flattened) <= 700:
        return flattened

    normalized_flattened = normalize(flattened)
    focus_positions = []
    for term in focus_terms or []:
        term = normalize(term)
        if not term:
            continue
        match = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized_flattened)
        if match:
            focus_positions.append(match.span())
    if not focus_positions:
        return flattened[:700]

    context = 160
    while True:
        intervals = sorted(
            (max(0, start - context), min(len(flattened), end + context))
            for start, end in focus_positions
        )
        merged: list[list[int]] = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        excerpt = " … ".join(
            ("…" if start else "") + flattened[start:end] + ("…" if end < len(flattened) else "")
            for start, end in merged
        )
        if len(excerpt) <= 700 or context == 0:
            return excerpt[:700]
        context = max(0, context - 20)


def _docx_block_lines(container) -> Iterator[str]:
    """Read DOCX paragraphs and tables in body order, including nested tables."""
    for block in container.iter_inner_content():
        rows = getattr(block, "rows", None)
        if rows is None:
            for line in getattr(block, "text", "").splitlines():
                if line.strip():
                    yield line.strip()
            continue

        for row in rows:
            cell_texts = []
            seen_cells = set()
            for cell in row.cells:
                # Merged cells can appear more than once in python-docx's row view.
                cell_element = cell._tc
                if cell_element in seen_cells:
                    continue
                seen_cells.add(cell_element)
                cell_text = " ".join(_docx_block_lines(cell)).strip()
                if cell_text:
                    cell_texts.append(cell_text)
            if cell_texts:
                yield " | ".join(cell_texts)


class DocumentTextLimitError(ValueError):
    """Raised when extracted document text exceeds the parser work budget."""


def _assign_pdf_worker_job(process: subprocess.Popen[bytes]) -> int | None:
    """Apply a Windows Job Object memory limit before the worker receives a PDF."""
    if os.name != "nt":
        return None

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", ctypes.c_ulong),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_ulong),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_ulong),
            ("SchedulingClass", ctypes.c_ulong),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        raise OSError("Could not create PDF parser job.")
    process_handle = None
    try:
        limits = ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = (
            0x00000100 | 0x00000200 | 0x00002000  # process + job memory, then kill on close
        )
        limits.ProcessMemoryLimit = MAX_PDF_WORKER_MEMORY_BYTES
        limits.JobMemoryLimit = MAX_PDF_WORKER_MEMORY_BYTES
        if not kernel32.SetInformationJobObject(
            job_handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            raise OSError("Could not set PDF parser memory limit.")
        process_handle = kernel32.OpenProcess(0x0001 | 0x0100, False, process.pid)
        if not process_handle or not kernel32.AssignProcessToJobObject(job_handle, process_handle):
            raise OSError("Could not assign PDF parser to its memory-limited job.")
        return int(job_handle)
    except Exception:
        kernel32.CloseHandle(job_handle)
        raise
    finally:
        if process_handle:
            kernel32.CloseHandle(process_handle)


def _close_pdf_worker_job(job_handle: int | None) -> None:
    if job_handle and os.name == "nt":
        ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(ctypes.c_void_p(job_handle))


def _pdf_worker_environment() -> dict[str, str]:
    """Keep runtime essentials only; PDF parsing does not need application secrets."""
    allowed_names = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR"}
    return {name: value for name, value in os.environ.items() if name.upper() in allowed_names}


def _run_pdf_parser_worker(payload: bytes) -> tuple[list[tuple[int, str]], list[tuple[int, bytes]]]:
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("File melampaui batas unggahan 8 MB.")
    worker_path = ROOT / "pdf_parser_worker.py"
    command = [
        sys.executable,
        str(worker_path),
        str(MAX_PDF_PAGES),
        str(MAX_EXTRACTED_TEXT_CHARACTERS),
        str(MAX_OCR_IMAGES_PER_PDF),
        str(MAX_UPLOAD_BYTES),
        str(MAX_PDF_DECODED_STREAM_BYTES),
        str(MAX_PDF_OCR_IMAGES_TOTAL_BYTES),
    ]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_pdf_worker_environment(),
        )
    except OSError as exc:
        raise ValueError("Parser PDF terisolasi tidak dapat dijalankan.") from exc

    job_handle = None
    try:
        try:
            job_handle = _assign_pdf_worker_job(process)
        except Exception as exc:
            process.kill()
            process.communicate()
            raise ValueError("Batas memori parser PDF tidak dapat diterapkan.") from exc
        try:
            output, _ = process.communicate(payload, timeout=MAX_PDF_WORKER_SECONDS)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise ValueError("Parsing PDF melampaui batas waktu yang diizinkan.") from exc
    finally:
        _close_pdf_worker_job(job_handle)

    if process.returncode != 0 or len(output) > MAX_PDF_WORKER_RESULT_BYTES:
        raise ValueError("PDF rusak atau melampaui batas sumber daya parser.")
    try:
        response = json.loads(output.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PDF rusak atau tidak dapat dibaca.") from exc
    if not isinstance(response, dict):
        raise ValueError("PDF rusak atau tidak dapat dibaca.")
    if not response.get("ok"):
        message = response.get("error")
        if isinstance(message, str) and len(message) <= 256:
            raise ValueError(message)
        raise ValueError("PDF rusak atau tidak dapat dibaca.")

    raw_pages = response.get("pages")
    raw_images = response.get("images")
    if not isinstance(raw_pages, list) or not isinstance(raw_images, list):
        raise ValueError("PDF rusak atau tidak dapat dibaca.")
    pages: list[tuple[int, str]] = []
    images: list[tuple[int, bytes]] = []
    total_image_bytes = 0
    try:
        for item in raw_pages:
            if (
                not isinstance(item, list)
                or len(item) != 2
                or not isinstance(item[0], int)
                or not isinstance(item[1], str)
            ):
                raise ValueError("PDF rusak atau tidak dapat dibaca.")
            pages.append((item[0], item[1]))
        for item in raw_images:
            if (
                not isinstance(item, list)
                or len(item) != 2
                or not isinstance(item[0], int)
                or not isinstance(item[1], str)
            ):
                raise ValueError("PDF rusak atau tidak dapat dibaca.")
            image_data = base64.b64decode(item[1], validate=True)
            total_image_bytes += len(image_data)
            if total_image_bytes > MAX_PDF_OCR_IMAGES_TOTAL_BYTES:
                raise ValueError("PDF melebihi batas ukuran total gambar untuk OCR.")
            images.append((item[0], image_data))
    except (ValueError, base64.binascii.Error) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("PDF melebihi batas"):
            raise
        raise ValueError("PDF rusak atau tidak dapat dibaca.") from exc
    return pages, images


def _append_bounded_text_lines(
    pages: list[tuple[int | None, str]],
    text: str,
    page_number: int | None,
    total_characters: int,
) -> int:
    total_characters += len(text)
    if total_characters > MAX_EXTRACTED_TEXT_CHARACTERS:
        raise DocumentTextLimitError("Dokumen melampaui batas teks hasil ekstraksi.")

    start = 0
    for boundary in DOCUMENT_LINE_BREAK_RE.finditer(text):
        line = text[start:boundary.start()]
        start = boundary.end()
        if line.strip():
            pages.append((page_number, line))
            if len(pages) > MAX_EXTRACTED_NONEMPTY_LINES:
                raise DocumentTextLimitError("Dokumen melampaui batas teks hasil ekstraksi.")
    if start < len(text):
        line = text[start:]
        if line.strip():
            pages.append((page_number, line))
            if len(pages) > MAX_EXTRACTED_NONEMPTY_LINES:
                raise DocumentTextLimitError("Dokumen melampaui batas teks hasil ekstraksi.")
    return total_characters
def extract_document(filename: str, payload: bytes) -> tuple[str, list[tuple[int | None, str]]]:
    ext = Path(filename).suffix.lower()
    total_characters = 0
    if ext == ".txt":
        text = payload.decode("utf-8", errors="replace")
        pages = []
        total_characters = _append_bounded_text_lines(pages, text, 1, total_characters)
        if not pages:
            raise ValueError("File TXT tidak berisi teks yang dapat diproses.")
    elif ext in (".png", ".jpg", ".jpeg"):
        expected_format = "PNG" if ext == ".png" else "JPEG"
        image = normalize_image(payload, expected_format=expected_format)
        text = call_ocr(image)
        pages = []
        total_characters = _append_bounded_text_lines(pages, text, 1, total_characters)
    elif ext == ".pdf":
        pdf_text_pages, pdf_ocr_images = _run_pdf_parser_worker(payload)
        pages = []
        for page_num, text in pdf_text_pages:
            total_characters = _append_bounded_text_lines(pages, text, page_num, total_characters)
        if pdf_ocr_images:
            if not ocr_is_configured():
                raise ValueError(
                    f"PDF ini perlu OCR. Atur {OCR_KEY_ENV}, {OCR_URL_ENV}, dan "
                    f"{OCR_ALLOWED_ORIGINS_ENV} atau instal backend PaddleOCR lokal."
                )
            if OCR_BACKEND == "api":
                reserve_ocr_calls(len(pdf_ocr_images))
            for page_num, image in pdf_ocr_images:
                text = call_ocr(image, reservation_made=(OCR_BACKEND == "api"))
                total_characters = _append_bounded_text_lines(pages, text, page_num, total_characters)
        if not pages:
            raise ValueError("Tidak ada teks yang berhasil diekstrak dari PDF.")
    elif ext == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ValueError("DOCX reader tidak tersedia di runtime ini.") from exc
        validate_docx_package(payload)
        try:
            doc = Document(io.BytesIO(payload))
            pages = []
            for line in _docx_block_lines(doc):
                total_characters = _append_bounded_text_lines(pages, line, None, total_characters)
        except DocumentTextLimitError:
            raise
        except Exception as exc:
            raise ValueError("DOCX rusak atau tidak dapat dibaca.") from exc
        if not pages:
            raise ValueError("DOCX tidak berisi teks yang dapat diproses.")
    else:
        raise ValueError("Format belum didukung. Unggah TXT, PDF teks, atau DOCX.")
    return ext[1:], pages


def validate_docx_package(payload: bytes) -> None:
    """Bound DOCX ZIP expansion before python-docx parses its XML parts."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) > MAX_DOCX_ZIP_MEMBERS:
                raise ValueError(f"DOCX melebihi batas {MAX_DOCX_ZIP_MEMBERS} komponen.")
            expanded_bytes = sum(member.file_size for member in members)
            if expanded_bytes > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ValueError("DOCX melebihi batas ukuran hasil ekstraksi yang diizinkan.")
            names = {member.filename for member in members}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("Paket DOCX tidak memiliki komponen dokumen utama.")
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError("File DOCX bukan paket ZIP yang valid.") from exc


def normalize_image(payload: bytes, expected_format: str | None = None) -> bytes:
    """Validate and convert an uploaded or embedded image to a compact PNG."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(payload)) as image:
            if image.format not in ("PNG", "JPEG"):
                raise ValueError("Format gambar harus PNG atau JPEG.")
            if expected_format is not None and image.format != expected_format:
                raise ValueError("Format isi gambar tidak cocok dengan ekstensi file.")
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Resolusi gambar melebihi batas yang diizinkan untuk OCR.")
            image.thumbnail((2200, 2200))
            image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Gambar tidak valid atau formatnya tidak didukung OCR.") from exc
    encoded_image = output.getvalue()
    if len(encoded_image) > MAX_UPLOAD_BYTES:
        raise ValueError("Gambar hasil normalisasi melebihi batas OCR 8 MB.")
    return encoded_image


def reserve_ocr_calls(count: int) -> None:
    """Enforce the OCR service's six-request rolling-minute limit locally."""
    if count <= 0:
        return
    if count > OCR_REQUESTS_PER_MINUTE:
        raise ValueError("OCR menerima maksimal 6 gambar per menit. PDF ini memiliki terlalu banyak halaman scan untuk satu proses.")
    current = time.monotonic()
    with OCR_LOCK:
        while OCR_CALLS and current - OCR_CALLS[0] >= 60:
            OCR_CALLS.popleft()
        if len(OCR_CALLS) + count > OCR_REQUESTS_PER_MINUTE:
            retry_after = max(1, int(60 - (current - OCR_CALLS[0])))
            raise ValueError(f"Batas OCR lokal 6 request/menit tercapai. Coba lagi sekitar {retry_after} detik.")
        OCR_CALLS.extend([current] * count)


def _parse_ocr_https_url(raw_url: str):
    if not raw_url or any(ord(char) <= 32 or char == "\\" for char in raw_url):
        raise ValueError("URL OCR tidak valid. Gunakan URL HTTPS internal yang sah.")
    try:
        parsed = urlsplit(raw_url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL OCR tidak valid. Gunakan URL HTTPS internal yang sah.") from exc
    if port is None:
        port = 443
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "?" in raw_url
        or "#" in raw_url
        or port < 1
        or port > 65535
        or "%" in hostname
    ):
        raise ValueError("URL OCR harus HTTPS dan tidak boleh memuat user/password, query, atau fragment.")
    try:
        normalized_host = ipaddress.ip_address(hostname).compressed
    except ValueError:
        try:
            normalized_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise ValueError("URL OCR tidak valid. Gunakan URL HTTPS internal yang sah.") from exc
        labels = normalized_host.split(".")
        if not normalized_host or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in labels
        ):
            raise ValueError("URL OCR tidak valid. Gunakan URL HTTPS internal yang sah.")
    return parsed, (normalized_host, port)


def _approved_ocr_origin_keys() -> set[tuple[str, int]]:
    configured = os.environ.get(OCR_ALLOWED_ORIGINS_ENV, "").strip()
    if not configured:
        raise ValueError(
            f"OCR belum dikonfigurasi. Set {OCR_ALLOWED_ORIGINS_ENV} ke origin HTTPS yang disetujui."
        )
    approved = set()
    for raw_origin in configured.split(","):
        origin = raw_origin.strip()
        if not origin:
            raise ValueError(f"Daftar origin OCR {OCR_ALLOWED_ORIGINS_ENV} tidak valid.")
        parsed, origin_key = _parse_ocr_https_url(origin)
        if parsed.path not in ("", "/"):
            raise ValueError(f"Daftar origin OCR {OCR_ALLOWED_ORIGINS_ENV} hanya boleh berisi origin HTTPS.")
        approved.add(origin_key)
    return approved


def _require_approved_ocr_origin(origin_key: tuple[str, int]) -> None:
    if origin_key not in _approved_ocr_origin_keys():
        raise ValueError(
            f"Origin endpoint OCR tidak ada dalam daftar {OCR_ALLOWED_ORIGINS_ENV} yang disetujui."
        )


def ocr_is_configured() -> bool:
    if not os.environ.get(OCR_KEY_ENV, "").strip():
        return False
    raw_url = os.environ.get(OCR_URL_ENV, "").strip().rstrip("/")
    if not raw_url:
        return False
    try:
        _, origin_key = _parse_ocr_https_url(raw_url)
        _require_approved_ocr_origin(origin_key)
    except ValueError:
        return False
    return True


def call_ocr_api(png_image: bytes, reservation_made: bool = False) -> str:
    api_key = os.environ.get(OCR_KEY_ENV, "").strip()
    if not api_key:
        raise ValueError(f"OCR belum dikonfigurasi. Atur environment variable {OCR_KEY_ENV} lalu jalankan ulang server.")
    base_url = os.environ.get(OCR_URL_ENV, "").strip().rstrip("/")
    if not base_url:
        raise ValueError(f"OCR belum dikonfigurasi. Atur environment variable {OCR_URL_ENV}.")
    _, origin_key = _parse_ocr_https_url(base_url)
    _require_approved_ocr_origin(origin_key)
    if not reservation_made:
        reserve_ocr_calls(1)
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    image_b64 = base64.b64encode(png_image).decode("ascii")
    payload = {
        "model": OCR_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Extract all text from this image. Preserve the original wording and line breaks."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]}],
        "max_tokens": 500,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        # OCR egress must not inherit an ambient environment or Windows proxy
        # while the proxy route and TLS inspection remain unapproved.
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _RejectOCRRedirects(),
        )
        with OCR_SEMAPHORE:
            with opener.open(request, timeout=45) as response:
                response_chunks = []
                response_size = 0
                while response_size <= MAX_OCR_RESPONSE_BYTES:
                    chunk = response.read(min(64 * 1024, MAX_OCR_RESPONSE_BYTES + 1 - response_size))
                    if not chunk:
                        break
                    response_size += len(chunk)
                    if response_size > MAX_OCR_RESPONSE_BYTES:
                        raise ValueError("Respons OCR melebihi batas 1 MiB; dokumen tidak disimpan.")
                    response_chunks.append(chunk)
                response_body = b"".join(response_chunks)
                result = json.loads(response_body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ValueError("API OCR membatasi request. Tunggu sebentar lalu coba lagi.") from exc
        if 300 <= exc.code < 400:
            raise ValueError("API OCR mengalihkan request; gunakan URL endpoint langsung.") from exc
        raise ValueError(f"API OCR merespons HTTP {exc.code}; dokumen tidak disimpan.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError("API OCR tidak dapat dijangkau dari server lokal.") from exc
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Respons OCR tidak berisi choices[0].message.content.") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValueError("OCR tidak menemukan teks yang bisa diproses.")
    return content


def call_ocr(png_image: bytes, reservation_made: bool = False) -> str:
    if OCR_BACKEND == "paddle":
        try:
            from ocr_local import recognize_png
            return recognize_png(png_image)
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc
    if OCR_BACKEND == "api":
        return call_ocr_api(png_image, reservation_made=reservation_made)
    raise ValueError("Backend OCR tidak valid. Gunakan 'paddle' atau 'api'.")


def ocr_is_configured() -> bool:
    if OCR_BACKEND == "paddle":
        try:
            return importlib.util.find_spec("paddleocr") is not None and importlib.util.find_spec("paddle") is not None
        except (ImportError, ValueError):
            return False
    if OCR_BACKEND == "api":
        return bool(os.environ.get(OCR_KEY_ENV) and os.environ.get(OCR_URL_ENV))
    return False


def profile_from_text(text: str) -> dict:
    profile_text = profile_text_without_labeled_sensitive_lines(text)
    ntext = normalize(profile_text)
    skills = [
        skill for skill in SKILLS
        if has_positive_alias_mention(ntext, skill)
    ]
    duration = next(
        (
            match for match in EXPERIENCE_DURATION_RE.finditer(ntext)
            if not AGE_DURATION_PREFIX_RE.search(ntext[max(0, match.start() - 40):match.start()])
            and not AGE_DURATION_SUFFIX_RE.match(ntext[match.end():match.end() + 20])
        ),
        None,
    )
    years = None
    if duration:
        amount = duration.group("amount").rstrip("+")
        if amount in ("a couple of", "couple of"):
            amount_value = 2
        elif amount in ("a few", "few", "several"):
            amount_value = None
        elif amount in ("a", "an"):
            amount_value = 1
        elif amount.isdigit():
            amount_value = int(amount)
        elif re.fullmatch(r"\d{1,2}[.,]\d{1,2}", amount):
            amount_value = float(amount.replace(",", "."))
        else:
            amount_value = EXPERIENCE_NUMBER_WORDS.get(amount)
        if amount_value is not None:
            years = amount_value * (10 if duration.group("unit").startswith("decade") else 1)
    degrees = education_mentions(profile_text)
    return {
        "skills": skills,
        "experience_years_mentioned": years,
        "experience_duration_text": duration.group(0) if duration else None,
        "education_levels_mentioned": degrees,
    }


def criterion_aliases(label: str) -> list[str]:
    base = normalize(label)
    found = [base]
    for key, aliases in ALIASES.items():
        if base == key or base in aliases:
            found.extend(aliases)
    return list(dict.fromkeys(term for term in found if term))


def alias_mention_is_negated(text: str, match: re.Match[str]) -> bool:
    """Catch short, direct English or Indonesian negation cues before a skill mention."""
    prefix = text[max(0, match.start() - 120):match.start()]
    prefix = re.split(r"[.!?;,]", prefix)[-1]
    cues = list(NEGATION_CUE_RE.finditer(prefix))
    if not cues:
        return False
    cue = cues[-1]
    between = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", prefix[cue.end():])
    if len(between) > 6:
        return False
    cue_word = cue.group(0).casefold()
    if cue_word in {"not", "bukan"} and between and between[0] in {"only", "just", "hanya", "sekadar", "cuma"}:
        return False
    if cue_word == "kurang" and between and between[0] in {"lebih", "dari"}:
        return False
    return True


def has_positive_alias_mention(text: str, alias: str) -> bool:
    pattern = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)")
    return any(not alias_mention_is_negated(text, match) for match in pattern.finditer(text))


def match_criterion(criterion: dict, pages: list[tuple[int | None, str]]) -> dict:
    aliases = criterion_aliases(criterion["label"])
    tokens = [t for t in re.findall(r"[a-z0-9+#.]+", normalize(criterion["label"])) if len(t) > 1]
    exact = []
    partial = []
    negated = []
    for page_num, line in pages:
        normalized_line = normalize(line)
        alias_matches = [
            match
            for alias in aliases
            for match in re.finditer(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized_line)
        ]
        if alias_matches:
            positive_matches = [
                match for match in alias_matches
                if not alias_mention_is_negated(normalized_line, match)
            ]
            negative_matches = [
                match for match in alias_matches
                if alias_mention_is_negated(normalized_line, match)
            ]
            if positive_matches:
                exact.append((page_num, line, positive_matches[0].group(0)))
            if negative_matches:
                negated.append((page_num, line, negative_matches[0].group(0)))
            continue
        present_tokens = [
            token for token in tokens
            if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", normalized_line)
        ]
        if len(tokens) >= 2 and len(present_tokens) >= max(2, (len(tokens) + 1) // 2):
            partial.append((page_num, line, present_tokens))
    if negated:
        page_num, line, focus_term = negated[0]
        return {"result": "needs_verification", "confidence": 0.0,
                "snippet": redact_for_evidence(line, [focus_term]), "page_number": page_num}
    if exact:
        page_num, line, focus_term = exact[0]
        snippet = redact_for_evidence(line, [focus_term])
        if not snippet:
            return {"result": "needs_verification", "confidence": 0.0,
                    "snippet": "", "page_number": page_num}
        # This value encodes lexical match strength only; it is not a probability.
        return {"result": "matched", "confidence": 1.0,
                "snippet": snippet, "page_number": page_num}
    if partial:
        page_num, line, focus_terms = partial[0]
        snippet = redact_for_evidence(line, focus_terms)
        if not snippet:
            return {"result": "needs_verification", "confidence": 0.0,
                    "snippet": "", "page_number": page_num}
        return {"result": "partial", "confidence": 0.5,
                "snippet": snippet, "page_number": page_num}
    return {"result": "unknown", "confidence": 0.0, "snippet": "", "page_number": None}


def score_candidate(criteria: list[dict], pages: list[tuple[int | None, str]]) -> tuple[float, list[dict]]:
    total_weight = sum(float(c["weight"]) for c in criteria) or 1.0
    matched_total = 0.0
    evidence_rows = []
    for criterion in criteria:
        result = match_criterion(criterion, pages)
        match_value = {
            "matched": 1.0,
            "partial": 0.5,
            "unknown": 0.0,
            "needs_verification": 0.0,
        }[result["result"]]
        matched_total += match_value * float(criterion["weight"])
        evidence_rows.append({**criterion, **result})
    return round(100 * matched_total / total_weight, 1), evidence_rows


def rank_retrieval(query: str, job: dict) -> list[dict]:
    """Small retrieval-only RAG baseline over approved requisition content."""
    criteria = json.loads(job["criteria_json"])
    sources = [
        {"source": "Deskripsi lowongan", "text": job["description"]},
        *[{"source": f"Kriteria: {c['label']}", "text": c["label"]} for c in criteria],
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


def multipart_file(handler: BaseHTTPRequestHandler) -> tuple[str, bytes]:
    length = request_content_length(handler)
    if length <= 0 or length > MAX_BODY_BYTES:
        handler.close_connection = True
        raise ValueError("Ukuran unggahan kosong atau melampaui batas 8 MB.")
    content_type = handler.headers.get("Content-Type", "").encode("ascii", "ignore")
    raw = read_request_body(handler, length)
    _preflight_single_file_multipart(content_type, raw)
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
    )
    parts = iter(message.iter_parts())
    part = next(parts, None)
    if part is None:
        raise ValueError("File tidak ditemukan pada permintaan unggah.")
    if part.get_content_disposition() != "form-data" or part.get_param("name", header="content-disposition") != "file":
        raise ValueError("Unggahan harus berisi satu bagian file bernama 'file'.")
    if part.get_content_maintype() in {"multipart", "message"}:
        raise ValueError("Format bagian file bertingkat tidak didukung.")
    if next(parts, None) is not None:
        raise ValueError("Unggahan harus berisi tepat satu file.")
    filename = part.get_filename() or "resume.txt"
    payload = part.get_payload(decode=True) or b""
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("Batas unggahan adalah 8 MB.")
    return filename, payload


def _preflight_single_file_multipart(content_type: bytes, raw: bytes) -> None:
    """Reject complex multipart structure before building the MIME message tree."""
    if not content_type or len(content_type) > 1024:
        raise ValueError("Header Content-Type unggahan tidak valid.")
    outer_headers = BytesHeaderParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type + b"\r\n\r\n"
    )
    if outer_headers.get_content_type() != "multipart/form-data":
        raise ValueError("Unggahan harus menggunakan multipart/form-data.")
    boundary = outer_headers.get_boundary()
    if not boundary:
        raise ValueError("Boundary multipart tidak ditemukan.")
    try:
        boundary_bytes = boundary.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Boundary multipart tidak valid.") from exc
    boundary_characters = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'()+_,-./:=?"
    if not 1 <= len(boundary_bytes) <= 70 or any(char not in boundary_characters for char in boundary_bytes):
        raise ValueError("Boundary multipart tidak valid.")

    delimiter = b"--" + boundary_bytes
    closing_delimiter = delimiter + b"--"
    body = io.BytesIO(raw)
    opening_line = body.readline(MAX_MULTIPART_HEADER_BYTES + 1)
    if opening_line.rstrip(b"\r\n") != delimiter:
        raise ValueError("Struktur multipart tidak valid.")

    header_lines: list[bytes] = []
    header_size = 0
    while True:
        line = body.readline(MAX_MULTIPART_HEADER_BYTES - header_size + 1)
        if not line:
            raise ValueError("Header bagian file tidak lengkap.")
        header_size += len(line)
        if header_size > MAX_MULTIPART_HEADER_BYTES:
            raise ValueError("Header bagian file melampaui batas.")
        if line.rstrip(b"\r\n") == b"":
            break
        if line[:1] in (b" ", b"\t") and not header_lines:
            raise ValueError("Header bagian file tidak valid.")
        if b":" not in line and line[:1] not in (b" ", b"\t"):
            raise ValueError("Header bagian file tidak valid.")
        header_lines.append(line)
        if len(header_lines) > MAX_MULTIPART_HEADER_LINES:
            raise ValueError("Header bagian file memiliki terlalu banyak baris.")

    part_headers = BytesHeaderParser(policy=policy.default).parsebytes(
        b"".join(header_lines) + b"\r\n"
    )
    dispositions = part_headers.get_all("Content-Disposition", [])
    if (
        len(dispositions) != 1
        or part_headers.get_content_disposition() != "form-data"
        or part_headers.get_param("name", header="Content-Disposition") != "file"
    ):
        raise ValueError("Unggahan harus berisi satu bagian file bernama 'file'.")
    content_types = part_headers.get_all("Content-Type", [])
    if len(content_types) > 1 or part_headers.get_content_maintype() in {"multipart", "message"}:
        raise ValueError("Format bagian file bertingkat tidak didukung.")

    closing_seen = False
    for line in body:
        normalized = line.rstrip(b"\r\n").rstrip(b" \t")
        if normalized == delimiter:
            raise ValueError("Unggahan harus berisi tepat satu file.")
        if normalized == closing_delimiter:
            if closing_seen:
                raise ValueError("Struktur multipart tidak valid.")
            closing_seen = True
            break
    if not closing_seen:
        raise ValueError("Penutup multipart tidak ditemukan.")
    while body.read(64 * 1024):
        raise ValueError("Data tambahan setelah penutup multipart tidak didukung.")


def insert_candidate(db: sqlite3.Connection, job_id: str, file_type: str,
                     pages: list[tuple[int | None, str]], criteria: list[dict],
                     source_key: str | None = None) -> tuple[str, float, dict]:
    whole_text = "\n".join(line for _, line in pages)
    profile = profile_from_text(whole_text)
    if source_key:
        profile["dataset_source"] = source_key
    score, matches = score_candidate(criteria, pages)
    candidate_id = new_id("cand")
    db.execute(
        "INSERT INTO candidates (id, job_id, file_type, profile_json, score, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (candidate_id, job_id, file_type, json.dumps(profile, ensure_ascii=False), score,
         "needs_review", now()),
    )
    for row in matches:
        db.execute("INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (new_id("ev"), candidate_id, row["id"], row["label"], row["type"], row["weight"],
                    row["result"], row["confidence"], row["snippet"], row["page_number"]))
    details = {"file_type": file_type, "evidence_count": len(matches), "score": score}
    if source_key:
        details["source"] = source_key
    audit(db, job_id, "system", "candidate_parsed", candidate_id, details)
    return candidate_id, score, profile


class Handler(BaseHTTPRequestHandler):
    server_version = "KarsaHire/0.1"

    def handle_one_request(self) -> None:
        # Generate a fresh opaque correlation ID for every request, including
        # multiple requests sent over one keep-alive connection.
        self.close_connection = True
        self.request_id = uuid.uuid4().hex
        self.rfile.begin_request()
        super().handle_one_request()

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_HEADER_IDLE_TIMEOUT_SECONDS)
        self.rfile.close()
        self.rfile = RequestHeadReader(self.connection)

    def version_string(self) -> str:
        return "KarsaHire"

    def send_error(self, code, message=None, explain=None) -> None:
        self.close_connection = True
        super().send_error(code, message, explain)

    def log_error(self, fmt: str, *args) -> None:
        # BaseHTTPRequestHandler's default error log includes the peer address.
        method = self.command if getattr(self, "command", None) in {
            "GET", "POST", "DELETE", "PUT", "PATCH", "HEAD", "OPTIONS",
        } else "OTHER"
        route = self.log_route() if getattr(self, "path", None) else "/<unparsed>"
        timed_out = fmt.startswith("Request timed out:")
        record = {
            "timestamp": now(),
            "severity": "WARNING",
            "event": "http_request_error",
            "reason": "timeout" if timed_out else "request_error",
            "method": method,
            "route": route,
        }
        request_id = getattr(self, "request_id", None)
        if request_id:
            record["request_id"] = request_id
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")), flush=True)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        request_id = getattr(self, "request_id", None)
        if request_id:
            self.send_header("X-Request-ID", request_id)
        super().end_headers()

    def log_route(self) -> str:
        path = urlsplit(self.path).path
        if path in (
            "/", "/index.html", "/app.js", "/app.css", "/approval.css",
            "/api/health", "/api/health/live", "/api/health/ready", "/api/metrics", "/api/jobs",
            "/api/criteria-recommendations",
        ):
            return path
        parts = [part for part in path.strip("/").split("/") if part]
        if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
            return "/api/jobs/:id"
        if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] in ("approvals", "candidates", "events", "ask", "load-synthetic-data", "load-demo-candidate", "analytics", "star-questions"):
            return f"/api/jobs/:id/{parts[3]}"
        if len(parts) == 3 and parts[:2] == ["api", "candidates"]:
            return "/api/candidates/:id"
        if len(parts) == 4 and parts[:2] == ["api", "candidates"] and parts[3] in ("reviews", "scorecards", "feedback"):
            return f"/api/candidates/:id/{parts[3]}"
        return "/<other>"

    def log_message(self, fmt: str, *args) -> None:
        # Never print the raw request line, which can contain candidate IDs or query values.
        method = self.command if self.command in {"GET", "POST", "DELETE", "PUT", "PATCH", "HEAD", "OPTIONS"} else "OTHER"
        status = args[1] if fmt == '"%s" %s %s' and len(args) == 3 and str(args[1]).isdigit() else "-"
        size = args[2] if fmt == '"%s" %s %s' and len(args) == 3 and str(args[2]).isdigit() else "-"
        if size == "-":
            size = getattr(self, "response_bytes", None)
        status_code = int(status) if status != "-" else None
        response_bytes = int(size) if size is not None and str(size).isdigit() else 0
        route = self.log_route()
        global HTTP_RESPONSE_BYTES_TOTAL
        with METRICS_LOCK:
            HTTP_REQUEST_COUNTS[(method, route, status_code)] += 1
            HTTP_RESPONSE_BYTES_TOTAL += response_bytes
        record = {
            "timestamp": now(),
            "severity": "ERROR" if status_code is not None and status_code >= 500 else (
                "WARNING" if status_code is not None and status_code >= 400 else "INFO"
            ),
            "event": "http_request",
            "method": method,
            "route": route,
            "status": status_code,
            "response_bytes": response_bytes if size is not None and str(size).isdigit() else None,
        }
        request_id = getattr(self, "request_id", None)
        if request_id:
            record["request_id"] = request_id
        print(json.dumps(record, ensure_ascii=False, separators=(",", ":")), flush=True)

    def send_json(self, status: int, payload: dict | list,
                  extra_headers: dict[str, str] | None = None) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.response_bytes = len(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.write_response_body(data)

    def write_response_body(self, body: bytes) -> None:
        try:
            self.wfile.write(body)
        except OSError:
            # Clients can disconnect while a response is being written; keep that
            # routine network condition from printing a server-thread traceback.
            self.close_connection = True

    def loopback_host(self) -> tuple[str, bool]:
        try:
            expected_port = self.server.server_address[1]
            host_values = self.headers.get_all("Host", [])
            if len(host_values) != 1:
                return "", False
            host_header = host_values[0]
            host = urlsplit(f"//{host_header}")
            host_name = (host.hostname or "").lower()
            allowed = (
                host_name in {"127.0.0.1", "localhost"}
                and host.port == expected_port
                and host.username is None
                and host.password is None
                and host.path == ""
                and not host.query
                and not host.fragment
            )
            return host_name, allowed
        except ValueError:
            return "", False

    def require_loopback_host(self) -> bool:
        _, allowed = self.loopback_host()
        if allowed:
            return True
        self.send_json(403, {"error": "Host harus menunjuk ke server lokal KarsaHire."})
        return False

    def require_same_origin_mutation(self) -> bool:
        """Block cross-site browser writes to the loopback API."""
        try:
            expected_port = self.server.server_address[1]
            host_name, valid_host = self.loopback_host()
            origin_values = self.headers.get_all("Origin", [])
            marker_values = self.headers.get_all("X-KarsaHire-Request", [])
            origin = urlsplit(origin_values[0] if len(origin_values) == 1 else "")
            same_origin = (
                len(origin_values) == 1
                and origin.scheme == "http"
                and (origin.hostname or "").lower() == host_name
                and (origin.port or 80) == expected_port
                and origin.username is None
                and origin.password is None
                and origin.path in ("", "/")
                and not origin.query
                and not origin.fragment
            )
            has_ui_marker = len(marker_values) == 1 and marker_values[0] == "same-origin-ui"
        except ValueError:
            valid_host = same_origin = has_ui_marker = False
        if valid_host and same_origin and has_ui_marker:
            return True
        # Do not drain an untrusted body: close instead of letting a rejected client
        # hold a request thread while slowly transmitting bytes.
        self.close_connection = True
        self.send_json(403, {"error": "Permintaan perubahan harus berasal dari UI lokal KarsaHire."})
        return False

    def read_json(self) -> dict:
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            self.close_connection = True
            raise ValueError("Content-Type harus application/json.")
        length = request_content_length(self)
        if length <= 0 or length > 1024 * 1024:
            self.close_connection = True
            raise ValueError("Permintaan kosong atau terlalu besar.")
        data = json.loads(read_request_body(self, length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Isi permintaan harus berupa objek JSON.")
        return data

    def do_GET(self) -> None:  # noqa: N802
        if not self.require_loopback_host():
            return
        path = urlsplit(self.path).path
        if DRAINING.is_set() and path not in (
            "/api/health/live", "/api/health/ready", "/api/health",
        ):
            self.send_json(503, {"error": "Server sedang dihentikan.", "draining": True})
            return
        static_types = {
            "landing.html": "text/html; charset=utf-8",
            "index.html": "text/html; charset=utf-8",
            "landing.css": "text/css; charset=utf-8",
            "landing.js": "text/javascript; charset=utf-8",
            "app.js": "text/javascript; charset=utf-8",
            "app.css": "text/css; charset=utf-8",
            "approval.css": "text/css; charset=utf-8",
            "role-templates.css": "text/css; charset=utf-8",
            "comparison.css": "text/css; charset=utf-8",
            "comparison.js": "text/javascript; charset=utf-8",
            "scorecard.css": "text/css; charset=utf-8",
            "scorecard.js": "text/javascript; charset=utf-8",
            "analytics-modal.css": "text/css; charset=utf-8",
            "analytics-modal.js": "text/javascript; charset=utf-8",
            "karsahire-shortlist-dashboard.png": "image/png",
            "karsahire-workflow-loop.gif": "image/gif",
            "karsahire-team-review.png": "image/png",
            "ATTRIBUTION.md": "text/markdown; charset=utf-8",
        }
        static_paths = {
            "/", "/index.html", "/app", "/app.html", "/landing.css", "/landing.js",
            "/app.js", "/app.css", "/approval.css", "/role-templates.css",
            "/comparison.css", "/comparison.js",
            "/scorecard.css", "/scorecard.js",
            "/analytics-modal.css", "/analytics-modal.js",
            "/assets/karsahire-shortlist-dashboard.png",
            "/assets/karsahire-workflow-loop.gif",
            "/assets/karsahire-team-review.png",
            "/assets/ATTRIBUTION.md",
        }
        if path in static_paths:
            if path in ("/", "/index.html"):
                filename = "landing.html"
            elif path in ("/app", "/app.html"):
                filename = "index.html"
            else:
                filename = path.rsplit("/", 1)[-1]
            target = WEB / "assets" / filename if path.startswith("/assets/") else WEB / filename
            types = static_types
            if not target.is_file():
                self.send_error(404)
                return
            body = target.read_bytes()
            self.response_bytes = len(body)
            self.send_response(200)
            self.send_header("Content-Type", types[filename])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.write_response_body(body)
            return
        if path == "/api/health/live":
            self.send_json(200, {"ok": True, "live": True, "draining": DRAINING.is_set()})
            return
        if path in ("/api/health", "/api/health/ready"):
            database_ready, schema_version = database_readiness()
            draining = DRAINING.is_set()
            ready = database_ready and not draining
            self.send_json(200 if ready else 503, {
                "ok": ready,
                "live": True,
                "ready": ready,
                "draining": draining,
                "database": "ready" if database_ready else "unavailable_or_wrong_schema",
                "schema_version": schema_version,
                "matching": "lexical-evidence-v1",
                "pipeline_version": pipeline_version(),
                "ocr_backend": OCR_BACKEND,
                "ocr_configured": ocr_is_configured(),
                "manual_uploads_enabled": MANUAL_UPLOADS_ENABLED,
                "external_llm": False,
            })
            return
        if path == "/api/metrics":
            self.send_json(200, metrics_snapshot())
            return
        if path == "/api/jobs":
            with connect() as db:
                jobs = db.execute(
                    "SELECT j.*, COUNT(c.id) AS candidate_count FROM jobs j "
                    "LEFT JOIN candidates c ON c.job_id=j.id GROUP BY j.id ORDER BY j.created_at DESC"
                ).fetchall()
            self.send_json(200, [{**dict(j), "criteria": json.loads(j["criteria_json"])} for j in jobs])
            return
        parts = [unquote(p) for p in path.strip("/").split("/")]
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "jobs":
            self.get_job(parts[2])
            return
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "events":
            with connect() as db:
                rows = db.execute("SELECT * FROM audit_events WHERE job_id=? ORDER BY created_at DESC LIMIT 100", (parts[2],)).fetchall()
            self.send_json(200, [{**dict(row), "details": json.loads(row["details_json"])} for row in rows])
            return
        if len(parts) == 5 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "export":
            if parts[4] == "csv":
                self.export_job_csv(parts[2])
                return
            if parts[4] == "json":
                self.export_job_json(parts[2])
                return
            if parts[4] == "dossier":
                self.export_job_dossier(parts[2])
                return
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "analytics":
            with connect() as db:
                try:
                    from analytics_service import get_hiring_analytics_summary
                    summary = get_hiring_analytics_summary(db, parts[2])
                    self.send_json(200, summary)
                except ValueError as exc:
                    self.send_json(404, {"error": str(exc)})
            return
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "star-questions":
            self.get_job_star_questions(parts[2])
            return
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "candidates" and parts[3] == "scorecards":
            with connect() as db:
                try:
                    from interview_service import get_candidate_scorecards, get_candidate_interview_summary
                    scorecards = get_candidate_scorecards(db, parts[2])
                    summary = get_candidate_interview_summary(db, parts[2])
                    self.send_json(200, {"scorecards": scorecards, "summary": summary})
                except Exception as exc:
                    self.send_json(400, {"error": str(exc)})
            return
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "candidates" and parts[3] == "feedback":
            with connect() as db:
                try:
                    from feedback_service import generate_candidate_feedback
                    feedback = generate_candidate_feedback(db, parts[2])
                    self.send_json(200, feedback)
                except ValueError as exc:
                    self.send_json(404, {"error": str(exc)})
                except Exception as exc:
                    self.send_json(500, {"error": str(exc)})
            return
        self.send_json(404, {"error": "Endpoint tidak ditemukan."})


    def get_job(self, job_id: str) -> None:
        with connect() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                self.send_json(404, {"error": "Lowongan tidak ditemukan."})
                return
            approvals = db.execute("SELECT reviewer, role, created_at FROM approvals WHERE job_id=? ORDER BY created_at", (job_id,)).fetchall()
            candidates = db.execute(
                f"SELECT * FROM candidates WHERE job_id=? ORDER BY {CANDIDATE_ORDER_BY_SQL}", (job_id,)
            ).fetchall()
            out = []
            synthetic_loaded = 0
            for candidate in candidates:
                item = dict(candidate)
                profile = json.loads(item.pop("profile_json"))
                source_key = profile.pop("dataset_source", None)
                if isinstance(source_key, str) and source_key.startswith(SYNTHETIC_DATASET_KEY_PREFIX):
                    synthetic_loaded += 1
                item["profile"] = profile
                item["evidence"] = [dict(row) for row in db.execute(
                    "SELECT * FROM evidence WHERE candidate_id=? ORDER BY weight DESC, criterion", (candidate["id"],)
                ).fetchall()]
                item["reviews"] = [dict(row) for row in db.execute(
                    "SELECT reviewer,role,decision,note,created_at FROM reviews WHERE candidate_id=? ORDER BY created_at DESC", (candidate["id"],)
                ).fetchall()]
                out.append(item)
        try:
            dataset_manifest = json.loads((SYNTHETIC_DATASET_DIR / "manifest.json").read_text(encoding="utf-8"))
            synthetic_available = len(dataset_manifest) if isinstance(dataset_manifest, list) else 0
        except (OSError, json.JSONDecodeError):
            synthetic_available = 0
        self.send_json(200, {**dict(job), "criteria": json.loads(job["criteria_json"]),
                             "approvals": [dict(row) for row in approvals], "candidates": out,
                             "synthetic_data": {"available": synthetic_available, "loaded": synthetic_loaded}})

    def export_job_csv(self, job_id: str) -> None:
        with connect() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                self.send_json(404, {"error": "Lowongan tidak ditemukan."})
                return
            candidates = db.execute(
                "SELECT * FROM candidates WHERE job_id=? ORDER BY score DESC, created_at ASC", (job_id,)
            ).fetchall()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow([
                "ID Kandidat",
                "Label",
                "Skor Evidence",
                "Status Review",
                "Format CV",
                "Pengalaman (Tahun)",
                "Pendidikan",
                "Skills",
                "Kriteria Cocok (Matched)",
                "Kriteria Parsial (Partial)",
                "Kriteria Belum Diketahui",
                "Reviewer Terakhir",
                "Peran Reviewer",
                "Keputusan Terakhir",
                "Catatan Reviewer",
                "Tanggal Unggah",
            ])
            status_map = {
                "needs_review": "Perlu review",
                "advance": "Lanjut proses",
                "needs_info": "Perlu informasi",
                "not_selected": "Tidak lanjut",
            }
            for candidate in candidates:
                profile = json.loads(candidate["profile_json"])
                evidence = db.execute(
                    "SELECT result, criterion FROM evidence WHERE candidate_id=?", (candidate["id"],)
                ).fetchall()
                matched_count = sum(1 for e in evidence if e["result"] == "matched")
                partial_count = sum(1 for e in evidence if e["result"] == "partial")
                unknown_count = sum(1 for e in evidence if e["result"] == "unknown")
                last_review = db.execute(
                    "SELECT reviewer, role, decision, note FROM reviews WHERE candidate_id=? ORDER BY created_at DESC LIMIT 1",
                    (candidate["id"],),
                ).fetchone()

                skills_str = ", ".join(profile.get("skills") or [])
                edu_str = ", ".join(profile.get("education_levels_mentioned") or [])
                exp_years = profile.get("experience_years_mentioned")
                exp_str = str(exp_years) if exp_years is not None else "-"
                cand_label = f"Kandidat · {candidate['id'][-4:].upper()}"
                status_label = status_map.get(candidate["status"], candidate["status"])

                writer.writerow([
                    candidate["id"],
                    cand_label,
                    f"{round(candidate['score'])}",
                    status_label,
                    candidate["file_type"].upper(),
                    exp_str,
                    edu_str,
                    skills_str,
                    matched_count,
                    partial_count,
                    unknown_count,
                    last_review["reviewer"] if last_review else "-",
                    last_review["role"] if last_review else "-",
                    status_map.get(last_review["decision"], last_review["decision"]) if last_review else "-",
                    last_review["note"] if last_review else "",
                    candidate["created_at"],
                ])

        safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", job["title"])[:30].strip("_") or "job"
        filename = f"rekap-kandidat-{safe_slug}-{job_id[:8]}.csv"
        content = output.getvalue()
        data = ("\ufeff" + content).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def export_job_json(self, job_id: str) -> None:
        with connect() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                self.send_json(404, {"error": "Lowongan tidak ditemukan."})
                return
            approvals = db.execute("SELECT reviewer, role, created_at FROM approvals WHERE job_id=? ORDER BY created_at", (job_id,)).fetchall()
            candidates = db.execute(
                "SELECT * FROM candidates WHERE job_id=? ORDER BY score DESC, created_at ASC", (job_id,)
            ).fetchall()
            out = []
            for candidate in candidates:
                item = dict(candidate)
                profile = json.loads(item.pop("profile_json"))
                item["profile"] = profile
                item["evidence"] = [dict(row) for row in db.execute(
                    "SELECT * FROM evidence WHERE candidate_id=? ORDER BY weight DESC, criterion", (candidate["id"],)
                ).fetchall()]
                item["reviews"] = [dict(row) for row in db.execute(
                    "SELECT reviewer,role,decision,note,created_at FROM reviews WHERE candidate_id=? ORDER BY created_at DESC", (candidate["id"],)
                ).fetchall()]
                out.append(item)

        payload = {
            "job_id": job["id"],
            "title": job["title"],
            "department": job["department"],
            "description": job["description"],
            "criteria": json.loads(job["criteria_json"]),
            "approvals": [dict(row) for row in approvals],
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "candidate_count": len(out),
            "candidates": out,
        }
        safe_slug = re.sub(r"[^a-zA-Z0-9_-]", "_", job["title"])[:30].strip("_") or "job"
        filename = f"debrief-kandidat-{safe_slug}-{job_id[:8]}.json"
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def export_job_dossier(self, job_id: str) -> None:
        with connect() as db:
            from dossier_service import generate_job_dossier_html
            try:
                html_content = generate_job_dossier_html(db, job_id)
            except ValueError as exc:
                self.send_json(404, {"error": str(exc)})
                return
            except Exception as exc:
                self.send_json(500, {"error": f"Gagal membuat dossier: {exc}"})
                return

        data = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def get_job_star_questions(self, job_id: str) -> None:
        with connect() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                self.send_json(404, {"error": "Lowongan tidak ditemukan."})
                return
            if job["status"] != "criteria_approved":
                self.send_json(409, {"error": "Panduan wawancara STAR hanya tersedia untuk lowongan yang telah disetujui kedua peran."})
                return
            criteria = json.loads(job["criteria_json"])
        from criteria_assistant import generate_star_interview_guide, audit_criteria_calibration
        guide = generate_star_interview_guide(criteria)
        calibration = audit_criteria_calibration(criteria)
        self.send_json(200, {
            "job_id": job_id,
            "title": job["title"],
            "department": job["department"],
            "status": job["status"],
            "criteria": criteria,
            "star_questions": guide,
            "calibration": calibration,
        })

    def get_criteria_recommendations_endpoint(self) -> None:
        data = self.read_json()
        title = str(data.get("title", "")).strip()[:160]
        department = str(data.get("department", "")).strip()[:120]
        if not title:
            raise ValueError("Nama posisi (title) wajib diisi.")
        from criteria_assistant import get_criteria_recommendations, audit_criteria_calibration
        recommendations = get_criteria_recommendations(title, department)
        calibration = audit_criteria_calibration(recommendations)
        self.send_json(200, {
            "title": title,
            "department": department,
            "recommendations": recommendations,
            "criteria": recommendations,
            "calibration": calibration,
        })

    def do_POST(self) -> None:  # noqa: N802
        if not self.require_same_origin_mutation():
            return
        if DRAINING.is_set():
            self.close_connection = True
            self.send_json(503, {"error": "Server sedang dihentikan.", "draining": True})
            return
        path = urlsplit(self.path).path
        try:
            parts = [unquote(p) for p in path.strip("/").split("/")]
            if path == "/api/jobs":
                self.create_job()
            elif path == "/api/criteria-recommendations":
                self.get_criteria_recommendations_endpoint()
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "approvals":
                self.approve_job(parts[2])
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "load-synthetic-data":
                self.load_synthetic_data(parts[2])
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "load-demo-candidate":
                self.load_demo_candidate(parts[2])
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "candidates":
                self.add_candidate(parts[2])
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "candidates" and parts[3] == "reviews":
                self.add_review(parts[2])
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "candidates" and parts[3] == "scorecards":
                self.add_scorecard(parts[2])
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "ask":
                self.ask_job(parts[2])

            else:
                self.close_connection = True
                self.send_json(404, {"error": "Endpoint tidak ditemukan."})
        except RequestBodyTimeout as exc:
            self.close_connection = True
            self.send_json(408, {"error": str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})
        except Exception as exc:  # keep internals out of API responses
            print(f"Request failed: {type(exc).__name__}")
            self.send_json(500, {"error": "Permintaan gagal diproses."})

    def create_job(self) -> None:
        data = self.read_json()
        title = str(data.get("title", "")).strip()[:160]
        department = str(data.get("department", "")).strip()[:120]
        description = str(data.get("description", "")).strip()[:12000]
        if not title:
            raise ValueError("Nama lowongan wajib diisi.")
        raw_criteria = data.get("criteria", [])
        if not isinstance(raw_criteria, list) or not raw_criteria:
            raise ValueError("Tambahkan setidaknya satu kriteria yang disepakati.")
        criteria = []
        for row in raw_criteria[:60]:
            label = str(row.get("label", "")).strip()[:180]
            kind = row.get("type", "required")
            if label and kind in ("required", "preferred"):
                criteria.append({"id": new_id("crit"), "label": label, "type": kind,
                                 "weight": 2.0 if kind == "required" else 1.0})
        if not criteria:
            raise ValueError("Kriteria tidak valid.")
        job_id = new_id("job")
        with connect() as db:
            db.execute("INSERT INTO jobs (id, title, department, description, criteria_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (job_id, title, department, description, json.dumps(criteria, ensure_ascii=False),
                        "awaiting_approval", now()))
            audit(db, job_id, "system", "criteria_submitted", details={"criteria_count": len(criteria)})
        self.send_json(201, {"id": job_id, "title": title, "criteria": criteria})

    def approve_job(self, job_id: str) -> None:
        data = self.read_json()
        reviewer = str(data.get("reviewer", "")).strip()[:100]
        role = data.get("role")
        if not reviewer or role not in ("recruiter", "hiring_manager"):
            raise ValueError("Nama approver dan peran recruiter/hiring manager wajib diisi.")
        with connect() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                self.send_json(404, {"error": "Requisition tidak ditemukan."})
                return
            if job["status"] == "criteria_approved":
                raise ValueError("Kriteria sudah disetujui kedua peran.")
            existing_role = db.execute("SELECT reviewer FROM approvals WHERE job_id=? AND role=?", (job_id, role)).fetchone()
            if existing_role:
                raise ValueError("Persetujuan untuk peran ini sudah tercatat.")
            other_role = db.execute("SELECT reviewer FROM approvals WHERE job_id=?", (job_id,)).fetchall()
            if any(row["reviewer"].casefold() == reviewer.casefold() for row in other_role):
                raise ValueError("Recruiter dan hiring manager harus memberikan persetujuan terpisah.")
            db.execute("INSERT INTO approvals VALUES (?, ?, ?, ?, ?)", (new_id("apr"), job_id, reviewer, role, now()))
            approval_count = db.execute("SELECT COUNT(*) FROM approvals WHERE job_id=?", (job_id,)).fetchone()[0]
            new_status = "criteria_approved" if approval_count == 2 else "awaiting_approval"
            db.execute("UPDATE jobs SET status=? WHERE id=?", (new_status, job_id))
            audit(db, job_id, reviewer, "criteria_approval_recorded", details={"role": role, "approved_count": approval_count})
        self.send_json(201, {"ok": True, "status": new_status})

    def add_candidate(self, job_id: str) -> None:
        global UPLOADS_ACTIVE, UPLOAD_BUSY_REJECTIONS_TOTAL
        if not MANUAL_UPLOADS_ENABLED:
            self.close_connection = True
            self.send_json(403, {
                "error": "Unggah CV manual dinonaktifkan. Gunakan fixture sintetis lokal untuk demo."
            })
            return
        with connect() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            self.send_json(404, {"error": "Lowongan tidak ditemukan."})
            return
        if job["status"] != "criteria_approved":
            self.send_json(409, {"error": "CV baru dapat diproses setelah recruiter dan hiring manager menyetujui kriteria."})
            return
        if not UPLOAD_SEMAPHORE.acquire(blocking=False):
            with METRICS_LOCK:
                UPLOAD_BUSY_REJECTIONS_TOTAL += 1
            self.send_json(503, {"error": "Server sedang memproses unggahan lain. Coba lagi sebentar."},
                           {"Retry-After": "2"})
            return
        with METRICS_LOCK:
            UPLOADS_ACTIVE += 1
        try:
            filename, payload = multipart_file(self)
            file_type, page_lines = extract_document(filename, payload)
            criteria = json.loads(job["criteria_json"])
            with connect() as db:
                candidate_id, score, profile = insert_candidate(db, job_id, file_type, page_lines, criteria)
            # Source bytes and full document text are not retained.
            self.send_json(201, {"id": candidate_id, "score": score, "profile": profile,
                                 "message": "CV diproses. Tinjau evidence sebelum mengambil keputusan."})
        finally:
            with METRICS_LOCK:
                UPLOADS_ACTIVE -= 1
            UPLOAD_SEMAPHORE.release()

    def load_demo_candidate(self, job_id: str) -> None:
        pages = [(None, line.strip()) for line in BUILTIN_DEMO_TEXT.splitlines() if line.strip()]
        candidate_id = None
        outcome = None
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                outcome = (404, {"error": "Requisition tidak ditemukan."})
            elif job["status"] != "criteria_approved":
                outcome = (409, {"error": "Setujui kriteria dengan recruiter dan hiring manager sebelum memuat fixture demo."})
            else:
                exists = any(
                    json.loads(row["profile_json"]).get("dataset_source") == BUILTIN_DEMO_SOURCE_KEY
                    for row in db.execute("SELECT profile_json FROM candidates WHERE job_id=?", (job_id,)).fetchall()
                )
                if not exists:
                    candidate_id, _score, _profile = insert_candidate(
                        db, job_id, "txt", pages, json.loads(job["criteria_json"]), BUILTIN_DEMO_SOURCE_KEY,
                    )
        if outcome:
            self.send_json(*outcome)
        elif candidate_id is None:
            self.send_json(200, {
                "ok": True,
                "added": False,
                "message": "Fixture demo sintetis sudah tersedia pada lowongan ini.",
            })
        else:
            self.send_json(201, {
                "ok": True,
                "added": True,
                "id": candidate_id,
                "message": "Fixture kandidat sintetis dimuat untuk demo lokal.",
            })

    def load_synthetic_data(self, job_id: str) -> None:
        with connect() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            self.send_json(404, {"error": "Requisition tidak ditemukan."})
            return
        if job["status"] != "criteria_approved":
            self.send_json(409, {"error": "Setujui kriteria dengan recruiter dan hiring manager sebelum memuat CV."})
            return

        manifest_path = SYNTHETIC_DATASET_DIR / "manifest.json"
        if not manifest_path.is_file():
            self.send_json(503, {"error": "Dataset uji lokal tidak tersedia di data/synthetic-cv-32."})
            return
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Manifest dataset uji tidak dapat dibaca.") from exc
        if not isinstance(manifest, list) or len(manifest) != SYNTHETIC_DATASET_SIZE:
            raise ValueError(f"Manifest dataset harus berisi tepat {SYNTHETIC_DATASET_SIZE} CV.")

        prepared = []
        seen_ids = set()
        for entry in manifest:
            sample_id = str(entry.get("sample_id", "")) if isinstance(entry, dict) else ""
            if not re.fullmatch(r"r\d{5}", sample_id) or sample_id in seen_ids:
                raise ValueError("Manifest berisi ID CV yang tidak valid atau duplikat.")
            seen_ids.add(sample_id)
            text_path = SYNTHETIC_DATASET_DIR / sample_id / "resume_text.txt"
            if not text_path.is_file():
                raise ValueError(f"Teks CV {sample_id} tidak tersedia; impor dibatalkan.")
            text = text_path.read_text(encoding="utf-8")
            if not text.strip() or len(text.encode("utf-8")) > MAX_UPLOAD_BYTES:
                raise ValueError(f"Teks CV {sample_id} kosong atau terlalu besar; impor dibatalkan.")
            pages = [(None, line.strip()) for line in text.splitlines() if line.strip()]
            if not pages:
                raise ValueError(f"Teks CV {sample_id} tidak berisi baris yang dapat diproses.")
            prepared.append({
                "sample_id": sample_id,
                "source_key": f"{SYNTHETIC_DATASET_KEY_PREFIX}{sample_id}",
                "pages": pages,
            })

        added = 0
        skipped = 0
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current_job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not current_job:
                self.send_json(404, {"error": "Requisition tidak ditemukan."})
                return
            if current_job["status"] != "criteria_approved":
                self.send_json(409, {"error": "Setujui kriteria sebelum memuat CV."})
                return
            existing = set()
            for row in db.execute("SELECT profile_json FROM candidates WHERE job_id=?", (job_id,)).fetchall():
                profile = json.loads(row["profile_json"])
                source_key = profile.get("dataset_source")
                if isinstance(source_key, str) and source_key.startswith(SYNTHETIC_DATASET_KEY_PREFIX):
                    existing.add(source_key)
            criteria = json.loads(current_job["criteria_json"])
            for sample in prepared:
                if sample["source_key"] in existing:
                    skipped += 1
                    continue
                insert_candidate(db, job_id, "txt", sample["pages"], criteria, sample["source_key"])
                existing.add(sample["source_key"])
                added += 1
            audit(db, job_id, "system", "synthetic_dataset_loaded", details={
                "dataset": SYNTHETIC_DATASET_ID,
                "split": "test",
                "added": added,
                "skipped_duplicates": skipped,
            })
            total = db.execute("SELECT COUNT(*) FROM candidates WHERE job_id=?", (job_id,)).fetchone()[0]
        self.send_json(200, {
            "ok": True,
            "dataset": SYNTHETIC_DATASET_ID,
            "added": added,
            "skipped": skipped,
            "total_candidates": total,
            "message": f"Dataset dimuat: {added} CV baru; {skipped} duplikat dilewati.",
        })

    def add_review(self, candidate_id: str) -> None:
        data = self.read_json()
        reviewer = str(data.get("reviewer", "")).strip()[:100]
        role = data.get("role")
        decision = data.get("decision")
        note = redact_for_evidence(str(data.get("note", "")).strip()[:2000])
        if not reviewer or role not in ("recruiter", "hiring_manager"):
            raise ValueError("Nama reviewer dan peran yang valid wajib diisi.")
        if decision not in ("advance", "needs_info", "not_selected"):
            raise ValueError("Pilihan review tidak valid.")
        with connect() as db:
            candidate = db.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
            if not candidate:
                self.send_json(404, {"error": "Kandidat tidak ditemukan."})
                return
            db.execute("INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (new_id("rev"), candidate_id, reviewer, role, decision, note, now()))
            db.execute("UPDATE candidates SET status=? WHERE id=?", (decision, candidate_id))
            audit(db, candidate["job_id"], reviewer, "human_review_recorded", candidate_id,
                  {"role": role, "decision": decision})
        self.send_json(201, {"ok": True, "message": "Review manusia tercatat."})

    def add_scorecard(self, candidate_id: str) -> None:
        data = self.read_json()
        with connect() as db:
            candidate = db.execute("SELECT * FROM candidates WHERE id=?", (candidate_id,)).fetchone()
            if not candidate:
                self.send_json(404, {"error": "Kandidat tidak ditemukan."})
                return
            from interview_service import record_scorecard
            scorecard_data = {
                "job_id": candidate["job_id"],
                "candidate_id": candidate_id,
                "reviewer": data.get("reviewer"),
                "role": data.get("role"),
                "overall_recommendation": data.get("overall_recommendation"),
                "notes": data.get("notes", ""),
                "criterion_scores": data.get("criterion_scores", []),
            }
            scorecard_id = record_scorecard(db, scorecard_data)
        self.send_json(201, {"ok": True, "id": scorecard_id, "message": "Scorecard wawancara tersimpan."})

    def ask_job(self, job_id: str) -> None:

        data = self.read_json()
        question = str(data.get("question", "")).strip()[:500]
        if not question:
            raise ValueError("Masukkan pertanyaan.")
        with connect() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            self.send_json(404, {"error": "Lowongan tidak ditemukan."})
            return
        try:
            from rag_service import retrieve_job_context
            rag_res = retrieve_job_context(question, dict(job))
            self.send_json(200, {
                "answer": rag_res["answer"],
                "sources": rag_res["sources"],
                "query": rag_res["query"],
                "total_sources_evaluated": rag_res["total_sources_evaluated"],
                "mode": "retrieval_only",
            })
        except Exception:
            sources = rank_retrieval(question, dict(job))
            self.send_json(200, {
                "answer": "Saya menemukan bagian requisition yang paling relevan. Jawaban ini hanya mengambil sumber yang disetujui; reviewer tetap perlu memeriksa konteks.",
                "sources": sources,
                "mode": "retrieval_only",
            })

    def do_DELETE(self) -> None:  # noqa: N802
        if not self.require_same_origin_mutation():
            return
        if DRAINING.is_set():
            self.close_connection = True
            self.send_json(503, {"error": "Server sedang dihentikan.", "draining": True})
            return
        try:
            body_length = request_content_length(self)
            if body_length:
                self.close_connection = True
                raise ValueError("DELETE tidak menerima body permintaan.")
        except ValueError as exc:
            self.close_connection = True
            self.send_json(400, {"error": str(exc)})
            return
        parts = [unquote(p) for p in urlsplit(self.path).path.strip("/").split("/")]
        if len(parts) != 3 or parts[:2] != ["api", "candidates"]:
            self.close_connection = True
            self.send_json(404, {"error": "Endpoint tidak ditemukan."})
            return
        with connect() as db:
            candidate = db.execute("SELECT * FROM candidates WHERE id=?", (parts[2],)).fetchone()
            if not candidate:
                self.send_json(404, {"error": "Kandidat tidak ditemukan."})
                return
            job_id = candidate["job_id"]
            db.execute("DELETE FROM audit_events WHERE candidate_id=?", (candidate["id"],))
            db.execute("DELETE FROM candidates WHERE id=?", (candidate["id"],))
            audit(db, job_id, "user", "candidate_deleted")
        self.send_json(200, {"ok": True})


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Bound accepted connections before ThreadingMixIn creates worker threads."""

    def __init__(self, server_address, request_handler_class, bind_and_activate=True):
        self._handler_slots = threading.BoundedSemaphore(MAX_CONCURRENT_HTTP_HANDLERS)
        super().__init__(server_address, request_handler_class, bind_and_activate)

    def process_request(self, request, client_address) -> None:
        global HTTP_HANDLER_REJECTIONS_TOTAL, HTTP_HANDLERS_ACTIVE
        if not self._handler_slots.acquire(blocking=False):
            with METRICS_LOCK:
                HTTP_HANDLER_REJECTIONS_TOTAL += 1
            try:
                request.settimeout(0.25)
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Connection: close\r\n"
                    b"Content-Length: 0\r\n"
                    b"Retry-After: 2\r\n\r\n"
                )
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return

        with METRICS_LOCK:
            HTTP_HANDLERS_ACTIVE += 1
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._release_handler_slot()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._release_handler_slot()

    def _release_handler_slot(self) -> None:
        global HTTP_HANDLERS_ACTIVE
        with METRICS_LOCK:
            HTTP_HANDLERS_ACTIVE -= 1
        self._handler_slots.release()


def main() -> None:
    if not WEB.is_dir():
        raise SystemExit("Folder web/ tidak ditemukan.")
    init_db()
    host, port = local_bind_config()
    grace_seconds = shutdown_grace_config()
    server = BoundedThreadingHTTPServer((host, port), Handler)
    # Drain active request handlers on shutdown instead of abandoning daemon workers.
    server.daemon_threads = False
    server.block_on_close = True

    register_shutdown_signal_handlers(server, grace_seconds)
    print(f"KarsaHire berjalan di http://{host}:{port}")
    print("MVP lokal: gunakan CV sintetis atau data uji yang memang diizinkan.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer dihentikan; menunggu request aktif selesai.")
    finally:
        DRAINING.set()
        server.server_close()


if __name__ == "__main__":
    main()
