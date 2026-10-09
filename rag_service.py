"""Internal RAG & Retrieval Service for KarsaHire Requisition Context.

Provides grounded, non-hallucinatory retrieval over approved job requisitions:
1. Multi-source weighted indexing:
   - Job Description (Deskripsi Posisi)
   - Approved Criteria (Required & Preferred with explicit weights)
   - Structured Interview Guidelines & Competency Rubrics (STAR method, objective scoring)
   - Custom organizational knowledge & policies
2. Precision BM25 / TF-IDF Token Overlap Ranking:
   - High-fidelity tokenization preserving technical identifiers (e.g. C++, .NET, CI/CD, Node.js)
   - Indonesian & English bilingual stop word filtering
   - Technical term boost (FastAPI, PostgreSQL, Audit, Sourcing, etc.)
   - Exact phrase and multi-token matching bonuses
   - Source-level prioritization for mandatory (required) criteria and interview rubrics
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

# ---------------------------------------------------------------------------
# Bilingual Stop Words (Indonesian & English)
# Note: Signal words such as "wajib", "kriteria", "rubrik", "wawancara",
# "panduan", "kompetensi" are intentionally EXCLUDED from stop words.
# ---------------------------------------------------------------------------

INDONESIAN_STOP_WORDS: set[str] = {
    "ada", "adalah", "adanya", "adapun", "agak", "agar", "akan", "akankah",
    "akhir", "akhiri", "akhirnya", "aku", "akulah", "amat", "amatlah", "anda",
    "andalah", "antar", "antara", "antaranya", "apa", "apaan", "apabila",
    "apakah", "apalagi", "apatah", "artinya", "asal", "asalkan", "atas", "atau",
    "ataukah", "ataupun", "awal", "awalnya", "bagai", "bagaikan", "bagaimana",
    "bagaimanakah", "bagaimanapun", "bagi", "bagian", "bahkan", "bahwa",
    "bahwasanya", "baik", "bakal", "bakalan", "balik", "banyak", "bapak",
    "beberapa", "begini", "beginian", "beginikah", "beginilah", "begitu",
    "begitukah", "begitulah", "begitupun", "bekerja", "belakang", "belakangan",
    "belum", "belumlah", "benar", "benarkah", "benarlah", "berada", "berakhir",
    "berakhirlah", "berakhirnya", "berapa", "berapakah", "berapalah", "berapapun",
    "berarti", "berawal", "berbagai", "berdatangan", "beri", "berikan", "berikut",
    "berikutnya", "berjumlah", "berkala", "berkali-kali", "berkata", "berkehendak",
    "berkeinginan", "berkenaan", "berlainan", "berlalu", "berlangsung", "berlebihan",
    "bermacam", "bermacam-macam", "bermaksud", "bermula", "bersama", "bersama-sama",
    "bersiap", "bersiap-siap", "bertanya", "bertanya-tanya", "berturut",
    "berturut-turut", "bertutur", "berujar", "berupa", "besar", "betul", "betulkah",
    "biasa", "biasanya", "bila", "bilakah", "bisa", "bisakah", "boleh", "bolehkah",
    "bolehlah", "buat", "bukan", "bukankah", "bukanlah", "bukannya", "cuma",
    "cukup", "cukupkah", "cukuplah", "dalam", "dan", "dapat", "dari", "daripada",
    "dekat", "demi", "demikian", "demikianlah", "dengan", "depan", "di", "dia",
    "dialah", "diantara", "diantaranya", "diberi", "diberikan", "diberikannya",
    "dibuat", "dibuatnya", "didapat", "didatangkan", "digunakan", "diibaratkan",
    "diibaratkannya", "diingat", "diingatkan", "diinginkan", "dijawab", "dijelaskan",
    "dijelaskannya", "dikarenakan", "dikatakan", "dikatakannya", "dikerjakan",
    "diketahui", "diketahuinya", "dikira", "dilakukan", "dilalui", "dilihat",
    "dimaksud", "dimaksudkan", "dimaksudkannya", "dimaksudya", "diminta",
    "dimintai", "dimisalkan", "dimulai", "dimulailah", "dimulainya", "dimungkinkan",
    "dini", "dipastikan", "diperbuat", "diperbuatnya", "dipergunakan", "diperkirakan",
    "diperlihatkan", "diperlukan", "diperlukannya", "dipersoalkan", "dipertanyakan",
    "dipunyai", "diri", "dirinya", "disampaikan", "disebut", "disebutkan",
    "disebutkannya", "disini", "disinilah", "ditambahkan", "ditandaskan", "ditanya",
    "ditanyai", "ditanyakan", "ditegaskan", "diterima", "ditemukan", "ditujukan",
    "ditunjuk", "ditunjuki", "ditunjukkan", "ditunjukkannya", "ditunjuknya",
    "dituturkan", "dituturkannya", "diucapkan", "diucapkannya", "diungkapkan",
    "dong", "dua", "dulu", "empat", "enggak", "enggaknya", "entah", "entahlah",
    "hal", "hampir", "hanya", "hanyalah", "harus", "haruslah", "harusnya", "hendak",
    "hendaklah", "hendaknya", "hingga", "ia", "ialah", "ibarat", "ibaratkan",
    "ibaratnya", "ibu", "ikut", "ingat", "ingat-ingat", "ingin", "inginkah",
    "inginkan", "ini", "inikah", "inilah", "itu", "itukah", "itulah", "jadi",
    "jadilah", "jadinya", "jangan", "jangankan", "janganlah", "jauh", "jawab",
    "jawaban", "jawabnya", "jelas", "jelaskan", "jelaslah", "jelasnya", "jika",
    "jikalau", "juga", "jumlah", "jumlahnya", "justru", "kala", "kalau", "kalaulah",
    "kalaupun", "kalian", "kami", "kamilah", "kamu", "kamulah", "kan", "kapan",
    "kapankah", "kapanpun", "karena", "karenanya", "kasus", "kata", "katakan",
    "katakanlah", "katanya", "ke", "keadaan", "kebetulan", "kecil", "kedua",
    "keduanya", "keinginan", "kelamaan", "kelihatan", "kelihatannya", "kelima",
    "keluar", "kembali", "kemudian", "kemungkinan", "kemungkinannya", "kenapa",
    "kepada", "kepadanya", "kesampaian", "keseluruhan", "keseluruhannya",
    "keterlaluan", "ketika", "khususnya", "kini", "kinilah", "kira", "kira-kira",
    "kiranya", "kita", "kitalah", "kurang", "lagi", "lagian", "lah", "lain",
    "lainnya", "lalu", "lama", "lamanya", "lanjut", "lanjutnya", "lebih", "lewat",
    "lihat", "lima", "luar", "macam", "maka", "makanya", "makin", "malah",
    "malahan", "mampu", "mampukah", "mana", "manakala", "manalagi", "masih",
    "masihkah", "masing", "masing-masing", "mau", "maupun", "melainkan",
    "melakukan", "melalui", "melihat", "melihatnya", "memang", "memastikan",
    "memberi", "memberikan", "membuat", "memerlukan", "memihak", "meminta",
    "memintakan", "memisalkan", "memperbuat", "mempergunakan", "memperkirakan",
    "memperlihatkan", "mempersiapkan", "mempersoalkan", "mempertanyakan",
    "mempunyai", "memulai", "memungkinkan", "menaiki", "menambahkan", "menandaskan",
    "menanti", "menanti-nanti", "menantikan", "menanya", "menanyai", "menanyakan",
    "mendapat", "mendapatkan", "mendatang", "mendatangi", "mendatangkan",
    "menegaskan", "mengakhiri", "mengapa", "mengatakan", "mengatakannya",
    "mengenai", "mengerjakan", "mengetahui", "menggunakan", "menghendaki",
    "mengibaratkan", "mengibaratkannya", "mengingat", "mengingatkan", "menginginkan",
    "mengira", "mengucapkan", "mengucapkannya", "mengungkapkan", "menjadi",
    "menjawab", "menuju", "menunjuk", "menunjuki", "menunjukkan", "menunjuknya",
    "menurut", "menuturkan", "menyampaikan", "menyangkut", "menyatakan",
    "menyebutkan", "menyeluruh", "menyiapkan", "merasa", "mereka", "merekalah",
    "merupakan", "meski", "meskipun", "meyakini", "minta", "mirip", "misal",
    "misalkan", "misalnya", "mula", "mulai", "mulailah", "mulanya", "mungkin",
    "mungkinkah", "nah", "naik", "namun", "nanti", "nantinya", "nyaris", "nyatanya",
    "oleh", "olehnya", "pada", "padahal", "padanya", "pak", "paling", "panjang",
    "pantas", "para", "pasti", "pastilah", "penting", "pentingnya", "per",
    "percuma", "perlu", "perlukah", "perlunya", "pernah", "persoalan", "pertama",
    "pertama-tama", "pertanyaan", "pertanyakan", "pihak", "pihaknya", "pukul",
    "pula", "pun", "punya", "rasa", "rasanya", "rata", "rupanya", "saat", "saatnya",
    "saja", "sajalah", "saling", "sama", "sama-sama", "sambil", "sampai",
    "sampai-sampai", "sampaikan", "sana", "sangat", "sangatlah", "satu", "saya",
    "sayalah", "se", "sebab", "sebabnya", "sebagai", "sebagaimana", "sebagainya",
    "sebagian", "sebaik", "sebaik-baiknya", "sebaiknya", "sebaliknya", "sebanyak",
    "sebegini", "sebegitu", "sebelum", "sebelumnya", "sebenarnya", "seberapa",
    "sebesar", "sebetulnya", "sebisanya", "sebuah", "sebut", "sebutlah", "sebutnya",
    "secara", "secukupnya", "sedang", "sedangkan", "sedemikian", "sedikit",
    "sedikitnya", "seenaknya", "segala", "segalanya", "segera", "seharusnya",
    "sehingga", "seingat", "sejak", "sejauh", "sejenak", "sejumlah", "sekadar",
    "sekadarnya", "sekali", "sekalian", "sekaligus", "sekalipun", "sekarang",
    "sekaranglah", "sekecil", "seketika", "sekiranya", "sekitar", "sekitarnya",
    "sekurang-kurangnya", "sela", "selain", "selaku", "selalu", "selama",
    "selama-lamanya", "selamanya", "selanjutnya", "seluruh", "seluruhnya",
    "semacam", "semakin", "semampu", "semampunya", "semasa", "semasih", "semata",
    "semata-mata", "semaunya", "sementara", "semisal", "semisalnya", "sempat",
    "semua", "semuanya", "semula", "sendiri", "sendirian", "sendirinya",
    "seolah", "seolah-olah", "seorang", "sepanjang", "sepantasnya", "sepantasnyalah",
    "seperlunya", "seperti", "sepertinya", "sepihak", "sering", "seringnya",
    "serta", "serupa", "sesaat", "sesama", "sesampai", "sesegera", "sesekali",
    "seseorang", "sesuatu", "sesuatunya", "sesudah", "sesudahnya", "setelah",
    "setempat", "setengah", "seterusnya", "setiap", "setiba", "setibanya",
    "setidak-tidaknya", "setidaknya", "setinggi", "seusai", "sewaktu", "siap",
    "siapa", "siapakah", "siapapun", "sini", "sinilah", "suatu", "sudah",
    "sudahkah", "sudahlah", "supaya", "tadi", "tadinya", "tahu", "tak", "tapi",
    "tegas", "tegasnya", "telah", "tempat", "tengah", "tentang", "tentu", "tentulah",
    "tentunya", "tepat", "terakhir", "terasa", "terbanyak", "terdahulu", "terdapat",
    "terdiri", "terhadap", "terhadapnya", "teringat", "teringat-ingat", "terjadi",
    "terjadilah", "terjadinya", "terkira", "terlalu", "terlebih", "terlihat",
    "termasuk", "ternyata", "tersampaikan", "tersebut", "tersebutlah", "tertentu",
    "tertuju", "terus", "terutama", "tetap", "tetapi", "tiap", "tiba", "tiba-tiba",
    "tidak", "tidakkah", "tidaklah", "toh", "untuk", "usah", "waduh", "wah", "wahai", "waktu",
    "waktunya", "walau", "walaupun", "wong", "yaitu", "yakin", "yakni", "yang",
}

ENGLISH_STOP_WORDS: set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't",
    "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves",
}

STOP_WORDS = INDONESIAN_STOP_WORDS | ENGLISH_STOP_WORDS

# Explicit keywords to preserve even if they might look like common words
SIGNAL_KEYWORDS = {
    "wajib", "preferensi", "kriteria", "rubrik", "wawancara", "panduan",
    "skor", "nilai", "syarat", "tugas", "posisi", "lowongan", "kompetensi",
    "bukti", "interview", "rubric", "criteria", "required", "preferred",
    "requirement", "qualification", "job", "role", "score", "evidence",
    "star", "behavioral", "c", "r", "go", "it",
}

# ---------------------------------------------------------------------------
# Technical Term Taxonomy & Domain Keywords
# ---------------------------------------------------------------------------

try:
    from taxonomy import ALIASES, SKILLS, SKILLS_BY_DOMAIN
except ImportError:
    SKILLS = []
    ALIASES = {}
    SKILLS_BY_DOMAIN = {}

# Additional specialized technical and operational terms
ADDITIONAL_TECHNICAL_TERMS = {
    # Software Engineering
    "fastapi", "postgresql", "postgres", "psql", "python", "golang", "go",
    "docker", "kubernetes", "k8s", "ci/cd", "rest", "api", "restful", "grpc",
    "graphql", "microservices", "sql", "nosql", "redis", "mongodb", "sqlite",
    "git", "github", "gitlab", "cloud", "aws", "gcp", "azure", "linux", "bash",
    "backend", "frontend", "fullstack", "devops", "tdd", "unit testing",
    "c++", "c#", ".net", "node.js", "react", "react.js", "vue", "next.js",
    "pydantic", "sqlalchemy", "orm", "celery", "kafka", "rabbitmq", "elasticsearch",
    # Accounting & Finance
    "audit", "auditing", "internal audit", "external audit", "audit internal",
    "sox", "sox compliance", "pajak", "tax", "taxation", "pph", "pph 21", "pph 23",
    "pph 25", "pph 4(2)", "ppn", "vat", "e-faktur", "e-spt", "buku besar",
    "general ledger", "gl", "pembukuan", "bookkeeping", "reconciliation",
    "rekonsiliasi", "rekonsiliasi bank", "laporan keuangan", "financial statement",
    "neraca", "balance sheet", "p&l", "profit & loss", "laba rugi", "ar", "ap",
    "accounts payable", "accounts receivable", "cost accounting", "fp&a",
    "psak", "ifrs", "gaap", "jurnal", "accurate", "sap", "oracle financials",
    # HR & Talent Acquisition
    "sourcing", "candidate sourcing", "talent sourcing", "headhunting",
    "screening", "skrining", "skrining cv", "resume screening",
    "wawancara terstruktur", "structured interview", "structured interviewing",
    "behavioral interview", "competency-based interview", "ats", "hris",
    "workday", "bamboohr", "talenta", "darwinbox", "greenhouse", "lever",
    "onboarding", "offboarding", "performance management", "kpi", "okr",
    "compensation", "benefits", "comp & ben", "payroll", "industrial relations",
    "hubungan industrial", "boolean search", "talent mapping",
    # Cybersecurity & Infra
    "siem", "soc", "incident response", "firewall", "vpn", "vlan",
    "penetration testing", "pentest", "vapt", "iso 27001", "active directory",
    "ldap", "zero trust", "edr", "waf", "threat hunting", "csirt",
}

ALL_TECHNICAL_TERMS: set[str] = {s.lower() for s in SKILLS} | ADDITIONAL_TECHNICAL_TERMS


def is_technical_term(term: str) -> bool:
    """Determine whether a token or phrase is a recognized technical or domain term."""
    norm = term.strip().lower()
    if norm in ALL_TECHNICAL_TERMS or norm in ALIASES:
        return True
    for aliases in ALIASES.values():
        if norm in aliases:
            return True
    return False


# ---------------------------------------------------------------------------
# Normalization & Tokenization
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Fold case, normalize dashes and whitespace."""
    return re.sub(r"\s+", " ", text.casefold().replace("–", "-").replace("—", "-")).strip()


