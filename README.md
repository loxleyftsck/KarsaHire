# KarsaHire — Explainable AI Recruitment Copilot

KarsaHire adalah purwarupa copilot rekrutmen kolaboratif lokal (*explainable, evidence-first recruitment copilot*) yang dirancang untuk tim rekrutmen modern (Recruiter & Hiring Manager). KarsaHire membantu tim menyepakati kriteria secara objektif sebelum membaca berkas pelamar, mengekstrak bukti (*evidence snippet*) langsung dari CV, mencegah bias kognitif melalui mode *blind-first review*, serta memelihara jejak audit yang transparan tanpa bergantung pada model ranking *black-box* atau halusinasi LLM.

Lihat [Rencana Arsitektur KarsaHire](KarsaHire-Architecture-Plan.md) untuk cetak biru sistem, tata kelola data, dan mitigasi bias yang lebih komprehensif.

---

## Daftar Isi

1. [Arsitektur Modular](#arsitektur-modular)
2. [Fitur Antarmuka Workspace (/app)](#fitur-antarmuka-workspace-app)
3. [Panduan Menjalankan Aplikasi](#panduan-menjalankan-aplikasi)
4. [Menjalankan Automated Test Suite](#menjalankan-automated-test-suite)
5. [Skema Database SQLite](#skema-database-sqlite)
6. [Dokumentasi API Outline](#dokumentasi-api-outline)
7. [OCR Lokal (PaddleOCR) & OCR API Internal](#ocr-lokal-paddleocr--ocr-api-internal)
8. [Prinsip Tata Kelola, Privasi, & Explainability](#prinsip-tata-kelola-privasi--explainability)

---

## Arsitektur Modular

KarsaHire dibangun dengan arsitektur modular berbasis Python standar yang terstruktur, modular, dan teruji tanpa ketergantungan tersembunyi pada model eksternal:

```
KarsaHire/
├── matching.py             # Engine pencocokan leksikal, PII redaction, & weighted scoring
├── taxonomy.py             # Taksonomi keahlian bilingual (ID/EN), gelar, & pengalaman kerja
├── rag_service.py          # Grounded RAG retrieval berbasis BM25 token overlap (tanpa LLM)
├── interview_service.py    # Structured interview scorecards (rubrik 1-5 & komparasi peran)
├── analytics_service.py    # Hiring analytics (funnel, inter-rater consensus, criteria health)
├── export_service.py       # Ekspor data kandidat ke CSV, evidence CSV, & JSON debrief
├── server.py               # HTTP server multithreaded, endpoint REST, & static handler
├── ocr_local.py            # Local on-device OCR wrapper berbasis PP-OCRv6 CPU
├── database/
│   └── schema.sql          # Skema canonical SQLite bersyarat FK & indeks teroptimasi
└── web/                    # Antarmuka web vanilla responsif (HTML5, modern CSS, ES Modules)
```

### 1. `matching.py` — Engine Pencocokan Leksikal & Redaksi PII
- **Transparent Lexical Matching**: Menggunakan pencocokan deterministik berbasis token dan frasa persis (*exact lexical match*) serta token parsial (*partial match*). Status kecocokan diklasifikasikan tegas menjadi `matched` (skor 1.0), `partial` (skor 0.5), atau `unknown` (skor 0.0). Tidak ada prediksi probabilitas acak.
- **Scoring Berbobot (Weighted Scoring)**: Menghitung skor persentase kandidat (0–100%) dengan bobot kriteria eksplisit: kriteria **Wajib (Required)** berbobot 2.0 dan kriteria **Diutamakan (Preferred)** berbobot 1.0.
- **PII Redaction Safeguards**: Secara otomatis menyaring informasi sensitif dan kontak langsung dari cuplikan bukti (*evidence snippet*) sebelum disimpan ke SQLite (email, nomor telepon lokal/internasional, tanggal lahir, dan header nama langsung).

### 2. `taxonomy.py` — Taksonomi Keahlian Bilingual & Ekstraksi Profil
- **Domain Taxonomies**: Mencakup ribuan keterampilan dan konsep kerja di 5 domain inti:
  1. *Software Engineering & Programming* (Python, FastAPI, PostgreSQL, Docker, CI/CD, React, dll.)
  2. *IT Infrastructure & Networking* (Linux, Cisco, Active Directory, Cloud AWS/GCP/Azure, Disaster Recovery, dll.)
  3. *Cybersecurity* (Incident Response, Penetration Testing, SIEM, ISO 27001, NIST CSF, Access Control, dll.)
  4. *HR & Talent Acquisition* (Sourcing, ATS, Behavioral Interview, HRIS, Industrial Relations, L&D, dll.)
  5. *Accounting & Finance Ops* (Bookkeeping, General Ledger, Accounts Payable/Receivable, PPh/PPN, ERP, dll.)
- **Bilingual Synonyms & Aliases (ID/EN)**: Kamus sinonim bilingual otomatis dua arah (misalnya `pembukuan` ↔ `bookkeeping`, `penyaringan cv` ↔ `resume screening`, `rekayasa perangkat lunak` ↔ `software engineering`, serta akronim seperti `AP`, `AR`, `GL`, `TNA`).
- **Normalisasi Gelar Pendidikan**: Regex multi-pola untuk mendeteksi kualifikasi pendidikan formal:
  - *Doctorate / S3* (Ph.D, Doktor, Strata 3)
  - *Master's / S2* (Magister, M.Sc, MBA, M.Kom, M.M, Strata 2)
  - *Bachelor's / S1* (Sarjana, S.Kom, S.T, S.E, S.Si, B.Sc, B.A, Strata 1)
  - *Associate's / D3 / D4* (Diploma, Ahli Madya, D3, D4, A.Md)
- **Ekstraksi Pengalaman Kerja**: Pola regex bilingual untuk mendeteksi lama pengalaman kerja kandidat dalam tahun (misal: `"5 tahun"`, `"3+ years"`, `"pengalaman minimal 4 tahun"`).

### 3. `rag_service.py` — Grounded Internal RAG Retrieval (BM25 Token Overlap)
- **Zero-Hallucination Retrieval**: Dirancang khusus untuk fitur *Tanya Requisition* tanpa memanggil model bahasa publik (LLM). Pencarian murni berbasis penelusuran leksikal yang memvalidasi kebenaran sumber (*grounded retrieval*).
- **Multi-Source Weighted Indexing**: Memindai deskripsi lowongan, kriteria wajib & preferensi berbobot, panduan wawancara berbasis kerangka STAR (*Situation, Task, Action, Result*), dan rubrik kompetensi terstruktur.
- **BM25 & Token Overlap Ranking**: Mempertahankan identitas teknis khusus (misalnya `C++`, `.NET`, `CI/CD`, `Node.js`), menerapkan penyaringan kata henti dwibahasa (*bilingual stop words*), penguatan bobot istilah teknis (*technical term boost*), dan bonus pencocokan frasa multi-token.

### 4. `interview_service.py` — Scorecard Wawancara Terstruktur & Komparasi Peran
- **Standardized Rubric Scale 1–5**:
  - `1`: *Tidak memadai* (Unsatisfactory / Poor)
  - `2`: *Kurang* (Below Expectations / Needs Improvement)
  - `3`: *Memenuhi syarat* (Meets Expectations / Competent)
  - `4`: *Kuat* (Strong / Above Expectations)
  - `5`: *Luar biasa* (Outstanding / Exceptional)
- **Structured Scorecards**: Mencatat penilaian kandidat per kriteria, catatan bukti konkret (*STAR evidence notes*), rekomendasi akhir (`hire`, `strong_hire`, `no_hire`, `advance`), dan catatan pewawancara.
- **Komparasi Dual-Role (Recruiter vs Hiring Manager)**: Menghitung rata-rata skor keseluruhan, rata-rata skor per peran reviewer, breakdown per kriteria, serta mendeteksi konsensus maupun perbedaan pandangan (*divergence*) antar pewawancara.

### 5. `analytics_service.py` — Recruitment Analytics & Governance Metrics
- **Job Funnel Analysis**: Metrik konversi pipeline seleksi (`needs_review`, `advance`, `needs_info`, `not_selected`), distribusi persentase status, serta nilai skor bukti (rata-rata, minimum, maksimum).
- **Inter-Rater Consensus Agreement**: Menghitung rasio konsensus kesepakatan (% kesesuaian keputusan) antara Recruiter dan Hiring Manager untuk kandidat yang dievaluasi kedua peran (*dual-reviewed*), serta mendaftar kasus divergensi (*override/mismatch*) untuk bahan rapat debrief tim.
- **Criteria Bottleneck & Health Diagnostics**: Mendiagnosis kesehatan kriteria requisition:
  - *Bottleneck Warning*: Kriteria terlalu ketat jika persentase bukti tidak ditemukan (*unknown*) > 80%.
  - *Too-Common Warning*: Kriteria tidak memiliki daya pembeda jika persentase bukti cocok (*matched*) > 90%.
  - Memberikan rekomendasi penyesuaian kriteria untuk tim rekrutmen.

### 6. `export_service.py` — Ekspor Data & Audit Trail Lengkap
- **Rekap Kandidat ke CSV (`export_candidates_csv`)**: Menghasilkan file CSV berstandar Excel (UTF-8 BOM) yang mencakup ID kandidat, skor bukti, status, ringkasan skill, pengalaman, pendidikan, dan keputusan reviewer.
- **Rincian Evidence ke CSV (`export_evidence_csv`)**: Menghasilkan audit rincian bukti per kriteria untuk setiap kandidat lengkap dengan jenis kriteria, bobot, hasil (`matched`/`partial`/`unknown`), confidence, cuplikan teks (*snippet*), dan nomor halaman CV.
- **Debrief Lengkap ke JSON (`export_job_report_json`)**: Menghasilkan berkas JSON komprehensif berisi metadata lowongan, kriteria yang disetujui, approver, seluruh profil dan evidence kandidat, riwayat review, serta seluruh jejak `audit_events`.

---

## Fitur Antarmuka Workspace (/app)

Antarmuka web KarsaHire dirancang khusus untuk alur kerja tim rekrutmen kolaboratif dengan fitur-fitur modern:

1. **Pencarian & Sorting Fleksibel**:
   - **Pencarian Real-Time**: Pencarian instan kandidat berdasarkan potongan ID kandidat, keahlian (*skills*), tingkat pendidikan, format file, atau kata kunci profil.
   - **Multi-Option Sorting**: Pilihan pengurutan dinamis: *Nilai tertinggi (default)*, *Nilai terendah*, *Terbaru diunggah*, dan *Terlama diunggah*.
   - **Filter Status**: Filter cepat satu klik untuk melihat status *Semua*, *Perlu review*, *Lanjut proses*, *Perlu informasi*, atau *Tidak lanjut*.

2. **Mode Review Buta (Blind-First Review Mode)**:
   - Disediakan tombol toggle **Mode Buta** untuk memitigasi bias kognitif dan bias afinitas saat peninjauan berkas tahap awal.
   - Menyamarkan nama pelamar, nama file CV asli, dan avatar dengan identifikasi netral (misalnya *Kandidat Anonim A*, *Kandidat Anonim B* dan *CV Terstandarisasi*).
   - Memastikan reviewer mengevaluasi kandidat murni berdasarkan kecocokan bukti obyektif terhadap kriteria yang telah disepakati.

3. **Modal Perbandingan Kandidat Berdampingan (Side-by-Side Comparison)**:
   - Pengguna dapat memilih 2 hingga 3 kandidat melalui checkbox untuk dibandingkan secara sejajar (*side-by-side*).
   - Menampilkan matriks perbandingan per kriteria secara terstruktur dan otomatis menyorot kriteria yang memiliki perbedaan bukti (*diff highlight*).
   - Dilengkapi form evaluasi cepat (*quick review*) di dalam modal untuk mencatat keputusan langsung ke audit trail saat membandingkan.

4. **Modal Analisis Seleksi (Debrief Analytics Modal)**:
   - Menyajikan dashboard visual metrik seleksi untuk rapat debrief tim rekrutmen:
     - *Pipeline Funnel*: Grafik konversi status pelamar dan rentang skor bukti.
     - *Inter-Rater Consensus*: Tingkat keselarasan Recruiter vs Hiring Manager beserta daftar kandidat yang memiliki perbedaan keputusan.
     - *Criteria Health*: Status kesehatan kriteria yang mengidentifikasi *bottleneck* (terlalu sulit) atau kriteria yang kurang diskriminatif.

5. **Form Scorecard Wawancara Terstruktur**:
   - Form pencatatan hasil wawancara terstandarisasi berbasis skala rubrik 1–5 untuk tiap kompetensi.
   - Kolom catatan bukti berbasis perilaku konkret (*STAR method*) dan pilihan rekomendasi akhir yang objektif.
   - Ringkasan komparasi otomatis antara nilai Recruiter dan Hiring Manager.

6. **Tombol Ekspor CSV & JSON**:
   - **Ekspor CSV Rekap**: Mengunduh rekapitulasi data kandidat dan keputusan review dalam format CSV siap olah.
   - **Ekspor JSON Debrief**: Mengunduh seluruh data requisition, kriteria, kandidat, evidence, dan log aktivitas audit trail ke format JSON.

---

## Panduan Menjalankan Aplikasi

### Persyaratan Sistem
- Python 3.10 atau versi yang lebih baru.
- Sistem Operasi: Windows, macOS, atau Linux.

### Menjalankan Server Lokal (PowerShell / Terminal)

```powershell
# Pasang dependensi utama
python -m pip install -r requirements.txt

# Jalankan server lokal
python .\server.py
```

Setelah server aktif:
- Buka **Landing Page**: <http://127.0.0.1:8765>
- Buka **Workspace Rekrutmen**: <http://127.0.0.1:8765/app>

Port default adalah `8765`. Anda dapat mengubah port melalui environment variable `RECRUITMENT_COPILOT_PORT` bila diperlukan:
```powershell
$env:RECRUITMENT_COPILOT_PORT="8900"
python .\server.py
```

### Dataset Pengujian Sintetis (32 CV)
Repositori menyertakan corpus uji 32 CV sintetis di `data/synthetic-cv-32` yang bersumber dari [sukhrobnurali/resume-parsing-vision](https://huggingface.co/datasets/sukhrobnurali/resume-parsing-vision) (lisensi CC BY 4.0). Dataset ini sepenuhnya sintetis dan bebas dari data pribadi riil.

Alur pengujian cepat:
1. Buka Workspace (<http://127.0.0.1:8765/app>).
2. Klik **Coba dengan data sintetis** atau buat requisition baru.
3. Catat persetujuan kriteria dari kedua peran: **Recruiter** dan **Hiring Manager**.
4. Klik tombol **Muat CV uji (0/32)** untuk memuat berkas teks sintetis secara lokal tanpa memanggil OCR.

---

## Menjalankan Automated Test Suite

KarsaHire dilengkapi dengan rangkaian automated test suite menyeluruh (unit test & integration test) yang menguji endpoint server, engine pencocokan, taksonomi, internal RAG, scorecard wawancara, hiring analytics, dan export service.

Jalankan test suite menggunakan environment virtual Python:

```powershell
.\.venv-ocr\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Atau menggunakan instalasi Python standar sistem:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Untuk menjalankan file pengujian tertentu secara spesifik:
```powershell
# Pengujian server & endpoint API
python -m unittest tests/test_server.py

# Pengujian matching & taxonomy
python -m unittest tests/test_matching.py

# Pengujian RAG service & BM25 retrieval
python -m unittest tests/test_rag_service.py

# Pengujian interview service & scorecards
python -m unittest tests/test_interview.py

# Pengujian analytics & governance
python -m unittest tests/test_analytics.py
```

---

## Skema Database SQLite

Database disimpan secara lokal di `data/copilot.sqlite3` dan diinisialisasi otomatis dari [`database/schema.sql`](database/schema.sql) pada saat server dinyalakan.

| Tabel | Deskripsi & Fungsi |
|---|---|
| `jobs` | Menyimpan data lowongan (*requisition*), deskripsi peran, kriteria terstruktur JSON, status persetujuan, dan stempel waktu. |
| `approvals` | Mencatat tanda tangan persetujuan kriteria terpisah antara Recruiter dan Hiring Manager sebelum CV dapat diproses (`UNIQUE(job_id, role)`). |
| `candidates` | Menyimpan profil kandidat yang diekstrak (JSON), format file, skor kecocokan evidence (0–100), dan status review manusia. |
| `evidence` | Menyimpan rincian bukti per kriteria: ID kriteria, jenis syarat (*required*/*preferred*), bobot, hasil (*matched*/*partial*/*unknown*), nilai confidence, cuplikan teks (*snippet*), dan nomor halaman CV. |
| `reviews` | Menyimpan keputusan review manual evaluator manusia (`advance`, `needs_info`, `not_selected`), peran reviewer, dan catatan evaluasi. |
| `audit_events` | Catatan jejak audit append-only yang merekam setiap aksi sistem (pengajuan kriteria, approval, pemrosesan CV, review, scorecard, penghapusan kandidat). |
| `interview_scorecards` | Menyimpan rekaman kartu penilaian wawancara terstruktur per kandidat: reviewer, peran, rekomendasi umum (*overall recommendation*), dan catatan umum wawancara. |
| `interview_criterion_scores` | Menyimpan nilai skor rubrik 1–5 per kriteria wawancara, label kompetensi, dan catatan bukti spesifik (*STAR evidence notes*) yang terhubung ke `interview_scorecards`. |

---

## Dokumentasi API Outline

Semua endpoint API disajikan melalui protokol REST JSON lokal:

### 1. Manajemen Requisition & Persetujuan Kriteria
- `POST /api/jobs` — Membuat requisition baru beserta kriteria wajib dan preferensi.
- `GET /api/jobs` — Menampilkan daftar seluruh lowongan dan jumlah kandidat terdaftar.
- `GET /api/jobs/{id}` — Mengambil detail requisition, status approval, daftar kandidat, dan bukti evidence.
- `POST /api/jobs/{id}/approvals` — Mencatat persetujuan kriteria dari Recruiter atau Hiring Manager (kedua peran wajib menyetujui sebelum CV dapat diproses).
- `POST /api/jobs/{id}/load-synthetic-data` — Memuat corpus 32 CV uji sintetis secara idempoten setelah kriteria disetujui.
- `GET /api/jobs/{id}/events` — Menampilkan riwayat jejak audit (*audit trail*) untuk requisition tertentu.

### 2. Pemrosesan & Evaluasi Kandidat
- `POST /api/jobs/{id}/candidates` — Mengunggah dan memproses berkas CV multipart (`.txt`, `.pdf`, `.docx`, `.png`, `.jpg`). Berkas asli tidak disimpan; sistem hanya mengekstrak teks dan bukti leksikal.
- `POST /api/candidates/{id}/reviews` — Mencatat keputusan review manusia (`advance`, `needs_info`, `not_selected`) beserta catatan reviewer.
- `DELETE /api/candidates/{id}` — Menghapus data kandidat, profil, evidence, dan riwayat review dari database (event penghapusan dicatat ke audit trail).

### 3. Wawancara Terstruktur (Structured Interview Scorecards)
- `GET /api/candidates/{id}/scorecards` — Mengambil daftar scorecard wawancara kandidat beserta ringkasan komparasi nilai per peran (Recruiter vs Hiring Manager) dan breakdown kriteria.
- `POST /api/candidates/{id}/scorecards` — Menyimpan scorecard wawancara terstruktur baru lengkap dengan skor rubrik 1–5 per kriteria, catatan bukti STAR, dan rekomendasi akhir.

### 4. Analisis Rekrutmen (Hiring Debrief Analytics)
- `GET /api/jobs/{id}/analytics` — Mengambil ringkasan metrik analitik seleksi untuk debrief tim, meliputi:
  - *Funnel pipeline*: distribusi status kandidat dan kalkulasi skor evidence.
  - *Inter-rater agreement*: persentase konsensus recruiter vs hiring manager dan daftar kasus divergensi (*override*).
  - *Criteria health*: diagnosis bottleneck atau kriteria yang kurang diskriminatif.

### 5. Ekspor Data & Pelaporan Debrief
- `GET /api/jobs/{id}/export/csv` — Mengunduh rekapitulasi data seluruh kandidat dalam format file CSV (dengan UTF-8 BOM untuk kompatibilitas Excel).
- `GET /api/jobs/{id}/export/json` — Mengunduh laporan debrief lengkap dalam format JSON yang mencakup metadata lowongan, kriteria, daftar approver, kandidat, evidence, review, dan log audit.

### 6. Grounded Requisition Q&A & Health Check
- `POST /api/jobs/{id}/ask` — Mengajukan pertanyaan seputar isi requisition; sistem mengembalikan kutipan sumber resmi berbasis BM25 token overlap tanpa halusinasi LLM.
- `GET /api/health` — Menampilkan status kesehatan server, status backend OCR yang aktif, dan konfigurasi environment.

---

## OCR Lokal (PaddleOCR) & OCR API Internal

KarsaHire mendukung ekstraksi teks dari berkas pindaian (*scanned PDF/PNG/JPG*) secara lokal atau melalui API internal:

### Opsi A: PaddleOCR Lokal (Default & On-Device)
PaddleOCR menjalankan pemrosesan OCR langsung di komputer lokal pengguna menggunakan model PP-OCRv6 CPU berlisensi Apache-2.0. Berkas gambar tidak dikirim ke jaringan eksternal.

Instalasi pada virtual environment Windows:
```powershell
python -m venv .venv-ocr
.\.venv-ocr\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-ocr\Scripts\python.exe -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
.\.venv-ocr\Scripts\python.exe -m pip install -r requirements-ocr.txt
.\.venv-ocr\Scripts\python.exe .\server.py
```

Environment variable opsional:
- `RECRUITMENT_COPILOT_OCR_BACKEND`: bernilai `paddle` (default) atau `api`.
- `RECRUITMENT_COPILOT_PADDLE_LANG`: bahasa OCR (default: `en`).
- `RECRUITMENT_COPILOT_PADDLE_DEVICE`: target komputasi (default: `cpu`).

### Opsi B: API OCR Internal OpenAI-Compatible
Jika memilih backend API internal, atur environment variable sebelum server dijalankan:
- `RECRUITMENT_COPILOT_OCR_BACKEND=api`
- `RECRUITMENT_COPILOT_OCR_API_KEY`: API key internal Anda.
- `RECRUITMENT_COPILOT_OCR_API_URL`: Base URL endpoint chat completions.
- `RECRUITMENT_COPILOT_OCR_MODEL`: Model OCR (default: `ocr-lighton`).

*Catatan Keamanan*: Jangan mencatat kredensial API atau token rahasia ke dalam berkas repositori Git. Server lokal dilengkapi mekanisme pelindung rate-limiting 6 request per menit dan 5 panggilan simultan.

---

## Prinsip Tata Kelola, Privasi, & Explainability

KarsaHire dibangun dengan prinsip etika dan tata kelola AI rekrutmen:

1. **Human-in-the-Loop & Penolakan Otomatis Ditiadakan**: Sistem tidak pernah menolak atau meloloskan pelamar secara otomatis. Skor persentase adalah representasi sintaksis atas bukti yang ditemukan dalam dokumen, bukan tolok ukur kapabilitas hakiki pelamar.
2. **Ketiadaan Halusinasi (No Generative Hallucination)**: Tidak menggunakan model generatif probabilistik untuk mengarang profil kandidat. Semua poin kecocokan wajib memiliki kutipan teks (*evidence snippet*) yang dapat diaudit langsung ke nomor halaman dokumen aslinya.
3. **Penyimpanan Minimalis (Data Minimization)**: Berkas asli pelamar (PDF/DOCX) dan teks lengkap CV tidak disimpan di SQLite setelah ekstraksi selesai. Hanya atribut terstruktur, entitas keterampilan, dan cuplikan bukti yang disimpan.
4. **Pencegahan Bias Melalui Dual Sign-Off & Blind Mode**: Kriteria wajib disetujui bersama oleh Recruiter dan Hiring Manager sebelum pemrosesan dimulai. Fitur review buta meminimalkan bias nama, gender, atau asal institusi saat screening awal.
5. **Jejak Audit Kekal (Append-Only Audit Trail)**: Setiap perubahan kriteria, aksi approval, pemrosesan CV, review, scorecard, dan penghapusan kandidat terekam dalam log audit yang tidak dapat dimanipulasi.

---
*KarsaHire — Prototype Portfolio Internal · Sistem Penilaian Leksikal Transparan · Keputusan Mutlak di Tangan Manusia.*
