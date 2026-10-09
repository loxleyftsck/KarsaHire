# KarsaHire — Atribusi Aset & Lisensi Pihak Ketiga

Dokumen ini mencatat seluruh aset pihak ketiga, pustaka *open-source*, dan materi referensi yang digunakan dalam prototipe **KarsaHire**, beserta lisensi resmi dan catatan kepatuhan privasi.

---

## 1. Dataset Sintetis CV

* **Nama Dataset:** `sukhrobnurali/resume-parsing-vision`
* **Penyedia / Sumber:** Hugging Face Datasets ([huggingface.co/datasets/sukhrobnurali/resume-parsing-vision](https://huggingface.co/datasets/sukhrobnurali/resume-parsing-vision))
* **Pembuat / Kurator:** Sukhrob Nurali
* **Lisensi:** [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
* **Penggunaan dalam KarsaHire:**
  * Subkumpulan 32 berkas CV sintetis (`data/synthetic-cv-32`) digunakan sebagai korpus uji lokal untuk demonstrasi *pipeline* parsing, ekstraksi bukti (*evidence extraction*), dan pengujian *lexical ranking baseline*.
  * Dataset ini sepenuhnya sintetis dan dibuat untuk keperluan riset/evaluasi teknis; **tidak mengandung data pribadi nyata (*no real PII*)**.

---

## 2. Ikon & Konsep Desain Antarmuka

### Lucide Icons
* **Proyek:** [Lucide Icons](https://lucide.dev/) ([github.com/lucide-icons/lucide](https://github.com/lucide-icons/lucide))
* **Lisensi:** [ISC License](https://github.com/lucide-icons/lucide/blob/main/LICENSE) (bagian turunan dari Feather Icons di bawah Lisensi MIT)
* **Penggunaan:** Inspirasi simbol grafis dan ikonografi antarmuka (misalnya: *users*, *file-search*, *list-checks*, *shield-check*, *eye*, dan *arrow-right*).

### unDraw Illustrations
* **Proyek:** [unDraw Illustrations](https://undraw.co/) oleh Katerina Limpitsouni ([handcrafts.undraw.co](https://handcrafts.undraw.co/))
* **Lisensi:** [unDraw Open License](https://undraw.co/license) (bebas digunakan untuk keperluan pribadi maupun komersial tanpa kewajiban atribusi).
* **Penggunaan:** Referensi gaya visual dan konsep komposisi ilustrasi alur kerja tim kolaboratif (*Project Flow* & *Team Permissions*).

### Aset Grafis Orisinal KarsaHire
Aset-aset berikut dibuat secara khusus untuk kebutuhan prototipe KarsaHire dengan palet warna resmi (`#f4f5f1`, `#1e2b27`, `#335a48`, `#e9f1eb`, `#bfe0ca`):
* `web/assets/karsahire-logo-concept.png`: Eksplorasi konsep logo dan monogram "K" berlatar transparan.
* `web/assets/karsahire-shortlist-dashboard.png`: Tampilan pratinjau UI *dashboard shortlist* berbasis data kandidat sintetis.
* `web/assets/karsahire-team-review.png`: Ilustrasi kolaborasi antara *recruiter* dan *hiring manager* saat meninjau kartu bukti kandidat.
* `web/assets/karsahire-workflow-loop.gif`: Animasi demonstrasi alur kerja: Sepakati Kriteria → Bukti CV → Review Tim (dilengkapi visual statis alternatif ketika preferensi *reduced motion* aktif).

---

## 3. Pustaka Open-Source Utama (Backend & Parsing)

| Komponen / Pustaka | Lisensi | Sumber Proyek | Peran dalam KarsaHire |
|---|---|---|---|
| **PaddleOCR** | Apache-2.0 | [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Mesin OCR lokal opsional (PP-OCRv6) untuk memproses teks dari pindaian/gambar tanpa mengirim data ke luar mesin lokal. |
| **pypdf** | BSD-3-Clause | [py-pdf/pypdf](https://github.com/py-pdf/pypdf) | Ekstraksi teks dari berkas CV berformat PDF secara lokal. |
| **python-docx** | MIT | [python-openxml/python-docx](https://github.com/python-openxml/python-docx) | Ekstraksi teks dari dokumen CV berformat Microsoft Word (.docx). |
| **Pillow (PIL Fork)** | HPND | [python-pillow/Pillow](https://github.com/python-pillow/Pillow) | Pemrosesan, konversi, dan rasterisasi citra untuk *pipeline* OCR lokal. |
| **Python Standard Library** | PSF License | [python.org](https://www.python.org/) | HTTP server lokal (`http.server`), penyimpanan SQLite (`sqlite3`), ekspresi reguler (`re`), struktur antrean, dan hashing/audit event. |

---

## 4. Disclaimer Prototipe & Kepatuhan Privasi

KarsaHire dirancang sebagai prototipe portofolio untuk mengeksplorasi rekrutmen kolaboratif yang transparan (*explainable AI copilot*). Untuk menjaga integritas dan privasi data:

1. **Tidak Menyimpan Berkas Asli:**
   Sistem tidak menyimpan berkas unggahan asli (PDF, DOCX, TXT, atau gambar) ke dalam media penyimpanan permanen/disk server.
2. **Tidak Menyimpan Teks CV Mentah:**
   Teks lengkap CV hasil ekstraksi tidak disimpan dalam basis data SQLite (`data/copilot.sqlite3`). Hanya ringkasan profil terstruktur, cuplikan bukti per kriteria (*evidence snippets*), skor indikator leksikal, dan riwayat keputusan manusia yang dicatat.
3. **Penyaringan PII Dasar (*Basic PII Redaction*):**
   Sebelum cuplikan bukti disimpan ke database lokal, filter ekspresi reguler menyaring informasi kontak langsung (nomor telepon, alamat email, dan baris identitas sensitif seperti tanggal lahir atau alamat rumah). Identitas kandidat menggunakan ID sintetis/buram (*opaque candidate ID*).
4. **Keputusan oleh Manusia (*Human-in-the-Loop*):**
   Skor kecocokan leksikal berfungsi sebagai indikator kelengkapan bukti, bukan penentu kelulusan kandidat. Keputusan seleksi (*advance*, *needs information*, *not selected*) mutlak dilakukan oleh reviewer manusia dengan catatan alasan yang tercatat dalam *audit trail*.
5. **Catatan Penerapan Skala Produksi:**
   Prototipe ini berjalan secara lokal (*local-first*) tanpa autentikasi pengguna atau SSO. Penerapan di lingkungan produksi memerlukan integrasi kontrol akses berbasis peran (RBAC), enkripsi data *at-rest* dan *in-transit*, audit kesetaraan (*fairness evaluation*), serta kepatuhan regulasi perlindungan data pribadi (seperti UU PDP / GDPR).