def tokenize(text: str, filter_stopwords: bool = True) -> list[str]:
    """Tokenize text while strictly preserving programming symbols and technical identifiers.
    
    Preserves tokens such as:
    - C++, C#, .NET
    - Node.js, Next.js, React.js
    - CI/CD, TCP/IP
    - FastAPI, PostgreSQL, Audit, Sourcing
    """
    normalized = normalize_text(text)
    raw_tokens = re.findall(r"[a-z0-9+#./-]+", normalized)
    cleaned_tokens: list[str] = []

    for raw in raw_tokens:
        # Strip trailing/leading punctuation unless essential (e.g. c++, c#, .net)
        t = re.sub(r"^[^\w+#.]+|[^\w+#]+$", "", raw)
        if not t:
            continue
        # Allow single-letter terms if significant (e.g., C or R language, digits)
        if len(t) == 1 and t not in {"c", "r"} and not t.isdigit():
            continue
        if filter_stopwords and (t in STOP_WORDS) and (t not in SIGNAL_KEYWORDS) and not is_technical_term(t):
            continue
        cleaned_tokens.append(t)

    return cleaned_tokens


# ---------------------------------------------------------------------------
# Knowledge Source Chunker (Multi-Source Extraction)
# ---------------------------------------------------------------------------

def _split_into_sentences(text: str) -> list[str]:
    """Split prose text into clean sentence units or list items."""
    raw_splits = re.split(r"(?<=[.!?])\s+|\n+|[•\-\*]\s+", text)
    sentences = []
    for s in raw_splits:
        cleaned = " ".join(s.split()).strip()
        if len(cleaned) >= 5:
            sentences.append(cleaned)
    return sentences


