# KarsaHire — handoff untuk Antigravity

Tanggal handoff: **8 Oktober 2026**. Baseline kode sebelum dokumen ini: `b794097` pada branch `main`.
Repository: https://github.com/loxleyftsck/KarsaHire

## Mulai di sini

Lanjutkan pengembangan project yang ada. Baca dokumen ini, `README.md`, dan `KarsaHire-Architecture-Plan.md` sebelum mengubah kode. Dokumen ini adalah snapshot handoff, bukan bukti production readiness. Periksa `git status` dan commit terbaru karena repository dapat berubah setelah handoff.

Instruksi pengguna yang masih berlaku:

- Dev hanya lokal dan memakai data sintetis. Pilot role, bahasa CV yang didukung, dan IdP SSO semuanya **TBD**; jangan menganggapnya disetujui.
- Lanjutkan implementasi dalam bagian pekerjaan yang konkret. Setiap melewati **dua fase yang benar-benar selesai**, lakukan testing sederhana. Checklist atau persiapan dokumen tidak berarti satu fase selesai.
- Hindari mengulang pemeriksaan dan pembaruan status tanpa perubahan implementasi yang diperlukan. Laporkan pekerjaan, hasil, dan blocker secara jelas.
- Jangan commit/push env, kredensial, database, upload, backup, atau virtualenv. Isi konfigurasi rahasia harus dibuat kembali secara lokal.
- Pertahankan landing page yang rapi, warna yang selaras, dan chart yang menjelaskan data. Referensi yang diminta pengguna: https://www.chartosaur.com/ (prinsip visualisasi, bukan library chart).

## Jalankan di PC baru (PowerShell)

