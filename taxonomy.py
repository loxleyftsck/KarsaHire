"""Taxonomy module for KarsaHire.

Defines comprehensive skill taxonomies across five core domains:
1. Software Engineering & Programming
2. IT Infrastructure & Networking
3. Cybersecurity
4. HR & Talent Acquisition
5. Accounting & Finance

Provides:
- Domain categorization
- Bilingual synonyms & translations (English <-> Indonesian)
- Acronym and spelling variation mappings (ALIASES)
- Education level patterns (Doctorate/S3, Master/S2/Magister, Bachelor/S1/Sarjana, Associate/D3/Diploma)
- Experience years extraction patterns (Indonesian & English)
- Helper functions for normalization, alias resolution, and pattern matching
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Domain Taxonomies
# ---------------------------------------------------------------------------

SKILLS_BY_DOMAIN: dict[str, list[str]] = {
    "Software Engineering & Programming": [
        "python", "javascript", "typescript", "go", "golang", "java", "c++", "c#",
        "rust", "php", "ruby", "swift", "kotlin", "scala", "r", "dart",
        "sql", "postgresql", "mysql", "mongodb", "redis", "sqlite", "elasticsearch",
        "cassandra", "dynamodb", "oracle database",
        "docker", "kubernetes", "terraform", "git", "github", "gitlab", "ci/cd",
        "jenkins", "github actions", "rest api", "restful api", "graphql", "grpc",
        "microservices", "api development", "system design",
        "fastapi", "django", "flask", "react", "react.js", "next.js", "vue", "angular",
        "node.js", "node", "express.js", "spring boot", "asp.net", "laravel",
        "html", "css", "tailwind css", "sass",
        "machine learning", "deep learning", "pytorch", "tensorflow", "scikit-learn",
        "nlp", "llm", "rag", "generative ai", "computer vision",
        "data analysis", "pandas", "numpy", "spark", "airflow", "tableau", "power bi",
        "automated testing", "unit testing", "integration testing", "tdd", "software development",
        "programming", "code review", "agile", "scrum", "kanban",
        "pemrograman", "rekayasa perangkat lunak", "pengembangan perangkat lunak",
        "pembelajaran mesin", "analisis data", "pengujian otomatis",
    ],
    "IT Infrastructure & Networking": [
        "linux", "windows server", "unix", "ubuntu", "centos", "debian", "red hat",
        "networking", "computer networking", "network administration", "tcp/ip",
        "dns", "dhcp", "vpn", "vlan", "subnetting", "routing", "switching",
        "cisco", "juniper", "mikrotik", "firewall",
        "cloud", "cloud computing", "cloud infrastructure", "aws", "amazon web services",
        "gcp", "google cloud platform", "azure", "microsoft azure",
        "backup & recovery", "backup and recovery", "backup & restore", "backup and restore",
        "disaster recovery", "business continuity", "veeam",
        "monitoring", "system monitoring", "network monitoring", "observability",
        "prometheus", "grafana", "nagios", "zabbix", "datadog", "elk stack",
        "virtualization", "vmware", "vsphere", "hyper-v", "proxmox", "kvm",
        "active directory", "ldap", "group policy", "server administration",
        "system administration", "sysadmin", "bash", "powershell", "shell scripting", "ansible",
        "jaringan", "jaringan komputer", "administrasi jaringan", "administrasi server",
        "administrasi sistem", "komputasi awan", "pencadangan dan pemulihan",
        "pemulihan bencana", "pemantauan", "pemantauan sistem", "virtualisasi",
    ],
    "Cybersecurity": [
        "incident response", "incident management", "digital forensics", "csirt",
        "vulnerability assessment", "vulnerability management", "penetration testing",
        "pentest", "vapt", "owasp", "security auditing",
        "siem", "security information and event management", "splunk", "qradar",
        "wazuh", "elastic siem", "log analysis",
        "iso 27001", "iso/iec 27001", "nist cybersecurity framework", "nist csf",
        "cis controls", "pci-dss", "gdpr", "information security", "cyber defense",
        "access control", "identity and access management", "iam", "rbac",
        "privilege access management", "pam", "multi-factor authentication", "mfa", "zero trust",
        "security monitoring", "soc", "security operations center", "threat hunting",
        "threat intelligence", "edr", "endpoint detection and response", "ids/ips",
        "waf", "network security", "antivirus", "malware analysis", "cryptography",
        "keamanan informasi", "keamanan siber", "penanganan insiden", "penilaian kerentanan",
        "uji penetrasi", "kontrol akses", "pemantauan keamanan",
    ],
    "HR & Talent Acquisition": [
        "sourcing", "candidate sourcing", "talent sourcing", "headhunting",
        "boolean search", "linkedin recruiter", "recruitment coordination",
        "recruitment", "talent acquisition",
        "screening", "candidate screening", "resume screening", "cv screening",
        "structured interviewing", "behavioral interview", "competency-based interview",
        "hris", "human resources information system", "workday", "bamboohr",
        "darwinbox", "talenta", "mekari",
        "ats", "applicant tracking system", "greenhouse", "lever", "workable", "recruitee",
        "employee relations", "industrial relations", "labor relations", "labor law",
        "workplace conflict", "disciplinary action", "employee engagement", "employee retention",
        "l&d", "learning and development", "training & development", "training and development",
        "training needs analysis", "tna", "instructional design", "curriculum design",
        "training facilitation", "training delivery", "training evaluation", "kirkpatrick model",
        "learning management system", "lms", "e-learning",
        "talent management", "onboarding", "offboarding", "performance management",
        "performance appraisal", "kpi", "okr",
        "compensation and benefits", "compensation & benefits", "comp & ben", "remuneration",
        "job evaluation", "salary benchmarking", "payroll administration",
        "workforce planning", "manpower planning", "recruitment metrics", "time to hire",
        "cost per hire", "people analytics", "hr analytics", "employer branding",
        "hr operations", "hr policy and compliance",
        "pencarian kandidat", "penyaringan", "skrining cv", "wawancara terstruktur",
        "hubungan karyawan", "hubungan industrial", "pelatihan dan pengembangan",
        "evaluasi pelatihan", "analisis kebutuhan pelatihan", "manajemen bakat",
        "penilaian kinerja", "kompensasi dan benefit", "perencanaan tenaga kerja",
    ],
    "Accounting & Finance": [
        "bookkeeping", "double-entry bookkeeping",
        "general ledger", "gl", "journal entries", "chart of accounts",
        "accounts payable", "ap", "vendor invoicing", "invoice processing",
        "accounts receivable", "ar", "billing", "invoicing", "collection",
        "month-end close", "year-end close", "period-end close", "accruals", "prepayments",
        "tax reporting", "taxation", "tax compliance", "tax planning",
        "pph", "pph 21", "pph 23", "pph 25", "pph 26", "pph 4(2)", "pph final",
        "ppn", "value added tax", "vat", "e-faktur", "e-spt", "spt tahunan", "spt masa",
        "payroll", "payroll processing", "salary administration", "timekeeping",
        "wage calculation", "payroll reconciliation", "bpjs ketenagakerjaan", "bpjs kesehatan",
        "bank reconciliation", "cash management", "petty cash", "account reconciliation",
        "financial reporting", "financial statements", "balance sheet", "income statement",
        "profit & loss", "cash flow statement", "psak", "ifrs", "gaap",
        "cost accounting", "budgeting", "financial planning & analysis", "fp&a",
        "auditing", "internal audit", "external audit", "internal controls", "sox compliance",
        "accounting software", "erp", "sap", "oracle financials", "microsoft dynamics",
        "odoo", "accurate", "jurnal", "jurnal by mekari", "quickbooks", "xero",
        "excel", "microsoft excel", "spreadsheet",
        "pembukuan", "tata buku", "buku besar", "jurnal umum",
        "hutang usaha", "utang usaha", "piutang usaha", "piutang",
        "tutup buku bulanan", "tutup buku", "penutupan buku", "closing bulanan",
        "perpajakan", "pelaporan pajak", "pajak", "penggajian", "pemrosesan gaji",
        "rekonsiliasi bank", "laporan keuangan", "neraca", "laporan laba rugi",
        "arus kas", "akuntansi biaya", "penganggaran", "audit internal",
        "pengendalian internal", "software akuntansi",
    ],
}

DOMAINS: list[str] = list(SKILLS_BY_DOMAIN.keys())

# Soft skills and general professional capabilities
SOFT_SKILLS: list[str] = [
    "cross-functional collaboration", "cross functional collaboration",
    "project management", "stakeholder management", "communication",
    "problem solving", "critical thinking", "teamwork", "leadership",
    "time management", "kolaborasi lintas fungsi", "manajemen proyek",
    "komunikasi", "kepemimpinan",
]

# Baseline skills from server.py to guarantee complete backwards compatibility
ORIGINAL_SERVER_SKILLS: list[str] = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "golang",
    "rust", "sql", "postgresql", "mysql", "mongodb", "redis", "fastapi", "django",
    "flask", "react", "react.js", "node.js", "node", "next.js", "vue", "angular",
    "html", "css", "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
    "linux", "git", "machine learning", "deep learning", "pytorch", "tensorflow",
    "scikit-learn", "nlp", "llm", "rag", "data analysis", "pandas", "spark",
    "airflow", "tableau", "power bi", "project management", "agile", "scrum",
    "stakeholder management", "cross-functional collaboration", "communication",
]

# Consolidated unique skills list
_ALL_SKILLS_SET: dict[str, None] = {}
for s in ORIGINAL_SERVER_SKILLS:
    _ALL_SKILLS_SET[s.lower()] = None
for domain_skills in SKILLS_BY_DOMAIN.values():
    for s in domain_skills:
        _ALL_SKILLS_SET[s.lower()] = None
for s in SOFT_SKILLS:
    _ALL_SKILLS_SET[s.lower()] = None

SKILLS: list[str] = list(_ALL_SKILLS_SET.keys())

# ---------------------------------------------------------------------------
# Bilingual Term Synonyms & Translations (English <-> Indonesian)
# ---------------------------------------------------------------------------

BILINGUAL_PAIRS: list[tuple[str, str]] = [
    ("software engineering", "rekayasa perangkat lunak"),
    ("software development", "pengembangan perangkat lunak"),
    ("programming", "pemrograman"),
    ("machine learning", "pembelajaran mesin"),
    ("deep learning", "pembelajaran mendalam"),
    ("data analysis", "analisis data"),
    ("project management", "manajemen proyek"),
    ("automated testing", "pengujian otomatis"),
    ("computer networking", "jaringan komputer"),
    ("server administration", "administrasi server"),
    ("system monitoring", "pemantauan sistem"),
    ("backup and recovery", "pencadangan dan pemulihan"),
    ("cloud computing", "komputasi awan"),
    ("cloud infrastructure", "infrastruktur cloud"),
    ("incident response", "penanganan insiden"),
    ("vulnerability assessment", "penilaian kerentanan"),
    ("penetration testing", "uji penetrasi"),
    ("access control", "kontrol akses"),
    ("security monitoring", "pemantauan keamanan"),
    ("information security", "keamanan informasi"),
    ("cybersecurity", "keamanan siber"),
    ("candidate sourcing", "pencarian kandidat"),
    ("resume screening", "skrining cv"),
    ("candidate screening", "penyaringan kandidat"),
    ("structured interviewing", "wawancara terstruktur"),
    ("employee relations", "hubungan karyawan"),
    ("industrial relations", "hubungan industrial"),
    ("learning and development", "pelatihan dan pengembangan"),
    ("training evaluation", "evaluasi pelatihan"),
    ("training needs analysis", "analisis kebutuhan pelatihan"),
    ("instructional design", "desain instruksional"),
    ("training facilitation", "fasilitasi pelatihan"),
    ("talent management", "manajemen bakat"),
    ("performance management", "manajemen kinerja"),
    ("performance appraisal", "penilaian kinerja"),
    ("compensation and benefits", "kompensasi dan benefit"),
    ("workforce planning", "perencanaan tenaga kerja"),
    ("bookkeeping", "pembukuan"),
    ("general ledger", "buku besar"),
    ("accounts payable", "hutang usaha"),
    ("accounts receivable", "piutang usaha"),
    ("month-end close", "tutup buku bulanan"),
    ("tax reporting", "pelaporan pajak"),
    ("taxation", "perpajakan"),
    ("payroll processing", "pemrosesan penggajian"),
    ("payroll", "penggajian"),
    ("bank reconciliation", "rekonsiliasi bank"),
    ("financial statements", "laporan keuangan"),
    ("financial reporting", "laporan keuangan"),
    ("internal controls", "pengendalian internal"),
    ("auditing", "pemeriksaan keuangan"),
    ("internal audit", "audit internal"),
    ("cost accounting", "akuntansi biaya"),
    ("budgeting", "penganggaran"),
    ("cross-functional collaboration", "kolaborasi lintas fungsi"),
    ("stakeholder management", "manajemen pemangku kepentingan"),
    ("communication", "komunikasi"),
]

# ---------------------------------------------------------------------------
# Comprehensive ALIASES Mapping
# Acronyms, spelling variations, bilingual synonyms, and multi-word terms
# ---------------------------------------------------------------------------

ALIASES: dict[str, list[str]] = {
    # Software Engineering & Programming
    "python": ["python", "python3", "py"],
    "javascript": ["javascript", "js", "ecmascript"],
    "typescript": ["typescript", "ts"],
    "c++": ["c++", "cpp"],
    "c#": ["c#", "csharp", "c sharp"],
    "go": ["go", "golang"],
    "golang": ["go", "golang"],
    "java": ["java"],
    "rust": ["rust"],
    "sql": ["sql", "structured query language"],
    "postgresql": ["postgresql", "postgres", "postgres db", "psql"],
    "mysql": ["mysql"],
    "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"],
    "docker": ["docker", "containerization", "docker container", "kontainer docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "terraform": ["terraform"],
    "git": ["git", "github", "gitlab", "version control", "kontrol versi"],
    "rest api": ["rest api", "restful api", "rest", "restful web services", "rest apis", "api rest"],
    "graphql": ["graphql"],
    "grpc": ["grpc"],
    "fastapi": ["fastapi", "fast api"],
    "django": ["django"],
    "flask": ["flask"],
    "react": ["react", "react.js", "reactjs"],
    "node.js": ["node.js", "nodejs", "node"],
    "next.js": ["next.js", "nextjs", "next"],
    "vue": ["vue", "vue.js", "vuejs"],
    "angular": ["angular", "angular.js", "angularjs"],
    "html": ["html", "html5"],
    "css": ["css", "css3", "tailwind", "tailwind css", "sass"],
    "machine learning": ["machine learning", "ml", "pembelajaran mesin"],
    "deep learning": ["deep learning", "dl", "pembelajaran mendalam"],
    "nlp": ["nlp", "natural language processing", "pemrosesan bahasa alami"],
    "llm": ["llm", "large language model", "large language models"],
    "rag": ["rag", "retrieval augmented generation", "retrieval-augmented generation"],
    "data analysis": ["data analysis", "analisis data", "data analytics"],
    "automated testing": [
        "automated testing", "pengujian otomatis", "automation testing",
        "test automation", "unit testing", "integration testing",
    ],
    "programming": ["programming", "pemrograman", "coding", "software programming"],
    "software development": [
        "software development", "pengembangan perangkat lunak",
        "software engineering", "rekayasa perangkat lunak", "software developer",
    ],
    "agile": ["agile", "agile methodology", "metodologi agile"],
    "scrum": ["scrum", "scrum master", "sprint"],
    "ci/cd": ["ci/cd", "ci cd", "continuous integration", "continuous deployment"],
    "cross-functional collaboration": [
        "cross-functional collaboration", "cross functional collaboration",
        "worked across teams", "cross-functional team", "kolaborasi lintas fungsi", "kerja sama tim",
    ],

    # IT Infrastructure & Networking
    "linux": ["linux", "gnu/linux", "ubuntu", "centos", "debian", "red hat"],
    "windows server": ["windows server", "win server", "server windows"],
    "networking": [
        "networking", "computer networking", "jaringan", "jaringan komputer",
        "network administration", "administrasi jaringan", "tcp/ip",
    ],
    "computer networking": [
        "computer networking", "networking", "jaringan komputer", "jaringan",
        "network administration", "administrasi jaringan", "tcp/ip",
    ],
    "cloud infrastructure": [
        "cloud infrastructure", "infrastruktur cloud", "cloud computing",
        "cloud", "komputasi awan",
    ],
    "cloud": ["cloud", "cloud computing", "komputasi awan", "cloud infrastructure"],
    "aws": ["aws", "amazon web services"],
    "gcp": ["gcp", "google cloud platform", "google cloud"],
    "azure": ["azure", "microsoft azure"],
    "backup & recovery": [
        "backup & recovery", "backup and recovery", "backup & restore", "backup and restore",
        "pencadangan dan pemulihan", "pencadangan", "disaster recovery", "pemulihan bencana",
    ],
    "backup and recovery": [
        "backup and recovery", "backup & recovery", "backup & restore", "backup and restore",
        "pencadangan dan pemulihan", "pencadangan", "disaster recovery", "pemulihan bencana",
    ],
    "monitoring": [
        "monitoring", "system monitoring", "network monitoring", "pemantauan sistem",
        "pemantauan", "observability", "observabilitas",
    ],
    "system monitoring": [
        "system monitoring", "monitoring", "network monitoring", "pemantauan sistem",
        "pemantauan", "observability",
    ],
    "server administration": [
        "server administration", "administrasi server", "system administration",
        "administrasi sistem", "sysadmin",
    ],
    "virtualization": ["virtualization", "virtualisasi", "vmware", "hyper-v", "proxmox"],

    # Cybersecurity
    "incident response": [
        "incident response", "ir", "penanganan insiden", "respon insiden",
        "incident management", "manajemen insiden keamanan",
    ],
    "vulnerability assessment": [
        "vulnerability assessment", "va", "penilaian kerentanan", "asesmen kerentanan",
        "vulnerability management", "vapt",
    ],
    "penetration testing": [
        "penetration testing", "pentest", "pen testing", "uji penetrasi", "pengetesan penetrasi",
    ],
    "siem": [
        "siem", "security information and event management",
        "splunk", "qradar", "wazuh", "elastic siem",
    ],
    "iso 27001": [
        "iso 27001", "iso27001", "iso/iec 27001", "iso-27001", "standar iso 27001",
    ],
    "nist cybersecurity framework": [
        "nist cybersecurity framework", "nist csf", "nist", "kerangka kerja nist",
    ],
    "access control": [
        "access control", "kontrol akses", "pengendalian akses",
        "iam", "identity and access management", "rbac", "role-based access control",
    ],
    "security monitoring": [
        "security monitoring", "pemantauan keamanan", "soc", "security operations center",
    ],
    "information security": [
        "information security", "infosec", "keamanan informasi", "cybersecurity", "keamanan siber",
    ],

    # HR & Talent Acquisition
    "sourcing": [
        "sourcing", "candidate sourcing", "talent sourcing", "pencarian kandidat", "sumber kandidat",
    ],
    "candidate sourcing": [
        "candidate sourcing", "sourcing", "talent sourcing", "pencarian kandidat", "sumber kandidat",
    ],
    "screening": [
        "screening", "candidate screening", "resume screening", "penyaringan", "skrining",
        "penyaringan kandidat", "skrining cv", "cv screening",
    ],
    "resume screening": [
        "resume screening", "screening", "candidate screening", "penyaringan", "skrining cv",
        "penyaringan cv", "skrining resume",
    ],
    "structured interviewing": [
        "structured interviewing", "structured interview", "wawancara terstruktur",
        "competency-based interview", "behavioral interview", "wawancara berbasis kompetensi",
    ],
    "recruitment coordination": [
        "recruitment coordination", "koordinasi rekrutmen", "talent acquisition", "rekrutmen", "recruitment",
    ],
    "hris": [
        "hris", "human resources information system", "sistem informasi sdm",
        "sistem informasi sumber daya manusia", "hr system", "aplikasi hris",
    ],
    "ats": [
        "ats", "applicant tracking system", "sistem pelacak pelamar", "sistem tracking pelamar",
    ],
    "applicant tracking system": [
        "applicant tracking system", "ats", "sistem pelacak pelamar", "sistem tracking pelamar",
    ],
    "employee relations": [
        "employee relations", "er", "hubungan karyawan", "hubungan industrial",
        "industrial relations", "hubungan kerja",
    ],
    "labor relations": [
        "labor relations", "hubungan ketenagakerjaan", "hubungan industrial", "hukum ketenagakerjaan",
    ],
    "l&d": [
        "l&d", "learning and development", "learning & development", "training & development",
        "training and development", "t&d", "pelatihan dan pengembangan", "diklat",
    ],
    "training evaluation": [
        "training evaluation", "evaluasi pelatihan", "evaluasi efektivitas pelatihan",
        "kirkpatrick", "kirkpatrick model",
    ],
    "training needs analysis": [
        "training needs analysis", "tna", "analisis kebutuhan pelatihan", "analisa kebutuhan pelatihan",
    ],
    "instructional design": [
        "instructional design", "desain instruksional", "perancangan kurikulum", "curriculum design",
    ],
    "training facilitation": [
        "training facilitation", "fasilitasi pelatihan", "training delivery", "pelatihan",
    ],
    "learning management system": [
        "learning management system", "lms", "sistem manajemen pembelajaran",
    ],
    "e-learning": ["e-learning", "elearning", "pembelajaran daring"],
    "talent management": ["talent management", "manajemen bakat"],
    "performance management": [
        "performance management", "manajemen kinerja", "penilaian kinerja",
        "performance appraisal", "kpi", "okr",
    ],
    "compensation and benefits": [
        "compensation and benefits", "compensation & benefits", "comp & ben",
        "kompensasi dan benefit", "remunerasi", "remuneration", "kompensasi",
    ],
    "workforce planning": [
        "workforce planning", "perencanaan tenaga kerja", "manpower planning", "perencanaan sdm",
    ],
    "hr policy and compliance": [
        "hr policy and compliance", "kebijakan hr", "kepatuhan sdm", "hr compliance", "peraturan perusahaan",
    ],
    "hr operations": [
        "hr operations", "operasional hr", "operasional sdm", "hr generalist",
    ],
    "recruitment metrics": [
        "recruitment metrics", "metrik rekrutmen", "time to hire", "cost per hire", "hr analytics",
    ],
    "hr analytics": [
        "hr analytics", "people analytics", "analitik sdm", "analitik hr",
    ],

    # Accounting & Finance
    "bookkeeping": [
        "bookkeeping", "pembukuan", "tata buku", "pencatatan keuangan", "pencatatan transaksi",
    ],
    "general ledger": [
        "general ledger", "gl", "buku besar", "buku besar umum", "jurnal umum",
    ],
    "accounts payable": [
        "accounts payable", "ap", "a/p", "hutang usaha", "utang usaha", "hutang dagang", "utang dagang",
    ],
    "accounts receivable": [
        "accounts receivable", "ar", "a/r", "piutang usaha", "piutang", "piutang dagang",
    ],
    "invoice processing": [
        "invoice processing", "pemrosesan invoice", "pemrosesan faktur", "verifikasi faktur", "penagihan",
    ],
    "month-end close": [
        "month-end close", "month end close", "tutup buku bulanan", "tutup buku",
        "penutupan buku", "closing bulanan", "monthly closing", "period-end close",
    ],
    "tax reporting": [
        "tax reporting", "taxation", "perpajakan", "pelaporan pajak", "pajak",
        "spt", "spt tahunan", "spt masa", "pph", "ppn", "e-faktur", "e-spt", "tax compliance",
    ],
    "payroll": [
        "payroll", "penggajian", "gaji", "payroll processing", "pemrosesan gaji",
        "salary administration", "perhitungan gaji",
    ],
    "payroll processing": [
        "payroll processing", "pemrosesan penggajian", "pemrosesan gaji", "proses payroll", "payroll", "penggajian",
    ],
    "timekeeping": [
        "timekeeping", "pencatatan kehadiran", "absensi", "time and attendance", "manajemen waktu kerja",
    ],
    "wage calculation": [
        "wage calculation", "perhitungan upah", "perhitungan gaji", "kalkulasi gaji", "tunjangan",
    ],
    "payroll reconciliation": [
        "payroll reconciliation", "rekonsiliasi payroll", "rekonsiliasi gaji",
    ],
    "payroll system": [
        "payroll system", "sistem payroll", "sistem penggajian", "aplikasi payroll",
    ],
    "payroll reporting": [
        "payroll reporting", "pelaporan payroll", "laporan gaji", "laporan penggajian",
    ],
    "bank reconciliation": [
        "bank reconciliation", "rekonsiliasi bank", "bank recon", "rekonsiliasi rekening",
    ],
    "financial statements": [
        "financial statements", "laporan keuangan", "financial reporting",
        "neraca", "balance sheet", "laporan laba rugi", "income statement", "arus kas", "cash flow",
    ],
    "financial reporting": [
        "financial reporting", "laporan keuangan", "financial statements", "pelaporan keuangan",
    ],
    "account reconciliation": [
        "account reconciliation", "rekonsiliasi akun", "rekonsiliasi saldo",
    ],
    "internal controls": [
        "internal controls", "kontrol internal", "pengendalian internal", "internal control",
    ],
    "accounting software": [
        "accounting software", "software akuntansi", "perangkat lunak akuntansi",
        "accurate", "jurnal", "jurnal by mekari", "quickbooks", "xero",
    ],
    "erp": [
        "erp", "enterprise resource planning", "sap", "oracle", "odoo", "microsoft dynamics",
    ],
    "excel": [
        "excel", "microsoft excel", "ms excel", "spreadsheet", "vlookup", "pivot table",
    ],
}

# Auto-expand ALIASES bidirectional mappings so looking up an Indonesian translation
# or acronym directly finds all members of the alias group.
for _key, _variants in list(ALIASES.items()):
    for _variant in _variants:
        if _variant not in ALIASES:
            ALIASES[_variant] = _variants

# ---------------------------------------------------------------------------
# Education Level Patterns
# Doctorate/S3, Master/S2/Magister, Bachelor/S1/Sarjana, Associate/D3/Diploma
# ---------------------------------------------------------------------------

EDUCATION_LEVEL_PATTERNS: list[tuple[str, str]] = [
    (r"\b(ph\.?d|doctorate|doktor|s-?3|strata\s*3)\b", "Doctorate"),
    (r"\b(master'?s?|magister|m\.s\.|m\.sc\.|mba|m\.kom|m\.m\.|m\.si|m\.t\.|s-?2|strata\s*2)\b", "Master's"),
    (r"\b(bachelor'?s?|sarjana|b\.s\.|b\.sc\.|b\.a\.|b\.eng|s-?1|strata\s*1|s\.kom|s\.t\.|s\.e\.|s\.si|s\.ked|s\.sos|s\.h\.|s\.ak)\b", "Bachelor's"),
    (r"\b(associate'?s?|diploma|ahli\s*madya|d-?3|d-?4|a\.md)\b", "Associate's"),
]

# ---------------------------------------------------------------------------
# Experience Years Extraction Patterns
# Supports Indonesian ("3 tahun", "pengalaman 5 tahun", "3 thn")
# and English ("5 years", "3+ yrs", "over 4 years of experience")
# ---------------------------------------------------------------------------

EXPERIENCE_YEARS_PATTERNS: list[str] = [
    r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?|tahun|thn)\b",
    r"\bpengalaman\s*(?:kerja)?\s*(?:selama)?\s*[:>]?\s*(\d{1,2})\b",
    r"\b(?:over|more than|minimal|minimum|sekitar|kurang lebih)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?|tahun|thn)\b",
    r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?|tahun|thn)\s*(?:of\s+)?(?:experience|pengalaman)\b",
]


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def normalize_text(value: str) -> str:
    """Normalize text by folding case, normalizing dashes, and stripping whitespace."""
    return re.sub(r"\s+", " ", value.casefold().replace("–", "-")).strip()


def match_education_levels(text: str) -> list[str]:
    """Extract mentioned education levels in normalized text, preserving standard labels."""
    ntext = normalize_text(text)
    matched: list[str] = []
    for pattern, label in EDUCATION_LEVEL_PATTERNS:
        if re.search(pattern, ntext):
            if label not in matched:
                matched.append(label)
    return matched


def extract_experience_years(text: str) -> int | None:
    """Extract maximum mentioned years of experience from Indonesian or English text."""
    ntext = normalize_text(text)
    found_years: list[int] = []
    for pattern in EXPERIENCE_YEARS_PATTERNS:
        matches = re.findall(pattern, ntext)
        for m in matches:
            try:
                val = int(m)
                if 1 <= val <= 50:
                    found_years.append(val)
            except ValueError:
                continue
    return max(found_years, default=None)


def get_skills_by_domain(domain: str) -> list[str]:
    """Retrieve list of skills for a given domain."""
    return SKILLS_BY_DOMAIN.get(domain, [])


def get_all_domains() -> list[str]:
    """Retrieve all supported taxonomy domains."""
    return list(SKILLS_BY_DOMAIN.keys())