def _generate_domain_rubrics_for_criterion(label: str) -> list[str]:
    """Generate high-yield structured interview probes for specific technical competencies."""
    norm = label.lower()
    rubrics: list[str] = []

    if "fastapi" in norm:
        rubrics.append(
            "Rubrik Wawancara Teknis (FastAPI): Evaluasi pemahaman arsitektur REST API, "
            "asynchronous programming (async/await), validasi skema Pydantic, dependency injection, "
            "dan pembuatan automated tests."
        )
    if "postgresql" in norm or "postgres" in norm:
        rubrics.append(
            "Rubrik Wawancara Teknis (PostgreSQL): Evaluasi perancangan skema relasional, "
            "indeksasi (B-Tree/GIN), optimasi query (EXPLAIN ANALYZE), transaksi ACID, "
            "dan manajemen migrasi database."
        )
    if "audit" in norm or "internal audit" in norm or "auditing" in norm:
        rubrics.append(
            "Rubrik Wawancara Kompetensi (Audit): Evaluasi pemahaman metodologi audit internal, "
            "pengujian kepatuhan dan pengujian substantif, evaluasi pengendalian internal, "
            "jejak audit (audit trail), serta pelaporan temuan ke manajemen."
        )
    if "sourcing" in norm or "recruitment" in norm:
        rubrics.append(
            "Rubrik Wawancara Kompetensi (Sourcing): Evaluasi strategi talent mapping, "
            "operator Boolean search, pemanfaatan platform talent (LinkedIn Recruiter), "
            "diversifikasi kanal sourcing, dan pengelolaan candidate pipeline."
        )

    # General competency probe for any criterion
    rubrics.append(
        f"Rubrik Wawancara Kompetensi ({label}): Minta kandidat menjelaskan situasi nyata "
        f"di mana kandidat menerapkan {label}, kendala teknis yang dihadapi, tindakan korektif yang diambil, "
        f"dan dampak hasil yang terukur."
    )
    return rubrics