```powershell
git clone https://github.com/loxleyftsck/KarsaHire.git
cd KarsaHire
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

Jika checkout sudah ada, periksa perubahan lokal sebelum `git pull --ff-only`.
Python 3.10+ diperlukan. Buka http://127.0.0.1:8765 dan pilih **Coba dengan data sintetis**.
SQLite dibuat otomatis; data sesi PC sebelumnya tidak ikut Git. Tidak perlu env/OCR untuk demo sintetis. Manual upload default nonaktif. Jangan mengaktifkan OCR eksternal atau memakai CV nyata untuk melanjutkan demo.

## Implementasi saat handoff

- Backend Python stdlib HTTP + SQLite; frontend HTML/CSS/JavaScript tanpa build Node.
- Intake lowongan, kriteria, dua persetujuan, impor 32 CV sintetis, evidence per kandidat, review manusia, penghapusan kandidat, dan audit lokal.
- Matching masih baseline leksikal transparan. Q&A hanya retrieval atas kriteria/deskripsi tersimpan; belum ada jawaban LLM atau production RAG.
- Parser TXT/PDF/DOCX dan jalur OCR opsional; PDF diproses worker terpisah dengan batas sumber daya. OCR provider belum dikonfigurasi/disetujui.
- Guard loopback/origin, batas request/parser, redaksi heuristik, health/readiness, log terstruktur, migrasi SQLite, serta tool backup/restore tersedia untuk dev lokal.
- Nama dan role approval/reviewer diketik pengguna dan **belum autentikasi/otorisasi**. Tidak ada SSO, RBAC, atau enforcement akses per lowongan.
- Konflik dengan commit GitHub schema sudah diselesaikan sebelum push baseline: migrasi transaksional ada di `server.py`; `database/schema.sql` menjadi referensi base schema. Indeks base schema dipertahankan dalam migrasi v1.

## Roadmap dan gerbang

| Fase | Status yang dapat diklaim saat handoff | Sisa utama |
|---|---|---|
| M0 | Draft scope/governance | Role pilot, bahasa, IdP, data, privasi, owner, dan persetujuan |
| M1 | Demo lokal sintetis pernah lulus QC | Pertahankan alur setelah perubahan berikutnya |
| M2 | Harness evaluasi, packet anotasi/ranking, laporan sintetis | Review independen, adjudikasi, baseline dan target kualitas disetujui |
| M3 | Guard lokal dan draft kontrol akses | SSO, RBAC, akses per lowongan, review keamanan dan kebijakan |
| M4 | Tool operasi lokal, health, backup/restore | Hosting/staging, secret management, observability, retention dan recovery |
| M5 | QC developer lokal sebagian selesai | Screen reader nyata, sisa retest, UAT recruiter/manajer dan sign-off |
| M6–M8 | Belum dimulai | Pilot dan tahap peluncuran/operasi sesuai roadmap setelah gerbang sebelumnya lulus |

Estimasi percakapan terakhir: sekitar **30–35% selesai menuju production**, sisa **65–70%**. Ini perkiraan effort/gerbang, bukan perhitungan jumlah file, jaminan tanggal, atau metrik otomatis. `production_ready` tetap **false**.

## Bukti QC dan batasnya

- Catatan utama: `docs/operations/m5-local-uat-checklist.md`. Ringkasan terakhir: 13 skenario lokal, 10 Pass, 3 Partial; bukan UAT formal atau persentase kesiapan produksi.
- Preflight tersimpan terakhir sebelum handoff: `data/evaluation/local-release-preflight-2026-10-02-160731.json`. Hasil historis tidak membuktikan checkout terkini lulus.
- Perubahan UI terakhir: fokus keyboard form diperjelas dan textarea catatan review diberi label aksesibel per kandidat. Retest browser dan check terarah dilakukan; full suite belum diulang setelah perubahan UI tersebut maupun penggabungan schema.
- Windows Narrator tersedia pada PC dev sebelumnya, tetapi suara screen reader tidak direkam oleh kanal browser QA. Jangan menandai pengumuman aktual lulus dari accessibility tree saja.
- Perbandingan kontras statis, OCR stub, dan corpus sintetis tidak membuktikan aksesibilitas menyeluruh atau kualitas hiring pada populasi nyata.
- Handoff ini hanya dokumentasi; tidak menjalankan ulang suite aplikasi.

## Urutan pekerjaan berikutnya

1. Setelah setup PC baru, jalankan smoke lokal sekali; jika gagal, perbaiki kegagalan nyata sebelum menambah fitur. Gunakan DB sementara yang dibuat harness, bukan database pengguna.
2. Periksa migrasi schema v1 pada fresh DB dan upgrade DB sintetis lama karena baseline baru menyatukan commit schema remote dengan migrasi lokal. Jangan mengganti atau menghapus DB pengguna.
3. Selesaikan retest M5 yang bisa dilakukan lokal: kontras aktual di browser, notice approval, reduced motion, keyboard/fokus, dan pembacaan error/status dengan screen reader yang benar-benar didengar. Catat kondisi dan bukti; tandai belum terverifikasi bila tidak bisa dilakukan.
4. Pilih satu perubahan implementasi yang ditunjukkan oleh hasil QC, selesaikan, dan uji secara terarah. Hindari menambah dokumen status berulang tanpa kebutuhan.
5. Untuk M2, rehearsal packet/anotasi/ranking boleh memakai fixture sintetis; jangan menyebutnya review independen atau hasil ground truth. Untuk SSO/hosting/data nyata, lanjutkan hanya setelah keputusan pemilik tersedia; jangan mengarang IdP atau approval.

Perintah QC yang tersedia:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test_local.py
# Preflight lebih luas; sudah mencakup smoke, jangan jalankan keduanya berulang tanpa alasan.
.\.venv\Scripts\python.exe scripts\preflight_local_release.py
```

Preflight memeriksa pin dependency, `pip check`, smoke dan laporan agregat sintetis; tidak mengirim request OCR eksternal dan selalu membedakan lulus lokal dari production readiness. Jangan mengubah hasil historis agar tampak lulus.

## Peta file

| File/folder | Kegunaan |
|---|---|
| `server.py`, `pdf_parser_worker.py` | API, migrasi, matching, parser dan isolasi PDF |
| `web/index.html`, `web/app.js`, `web/app.css`, `web/approval.css` | UI dan chart evidence |
| `scripts/` | Smoke, evaluator, packet, preflight, backup/restore |
| `data/synthetic-cv-32/` | Fixture sintetis; pertahankan atribusi sumber/lisensi |
| `data/evaluation/` | Template dan laporan agregat historis sintetis |
| `docs/governance/m0-scope-decision-record.md` | Keputusan yang belum disetujui |
| `docs/security/m3-access-control-draft.md` | Rancangan kontrol akses provider-neutral |
| `docs/operations/` | Runbook lokal dan checklist M5 |

Env dan database tidak ikut repository. Simpan input evaluasi/adjudikasi di luar checkout sebagaimana diwajibkan tool. Jangan mengekspos server ke jaringan: aplikasi saat ini harus tetap bind `127.0.0.1`.
