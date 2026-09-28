"""Local, evidence-first recruitment copilot prototype.

Uses standard-library HTTP/SQLite plus bundled document packages. An optional
internal OCR endpoint receives image pages; no public LLM endpoint is called.
Matching is lexical and keeps unknown evidence separate from a negative human decision.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import sqlite3
import threading
import time
import uuid
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DATA = ROOT / "data"
DB_PATH = DATA / "copilot.sqlite3"
SYNTHETIC_DATASET_ID = "sukhrobnurali/resume-parsing-vision"
SYNTHETIC_DATASET_DIR = DATA / "synthetic-cv-32"
SYNTHETIC_DATASET_KEY_PREFIX = f"hf:{SYNTHETIC_DATASET_ID}:"
SYNTHETIC_DATASET_SIZE = 32
DEFAULT_PORT = 8765
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_BODY_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024
OCR_KEY_ENV = "RECRUITMENT_COPILOT_OCR_API_KEY"
OCR_MODEL = os.environ.get("RECRUITMENT_COPILOT_OCR_MODEL", "ocr-lighton")
OCR_REQUESTS_PER_MINUTE = 6
OCR_CALLS: deque[float] = deque()
OCR_LOCK = threading.Lock()
OCR_SEMAPHORE = threading.BoundedSemaphore(5)

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)")
SENSITIVE_LINE_RE = re.compile(
    r"^\s*(?:full\s+name|candidate\s+name|name|email|e-mail|phone|mobile|"
    r"date\s+of\s+birth|dob|birthday|address|home\s+address)\s*[:|–-]",
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


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def connect() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
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
            """
        )
        job_columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)").fetchall()}
        if "status" not in job_columns:
            db.execute("ALTER TABLE jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'awaiting_approval'")


def audit(db: sqlite3.Connection, job_id: str, actor: str, event_type: str,
          candidate_id: str | None = None, details: dict | None = None) -> None:
    db.execute(
        "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_id("evt"), job_id, candidate_id, actor, event_type,
         json.dumps(details or {}, ensure_ascii=False), now()),
    )


def normalize(value: str) -> str:
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
            r"\b(?:DOB|date of birth|birthday)\s*[:|-]?\s*[^,;|]+",
            "[birth date removed]", line, flags=re.IGNORECASE,
        )
        lines.append(line)
    return " ".join(" ".join(lines).split())[:700]