def build_knowledge_chunks(
    job: dict[str, Any],
    custom_knowledge: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Extract and categorize multi-source knowledge chunks from the job requisition.
    
    Sources extracted:
    1. Deskripsi Posisi Lowongan (Job Description)
    2. Kriteria yang Disetujui (Required / Preferred dengan bobot penilaian)
    3. Panduan Wawancara & Rubrik Kompetensi Terstruktur
    4. Custom Knowledge / Kebijakan Internal
    """
    chunks: list[dict[str, Any]] = []

    # 1. Job Description & Position Meta
    title = str(job.get("title", "")).strip()
    department = str(job.get("department", "")).strip()
    if title:
        summary_text = f"Posisi Requisition: {title}" + (f" | Departemen: {department}" if department else "")
        chunks.append({
            "source": f"Informasi Posisi: {title}",
            "text": summary_text,
            "source_type": "position_meta",
            "source_weight": 1.2,
            "label": title,
        })

    description = str(job.get("description", "")).strip()
    if description:
        sentences = _split_into_sentences(description)
        for sentence in sentences:
            chunks.append({
                "source": "Deskripsi lowongan",
                "text": sentence,
                "source_type": "job_description",
                "source_weight": 1.1,
                "label": "Job Description",
            })

    # 2. Approved Criteria (Required & Preferred)
    criteria_raw = job.get("criteria_json", job.get("criteria", []))
    criteria: list[dict[str, Any]] = []
    if isinstance(criteria_raw, str):
        try:
            criteria = json.loads(criteria_raw)
        except Exception:
            criteria = []
    elif isinstance(criteria_raw, list):
        criteria = criteria_raw

    for crit in criteria:
        if not isinstance(crit, dict):
            continue
        label = str(crit.get("label", "")).strip()
        if not label:
            continue
        kind = str(crit.get("type", "required")).lower()
        is_required = kind == "required"
        weight = float(crit.get("weight", 2.0 if is_required else 1.0))

        source_label = f"Kriteria {'Wajib' if is_required else 'Preferensi'}: {label} (Bobot {weight:.1f})"
        text_content = (
            f"Kriteria {'wajib' if is_required else 'preferensi'} yang disetujui: "
            f"Kandidat dievaluasi atas kompetensi '{label}' dengan bobot penilaian {weight:.1f}."
        )

        # Higher base source_weight for required criteria
        base_source_weight = (2.2 * weight) if is_required else (1.1 * weight)

        chunks.append({
            "source": source_label,
            "text": text_content,
            "source_type": "required_criterion" if is_required else "preferred_criterion",
            "source_weight": base_source_weight,
            "label": label,
            "is_required": is_required,
        })

    # 3. Structured Interview Guidelines & Competency Rubrics
    # KarsaHire Standard Guidelines
    chunks.append({
        "source": "Panduan Wawancara: Standar Wawancara Terstruktur KarsaHire",
        "text": "Setiap interviewer wajib menggunakan daftar pertanyaan terstruktur dan rubrik kompetensi "
                "yang sama untuk semua kandidat guna meminimalkan bias dan memastikan objektivitas seleksi.",
        "source_type": "interview_rubric",
        "source_weight": 1.3,
        "label": "Structured Interview Standard",
    })
    chunks.append({
        "source": "Panduan Wawancara: Metode Evaluasi Bukti (STAR)",
        "text": "Evaluasi jawaban wawancara berbasis bukti menggunakan kerangka STAR (Situation, Task, Action, Result). "
                "Fokuskan penilaian pada aksi spesifik dan hasil konkret yang dicapai kandidat.",
        "source_type": "interview_rubric",
        "source_weight": 1.3,
        "label": "STAR Method Guide",
    })
    chunks.append({
        "source": "Rubrik Penilaian: Skala Skor Kompetensi Wawancara",
        "text": "Skala penilaian rubrik 1-5: Skor 1 (Tidak ada bukti), Skor 2 (Bukti di bawah standar), "
                "Skor 3 (Memenuhi kualifikasi dasar), Skor 4 (Melebihi ekspektasi), Skor 5 (Penguasaan mendalam & memimpin).",
        "source_type": "interview_rubric",
        "source_weight": 1.4,
        "label": "Scoring Rubric Scale",
    })
    chunks.append({
        "source": "Panduan Wawancara: Aturan Objektivitas Penilaian",
        "text": "Dilarang menyimpulkan kompetensi dari aksen, gaya bicara, atau dugaan culture fit. "
                "Setiap skor wawancara harus disertai catatan bukti yang merujuk langsung pada kriteria disetujui.",
        "source_type": "interview_rubric",
        "source_weight": 1.3,
        "label": "Objective Evaluation Rule",
    })

    # Criterion-specific rubrics
    for crit in criteria:
        if not isinstance(crit, dict):
            continue
        label = str(crit.get("label", "")).strip()
        if not label:
            continue
        is_required = str(crit.get("type", "required")).lower() == "required"
        rubrics = _generate_domain_rubrics_for_criterion(label)
        for rub_text in rubrics:
            chunks.append({
                "source": f"Rubrik Wawancara: Kompetensi {label}",
                "text": rub_text,
                "source_type": "interview_rubric",
                "source_weight": 1.6 if is_required else 1.2,
                "label": label,
                "is_required": is_required,
            })

    # Explicit rubrics stored in job dict if provided
    for key in ("interview_rubric", "interview_rubrics", "rubric", "rubrics", "interview_guide"):
        val = job.get(key)
        if isinstance(val, str) and val.strip():
            for sentence in _split_into_sentences(val):
                chunks.append({
                    "source": "Rubrik Wawancara Khusus Requisition",
                    "text": sentence,
                    "source_type": "interview_rubric",
                    "source_weight": 1.5,
                    "label": "Custom Rubric",
                })
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    src = item.get("source", "Rubrik Wawancara Requisition")
                    txt = item.get("text", str(item))
                    chunks.append({
                        "source": src,
                        "text": txt,
                        "source_type": "interview_rubric",
                        "source_weight": float(item.get("weight", 1.4)),
                        "label": "Custom Rubric",
                    })
                elif isinstance(item, str) and item.strip():
                    chunks.append({
                        "source": "Rubrik Wawancara Requisition",
                        "text": item.strip(),
                        "source_type": "interview_rubric",
                        "source_weight": 1.4,
                        "label": "Custom Rubric",
                    })

    # 4. Custom Knowledge (optional caller-provided documents)
    if custom_knowledge and isinstance(custom_knowledge, list):
        for item in custom_knowledge:
            if not isinstance(item, dict):
                continue
            src = str(item.get("source", "Dokumen Pengetahuan Tambahan")).strip()
            txt = str(item.get("text", "")).strip()
            if not txt:
                continue
            item_weight = float(item.get("weight", 1.0))
            for sentence in _split_into_sentences(txt):
                chunks.append({
                    "source": src,
                    "text": sentence,
                    "source_type": "custom_knowledge",
                    "source_weight": item_weight,
                    "label": src,
                })

    # Pre-tokenize all chunks for fast ranking
    for chunk in chunks:
        chunk["tokens"] = tokenize(chunk["text"], filter_stopwords=True)
        chunk["raw_tokens"] = tokenize(chunk["text"], filter_stopwords=False)
        chunk["text_norm"] = normalize_text(chunk["text"])

    return chunks


# ---------------------------------------------------------------------------
# BM25 & TF-IDF Precision Retrieval Engine
# ---------------------------------------------------------------------------

def _compute_idf(corpus_tokens: list[list[str]], term: str) -> float:
    """Compute Robertson-Spärck Jones smoothed positive IDF."""
    doc_count = len(corpus_tokens)
    if doc_count == 0:
        return 0.0
    df = sum(1 for tokens in corpus_tokens if term in tokens)
    # Smoothed positive formulation: ln(1 + (N - df + 0.5) / (df + 0.5))
    return math.log(1.0 + (doc_count - df + 0.5) / (df + 0.5))


def retrieve_job_context(
    query: str,
    job: dict[str, Any],
    custom_knowledge: list[dict[str, Any]] | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Retrieve relevant, evidence-grounded requisition context using weighted BM25/TF-IDF.
    
    Args:
        query: User question or keyword search.
        job: Job dictionary containing title, department, description, criteria_json, etc.
        custom_knowledge: Optional custom knowledge base entries.
        top_k: Maximum number of top relevant sources to return.
        
    Returns:
        {
            "answer": str,  # Neutral evidence summary grounded in stored documents
            "sources": list[dict],  # List of {source, text, score, matched_tokens}
            "query": str,
            "total_sources_evaluated": int
        }
    """
    cleaned_query = query.strip() if query else ""
    chunks = build_knowledge_chunks(job, custom_knowledge)
    total_sources_evaluated = len(chunks)

    if not cleaned_query:
        return {
            "answer": "Pertanyaan kosong. Masukkan kata kunci atau pertanyaan seputar deskripsi posisi, "
                      "kriteria yang disetujui, atau rubrik wawancara.",
            "sources": [],
            "query": query,
            "total_sources_evaluated": total_sources_evaluated,
        }

    if total_sources_evaluated == 0:
        return {
            "answer": "Tidak ada dokumen requisition tersimpan untuk lowongan ini.",
            "sources": [],
            "query": cleaned_query,
            "total_sources_evaluated": 0,
        }

    # Query tokenization
    query_tokens = tokenize(cleaned_query, filter_stopwords=True)
    if not query_tokens:
        # Fallback to tokenizing without stop word filter if all tokens were filtered
        query_tokens = tokenize(cleaned_query, filter_stopwords=False)

    if not query_tokens:
        return {
            "answer": "Tidak ditemukan rujukan relevan dalam dokumen requisition tersimpan untuk pertanyaan tersebut.",
            "sources": [],
            "query": cleaned_query,
            "total_sources_evaluated": total_sources_evaluated,
        }

    norm_query = normalize_text(cleaned_query)
    corpus_tokens = [c["tokens"] for c in chunks]
    avgdl = sum(len(c["tokens"]) for c in chunks) / max(1, total_sources_evaluated)

    # Precalculate IDFs for query tokens
    idfs: dict[str, float] = {}
    for term in set(query_tokens):
        idfs[term] = _compute_idf(corpus_tokens, term)

    # Detect query intent signals
    query_signals = set(query_tokens)
    prefers_required = any(sig in query_signals for sig in ("wajib", "required", "mandatory", "must"))
    prefers_rubric = any(sig in query_signals for sig in ("rubrik", "wawancara", "interview", "pertanyaan", "panduan", "skala"))

    k1 = 1.5
    b = 0.75

    scored_chunks: list[dict[str, Any]] = []

    for chunk in chunks:
        tokens = chunk["tokens"]
        doc_len = len(tokens)
        token_set = set(tokens)
        text_norm = chunk["text_norm"]

        # Track matched tokens
        matched_tokens: list[str] = []
        for q_term in query_tokens:
            if q_term in token_set or (len(q_term) >= 3 and q_term in text_norm):
                if q_term not in matched_tokens:
                    matched_tokens.append(q_term)

        # 1. Okapi BM25 base score
        bm25_score = 0.0
        for term in set(query_tokens):
            tf = tokens.count(term)
            if tf == 0 and term in text_norm:
                tf = 1  # Substring occurrence count credit

            if tf > 0:
                idf = idfs.get(term, 0.0)
                # Boost technical terms
                tech_mult = 2.0 if is_technical_term(term) else 1.0
                tf_norm = (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * (doc_len / max(1.0, avgdl))))
                bm25_score += idf * tf_norm * tech_mult

        # 2. Technical term overlap count
        tech_matched = [t for t in matched_tokens if is_technical_term(t)]
        tech_bonus = 1.5 * len(tech_matched)

        # 3. Exact phrase match bonus
        phrase_bonus = 0.0
        if len(query_tokens) >= 2:
            # Full query phrase match
            full_phrase = " ".join(query_tokens)
            if full_phrase in text_norm:
                phrase_bonus += 4.0 * len(query_tokens)
            elif norm_query in text_norm:
                phrase_bonus += 3.5 * len(query_tokens)
            else:
                # Consecutive bigram matches
                for i in range(len(query_tokens) - 1):
                    bigram = f"{query_tokens[i]} {query_tokens[i+1]}"
                    if bigram in text_norm:
                        phrase_bonus += 1.8

        # 4. Single-token exact match bonus on criterion label
        label_norm = normalize_text(chunk.get("label", ""))
        label_bonus = 0.0
        if any(term == label_norm or term in label_norm.split() for term in query_tokens):
            label_bonus += 2.5

        # 5. Source weighting
        source_weight = chunk.get("source_weight", 1.0)
        source_type = chunk.get("source_type", "")

        # Query intent booster
        intent_boost = 1.0
        if prefers_required and source_type == "required_criterion":
            intent_boost *= 1.8
        elif prefers_rubric and source_type == "interview_rubric":
            intent_boost *= 1.8

        # Aggregate final score
        raw_score = (bm25_score + tech_bonus + phrase_bonus + label_bonus) * source_weight * intent_boost

        if matched_tokens and raw_score > 0.01:
            scored_chunks.append({
                "source": chunk["source"],
                "text": chunk["text"],
                "score": round(raw_score, 4),
                "matched_tokens": matched_tokens,
                "source_type": source_type,
            })

    # Sort descending by score
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)

    # Deduplicate closely identical texts
    seen_texts: set[str] = set()
    unique_sources: list[dict[str, Any]] = []
    for sc in scored_chunks:
        simplified = re.sub(r"\W+", "", sc["text"].lower())
        if simplified in seen_texts:
            continue
        seen_texts.add(simplified)
        unique_sources.append({
            "source": sc["source"],
            "text": sc["text"],
            "score": sc["score"],
            "matched_tokens": sc["matched_tokens"],
        })
        if len(unique_sources) >= top_k:
            break

    # Build grounded neutral answer
    if unique_sources:
        answer = (
            f"Ditemukan {len(unique_sources)} bagian requisition yang relevan berdasarkan dokumen tersimpan "
            "(deskripsi posisi, kriteria yang disetujui, dan panduan/rubrik wawancara). "
            "Hasil pencarian disajikan langsung dari sumber terverifikasi tanpa inferensi eksternal; "
            "reviewer disarankan memeriksa konteks lengkap dokumen."
        )
    else:
        answer = (
            "Tidak ditemukan rujukan relevan dalam dokumen requisition tersimpan untuk pertanyaan tersebut. "
            "Pastikan kriteria yang disetujui dan deskripsi lowongan telah terisi secara lengkap."
        )

    return {
        "answer": answer,
        "sources": unique_sources,
        "query": cleaned_query,
        "total_sources_evaluated": total_sources_evaluated,
    }