def extract_document(filename: str, payload: bytes) -> tuple[str, list[tuple[int | None, str]]]:
    ext = Path(filename).suffix.lower()
    if ext == ".txt":
        text = payload.decode("utf-8", errors="replace")
        pages = [(1, line) for line in text.splitlines() if line.strip()]
    elif ext in (".png", ".jpg", ".jpeg"):
        image = normalize_image(payload)
        text = call_ocr_api(image)
        pages = [(1, line) for line in text.splitlines() if line.strip()]
    elif ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF reader tidak tersedia di runtime ini.") from exc
        reader = PdfReader(io.BytesIO(payload))
        pages = []
        ocr_images = []
        for idx, page in enumerate(reader.pages):
            page_num = idx + 1
            text = page.extract_text() or ""
            if text.strip():
                pages.extend((page_num, line) for line in text.splitlines() if line.strip())
            else:
                embedded_images = getattr(page, "images", [])
                for embedded in embedded_images:
                    try:
                        ocr_images.append((page_num, normalize_image(embedded.data)))
                    except ValueError:
                        continue
                if not embedded_images:
                    raise ValueError(f"Halaman {page_num} tidak memiliki teks atau gambar yang bisa dikirim ke OCR.")
        if ocr_images:
            if not os.environ.get(OCR_KEY_ENV):
                raise ValueError(f"PDF ini perlu OCR. Atur environment variable {OCR_KEY_ENV} untuk mengaktifkan OCR internal.")
            reserve_ocr_calls(len(ocr_images))
            for page_num, image in ocr_images:
                text = call_ocr_api(image, reservation_made=True)
                pages.extend((page_num, line) for line in text.splitlines() if line.strip())
        if not pages:
            raise ValueError("Tidak ada teks yang berhasil diekstrak dari PDF.")
    elif ext == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ValueError("DOCX reader tidak tersedia di runtime ini.") from exc
        doc = Document(io.BytesIO(payload))
        pages = [(None, p.text) for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                cell_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if cell_text:
                    pages.append((None, cell_text))
    else:
        raise ValueError("Format belum didukung. Unggah TXT, PDF teks, atau DOCX.")
    return ext[1:], pages


def normalize_image(payload: bytes) -> bytes:
    """Validate and convert an uploaded or embedded image to a compact PNG."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(payload)) as image:
            image = image.convert("RGB")
            image.thumbnail((2200, 2200))
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
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


def call_ocr_api(png_image: bytes, reservation_made: bool = False) -> str:
    api_key = os.environ.get(OCR_KEY_ENV, "").strip()
    if not api_key:
        raise ValueError(f"OCR belum dikonfigurasi. Atur environment variable {OCR_KEY_ENV} lalu jalankan ulang server.")
    if not reservation_made:
        reserve_ocr_calls(1)
    base_url = os.environ.get("RECRUITMENT_COPILOT_OCR_API_URL", "").strip().rstrip("/")
    if not base_url:
        raise ValueError("OCR belum dikonfigurasi. Atur environment variable RECRUITMENT_COPILOT_OCR_API_URL.")
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
        with OCR_SEMAPHORE:
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ValueError("API OCR membatasi request. Tunggu sebentar lalu coba lagi.") from exc
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


def profile_from_text(text: str) -> dict:
    ntext = normalize(text)
    skills = [skill for skill in SKILLS if re.search(rf"(?<!\w){re.escape(skill)}(?!\w)", ntext)]
    exp = re.findall(r"\b(\d{1,2})\s*\+?\s+years?\b", ntext)
    years = max((int(value) for value in exp), default=None)
    degrees = [
        label for pattern, label in [
            (r"\b(ph\.?d|doctorate)\b", "Doctorate"),
            (r"\b(master'?s|m\.s\.|m\.sc\.|mba)\b", "Master's"),
            (r"\b(bachelor'?s|b\.s\.|b\.sc\.|b\.a\.)\b", "Bachelor's"),
            (r"\b(associate'?s)\b", "Associate's"),
        ] if re.search(pattern, ntext)
    ]
    return {"skills": skills, "experience_years_mentioned": years, "education_levels_mentioned": degrees}


def criterion_aliases(label: str) -> list[str]:
    base = normalize(label)
    found = [base]
    for key, aliases in ALIASES.items():
        if base == key or base in aliases:
            found.extend(aliases)
    return list(dict.fromkeys(term for term in found if term))


def match_criterion(criterion: dict, pages: list[tuple[int | None, str]]) -> dict:
    aliases = criterion_aliases(criterion["label"])
    tokens = [t for t in re.findall(r"[a-z0-9+#.]+", normalize(criterion["label"])) if len(t) > 1]
    exact = []
    partial = []
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
        return {"result": "matched", "confidence": 1.0,
                "snippet": redact_for_evidence(line), "page_number": page_num}
    if partial:
        page_num, line = partial[0]
        return {"result": "partial", "confidence": 0.5,
                "snippet": redact_for_evidence(line), "page_number": page_num}
    return {"result": "unknown", "confidence": 0.0, "snippet": "", "page_number": None}


def score_candidate(criteria: list[dict], pages: list[tuple[int | None, str]]) -> tuple[float, list[dict]]:
    total_weight = sum(float(c["weight"]) for c in criteria) or 1.0
    matched_total = 0.0
    evidence_rows = []
    for criterion in criteria:
        result = match_criterion(criterion, pages)
        match_value = {"matched": 1.0, "partial": 0.5, "unknown": 0.0}[result["result"]]
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
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > MAX_BODY_BYTES:
        raise ValueError("Ukuran unggahan kosong atau melampaui batas 8 MB.")
    content_type = handler.headers.get("Content-Type", "").encode("ascii", "ignore")
    raw = handler.rfile.read(length)
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
    )
    for part in message.iter_parts():
        if part.get_content_disposition() == "form-data" and part.get_param("name", header="content-disposition") == "file":
            filename = part.get_filename() or "resume.txt"
            payload = part.get_payload(decode=True) or b""
            if len(payload) > MAX_UPLOAD_BYTES:
                raise ValueError("Batas unggahan adalah 8 MB.")
            return filename, payload
    raise ValueError("File tidak ditemukan pada permintaan unggah.")


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

    def log_message(self, fmt: str, *args) -> None:
        # Avoid access logs containing query strings or candidate data.
        print(f"{self.address_string()} {fmt % args}")

    def send_json(self, status: int, payload: dict | list) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1024 * 1024:
            raise ValueError("Permintaan kosong atau terlalu besar.")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path in ("/", "/index.html", "/app.js", "/app.css", "/approval.css"):
            filename = "index.html" if path in ("/", "/index.html") else path.rsplit("/", 1)[-1]
            types = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8", "approval.css": "text/css; charset=utf-8"}
            target = WEB / filename
            if not target.is_file():
                self.send_error(404)
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", types[filename])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/health":
            self.send_json(200, {"ok": True, "matching": "lexical-evidence-v1",
                                 "ocr_configured": bool(os.environ.get(OCR_KEY_ENV)),
                                 "external_llm": False})
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
        self.send_json(404, {"error": "Endpoint tidak ditemukan."})

    def get_job(self, job_id: str) -> None:
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

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        try:
            parts = [unquote(p) for p in path.strip("/").split("/")]
            if path == "/api/jobs":
                self.create_job()
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "approvals":
                self.approve_job(parts[2])
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "load-synthetic-data":
                self.load_synthetic_data(parts[2])
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "candidates":
                self.add_candidate(parts[2])
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "candidates" and parts[3] == "reviews":
                self.add_review(parts[2])
            elif len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs" and parts[3] == "ask":
                self.ask_job(parts[2])
            else:
                self.send_json(404, {"error": "Endpoint tidak ditemukan."})
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
        with connect() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            self.send_json(404, {"error": "Lowongan tidak ditemukan."})
            return
        if job["status"] != "criteria_approved":
            self.send_json(409, {"error": "CV baru dapat diproses setelah recruiter dan hiring manager menyetujui kriteria."})
            return
        filename, payload = multipart_file(self)
        file_type, page_lines = extract_document(filename, payload)
        criteria = json.loads(job["criteria_json"])
        with connect() as db:
            candidate_id, score, profile = insert_candidate(db, job_id, file_type, page_lines, criteria)
        # Source bytes and full document text are not retained.
        self.send_json(201, {"id": candidate_id, "score": score, "profile": profile,
                             "message": "CV diproses. Tinjau evidence sebelum mengambil keputusan."})

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
        note = str(data.get("note", "")).strip()[:2000]
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
        sources = rank_retrieval(question, dict(job))
        self.send_json(200, {
            "answer": "Saya menemukan bagian requisition yang paling relevan. Jawaban ini hanya mengambil sumber yang disetujui; reviewer tetap perlu memeriksa konteks.",
            "sources": sources,
            "mode": "retrieval_only",
        })

    def do_DELETE(self) -> None:  # noqa: N802
        parts = [unquote(p) for p in urlsplit(self.path).path.strip("/").split("/")]
        if len(parts) != 3 or parts[:2] != ["api", "candidates"]:
            self.send_json(404, {"error": "Endpoint tidak ditemukan."})
            return
        with connect() as db:
            candidate = db.execute("SELECT * FROM candidates WHERE id=?", (parts[2],)).fetchone()
            if not candidate:
                self.send_json(404, {"error": "Kandidat tidak ditemukan."})
                return
            audit(db, candidate["job_id"], "user", "candidate_deleted", candidate["id"])
            db.execute("DELETE FROM candidates WHERE id=?", (parts[2],))
        self.send_json(200, {"ok": True})


def main() -> None:
    if not WEB.is_dir():
        raise SystemExit("Folder web/ tidak ditemukan.")
    init_db()
    port = int(os.environ.get("RECRUITMENT_COPILOT_PORT", DEFAULT_PORT))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    print(f"KarsaHire berjalan di http://127.0.0.1:{port}")
    print("MVP lokal: gunakan CV sintetis atau data uji yang memang diizinkan.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer dihentikan.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
