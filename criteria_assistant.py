"""Criteria Assistant & STAR Interview Copilot for KarsaHire.

Provides calibration audits for requisition criteria and generates structured
STAR (Situation, Task, Action, Result) behavioral interview guides for recruiters
and hiring managers during job intake and structured scorecard evaluations.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

# Default weights as specified in KarsaHire criteria architecture
DEFAULT_REQUIRED_WEIGHT = 1.0
DEFAULT_PREFERRED_WEIGHT = 0.8
MONOPOLY_THRESHOLD = 0.40  # Max single criterion weight percentage (40%)


# ---------------------------------------------------------------------------
# Predefined Role Criteria Recommendations (4-6 criteria each, 1.0 vs 0.8)
# ---------------------------------------------------------------------------

ROLE_CRITERIA_CATALOG: dict[str, list[dict[str, Any]]] = {
    "software_developer": [
        {"label": "Programming", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Technical"},
        {"label": "Software development", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Technical"},
        {"label": "Git", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Engineering Practices"},
        {"label": "REST API", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Architecture"},
        {"label": "Automated testing", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Quality"},
    ],
    "backend_developer": [
        {"label": "Python", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Language"},
        {"label": "API development", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Architecture"},
        {"label": "PostgreSQL", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Database"},
        {"label": "Docker", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "DevOps"},
        {"label": "Unit testing", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Quality"},
    ],
    "frontend_developer": [
        {"label": "JavaScript", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Language"},
        {"label": "React", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Framework"},
        {"label": "HTML & CSS", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "UI"},
        {"label": "TypeScript", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Language"},
        {"label": "State management", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Architecture"},
    ],
    "network_administrator": [
        {"label": "Computer networking", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Infrastructure"},
        {"label": "Server administration", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Systems"},
        {"label": "System monitoring", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Operations"},
        {"label": "Backup and recovery", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Resilience"},
        {"label": "Linux", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "OS"},
    ],
    "systems_administrator": [
        {"label": "Linux", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "OS"},
        {"label": "Server administration", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Systems"},
        {"label": "Active Directory", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Identity"},
        {"label": "System monitoring", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Operations"},
        {"label": "Shell scripting", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Automation"},
    ],
    "accountant": [
        {"label": "General ledger", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Accounting Core"},
        {"label": "Financial statements", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Reporting"},
        {"label": "Account reconciliation", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Audit & Control"},
        {"label": "Month-end close", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Operations"},
        {"label": "Tax reporting", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Compliance"},
    ],
    "accounting_clerk": [
        {"label": "Bookkeeping", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Accounting Core"},
        {"label": "Accounts payable", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Operations"},
        {"label": "Accounts receivable", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Operations"},
        {"label": "Invoice processing", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Verification"},
        {"label": "Excel", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Tooling"},
    ],
    "hr_specialist": [
        {"label": "Candidate sourcing", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Talent Acquisition"},
        {"label": "Resume screening", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Assessment"},
        {"label": "Structured interviewing", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Interviewing"},
        {"label": "Recruitment coordination", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Operations"},
        {"label": "Applicant tracking system", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Systems"},
    ],
    "hr_manager": [
        {"label": "HR operations", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Leadership"},
        {"label": "Employee relations", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Culture & Law"},
        {"label": "Workforce planning", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Strategy"},
        {"label": "Compensation and benefits", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Rewards"},
        {"label": "HR analytics", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Data"},
    ],
    "learning_development": [
        {"label": "Training needs analysis", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Analysis"},
        {"label": "Instructional design", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Curriculum"},
        {"label": "Training facilitation", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Delivery"},
        {"label": "Training evaluation", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Impact"},
        {"label": "Learning management system", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Tooling"},
    ],
    "data_analyst": [
        {"label": "Data analysis", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Analytics Core"},
        {"label": "SQL", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Querying"},
        {"label": "Data visualization", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Reporting"},
        {"label": "Python", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Programming"},
        {"label": "Business intelligence", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Strategy"},
    ],
    "data_scientist": [
        {"label": "Machine learning", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Modeling"},
        {"label": "Python", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Programming"},
        {"label": "Data analysis", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Analytics"},
        {"label": "SQL", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Database"},
        {"label": "Deep learning", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Advanced AI"},
    ],
    "cybersecurity_analyst": [
        {"label": "Security monitoring", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "SecOps"},
        {"label": "Vulnerability assessment", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Assessment"},
        {"label": "Incident response", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Defense"},
        {"label": "Access control", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "IAM"},
        {"label": "SIEM", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Tooling"},
    ],
    "devops_engineer": [
        {"label": "CI/CD", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Pipeline"},
        {"label": "Docker", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Containerization"},
        {"label": "Cloud infrastructure", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Cloud"},
        {"label": "Kubernetes", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Orchestration"},
        {"label": "Infrastructure as code", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Automation"},
    ],
    "product_manager": [
        {"label": "Product roadmap", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Strategy"},
        {"label": "User research", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Customer Discovery"},
        {"label": "Agile methodology", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Execution"},
        {"label": "Data analysis", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Metrics"},
        {"label": "Cross-functional collaboration", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Leadership"},
    ],
    "general": [
        {"label": "Job domain knowledge", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Core Competency"},
        {"label": "Problem solving", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Cognitive"},
        {"label": "Execution & delivery", "type": "required", "weight": DEFAULT_REQUIRED_WEIGHT, "category": "Operational"},
        {"label": "Cross-functional collaboration", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Teamwork"},
        {"label": "Communication skills", "type": "preferred", "weight": DEFAULT_PREFERRED_WEIGHT, "category": "Interpersonal"},
    ],
}


# ---------------------------------------------------------------------------
# STAR Knowledge Base: Behavioral Questions, Probes, Rubrics
# ---------------------------------------------------------------------------

STAR_QUESTION_BANK: dict[str, dict[str, Any]] = {
    "programming": {
        "question": "Ceritakan proyek paling kompleks di mana Anda menulis atau merekayasa kode produksi dari awal hingga selesai.",
        "star_probe": {
            "situation": "Apa konteks sistem yang dibangun dan batasan teknis (performance, deadline, arsitektur) yang ada saat itu?",
            "task": "Komponen atau fitur kritis apa yang secara spesifik menjadi tanggung jawab penulisan kode Anda?",
            "action": "Bagaimana pendekatan desain pola kode yang Anda pilih, teknik debugging apa yang digunakan, dan bagaimana Anda memastikan kode mudah dipelihara?",
            "result": "Bagaimana performa modul tersebut saat rilis, seberapa rendah tingkat bug, dan apa dampak terukurnya bagi pengguna?",
        },
        "look_for": [
            "Menjelaskan struktur kode, algoritma, atau modularitas dengan prinsip clean code dan separation of concerns.",
            "Memiliki kesadaran tinggi akan penanganan edge cases, konkurensi, dan pengujian mandiri.",
            "Mampu mempertanggungjawabkan trade-off pemilihan library atau struktur data yang dipakai.",
        ],
        "red_flags": [
            "Hanya bisa menjelaskan kode superficial atau mengandalkan copy-paste tanpa mengerti alur eksekusi.",
            "Tidak memedulikan maintainability, performa kode, atau mengabaikan penanganan error exception.",
            "Tidak mampu menjelaskan bagaimana bug rumit diselidiki dan diselesaikan secara metodis.",
        ],
    },
    "software development": {
        "question": "Ceritakan pengalaman Anda dalam siklus hidup pengembangan perangkat lunak (SDLC) ketika menghadapi perubahan spesifikasi yang mendadak sebelum peluncuran.",
        "star_probe": {
            "situation": "Apa urgensi perubahan spesifikasi tersebut dan bagaimana pengaruhnya terhadap jadwal rilis tim?",
            "task": "Apa peran Anda dalam mengevaluasi kelayakan teknis dan menyusun strategi adaptasi jadwal serta dependensi kode?",
            "action": "Langkah refactoring atau penyesuaian backlog apa yang Anda lakukan bersama tim produk dan engineering?",
            "result": "Apakah fitur berhasil rilis tepat waktu tanpa regresi? Apa metrik stabilitas sistem pasca-rilis?",
        },
        "look_for": [
            "Memahami siklus rilis end-to-end (requirement, build, test, deploy, monitor).",
            "Mampu berkolaborasi aktif dengan product manager dan QA untuk mitigasi risiko teknis.",
            "Menunjukkan ketenangan dan pemikiran terstruktur di bawah tekanan deadline.",
        ],
        "red_flags": [
            "Menolak perubahan secara kaku tanpa menawarkan alternatif kompromi teknis.",
            "Merilis kode tanpa pengujian ulang yang memicu downtime atau insiden kritis.",
            "Menimpakan keterlambatan kepada pihak lain tanpa evaluasi retrospektif diri.",
        ],
    },
    "git": {
        "question": "Ceritakan situasi saat terjadi merge conflict besar atau insiden salah commit di branch utama (main/production) yang melibatkan banyak anggota tim.",
        "star_probe": {
            "situation": "Bagaimana insiden tersebut terdeteksi dan berapa banyak developer atau layanan yang terdampak?",
            "task": "Apa tanggung jawab Anda dalam mengisolasi insiden dan memulihkan kestabilan repositori?",
            "action": "Perintah Git spesifik apa yang Anda gunakan (revert, rebase, cherry-pick) dan bagaimana koordinasi branch dilakukan?",
            "result": "Berapa lama waktu recovery repositori, dan branching strategy pencegahan apa yang Anda terapkan setelahnya?",
        },
        "look_for": [
            "Fasih menggunakan branching workflow (Gitflow/trunk-based), rebase, revert, cherry-pick, dan resolusi konflik bersih.",
            "Mendorong budaya pull request review yang konstruktif dan perlindungan branch utama.",
            "Menjelaskan langkah mitigasi dengan runut tanpa panik saat pipeline rilis terhambat.",
        ],
        "red_flags": [
            "Memakai 'git push --force' ke production branch tanpa koordinasi atau izin.",
            "Menghindari konflik dengan menghapus pekerjaan rekan satu tim secara ceroboh.",
            "Tidak memahami konsep dasar commit history, staging, atau branch protection.",
        ],
    },
    "rest api": {
        "question": "Ceritakan pengalaman Anda dalam mendesain atau mengoptimasi endpoint RESTful API yang melayani beban traffic tinggi.",
        "star_probe": {
            "situation": "Berapa estimasi throughput (RPS) endpoint tersebut dan format data apa yang ditransmisikan?",
            "task": "Apa tantangan utama terkait latensi, konsistensi data, atau standarisasi response payload?",
            "action": "Bagaimana Anda menyusun status code, caching header, validasi skema input, dan paginasi data?",
            "result": "Berapa reduksi latensi (p95/p99) yang tercapai dan bagaimana kemudahan integrasi di sisi client/frontend?",
        },
        "look_for": [
            "Penerapan standar REST yang konsisten (HTTP verbs, idempotent operations, pagination, payload contracts).",
            "Perhatian kuat pada validasi payload, security (rate limiting, auth), dan backward compatibility.",
            "Pengukuran performa berbasis metrik kuantitatif (latensi ms, RPS, error rate).",
        ],
        "red_flags": [
            "Menggunakan status code 200 untuk seluruh respon termasuk error internal sistem.",
            "Tidak memikirkan paginasi atau query limit pada dataset berukuran besar.",
            "Mendesain API rapuh yang mudah jebol bila dikirimkan format payload di luar ekspektasi.",
        ],
    },
    "automated testing": {
        "question": "Ceritakan skenario ketika pengujian otomatis yang Anda rancang berhasil mencegah bug fatal lolos ke lingkungan produksi.",
        "star_probe": {
            "situation": "Bagian sistem mana yang rawan mengalami regresi dan seberapa kritikal dampaknya jika sampai terjadi kegagalan?",
            "task": "Cakupan testing level apa (unit, integration, e2e) yang Anda prioritaskan untuk melindungi modul tersebut?",
            "action": "Bagaimana Anda menyusun skenario edge-case, mock data dependensi eksternal, dan integrasi ke pipeline CI?",
            "result": "Bug kritis apa yang berhasil tertangkap sebelum deploy, dan berapa peningkatan coverage yang diraih?",
        },
        "look_for": [
            "Filosofi pengujian yang seimbang (testing pyramid) dan kebiasaan menulis tes deterministik (non-flaky).",
            "Mampu membuat mock/stub yang efisien tanpa menyembunyikan perilaku sistem yang sesungguhnya.",
            "Menjadikan automated testing sebagai bagian alami dari disiplin pengembangan harian.",
        ],
        "red_flags": [
            "Menganggap pengujian otomatis hanya membuang waktu dan sepenuhnya membebankannya pada tim QA manual.",
            "Tes yang dibuat bersifat semu hanya demi mengejar target angka coverage tanpa menguji logika bisnis.",
            "Membiarkan tes gagal di pipeline CI di-bypass ('skip test') demi mengejar rilis cepat.",
        ],
    },
    "sql": {
        "question": "Ceritakan pengalaman Anda dalam melakukan tuning atau mengoptimalkan query database yang lambat dan membebani server.",
        "star_probe": {
            "situation": "Berapa volume data pada tabel terkait dan seberapa lambat eksekusi query sebelum dilakukan optimasi?",
            "task": "Apa target durasi eksekusi query dan pemulihan performa CPU/memory database yang diharapkan?",
            "action": "Bagaimana langkah analisis query plan (EXPLAIN ANALYZE), modifikasi indeks, atau restrukturisasi query yang Anda lakukan?",
            "result": "Berapa persentase percepatan waktu kueri dan penurunan beban server database yang terbukti di grafik monitoring?",
        },
        "look_for": [
            "Menguasai penggunaan EXPLAIN plan, analisis index scan vs seq scan, dan penghindaran N+1 queries.",
            "Paham normalisasi/denormalisasi data serta transaksi atomik (ACID) dan isolasi level.",
            "Mampu membedakan kapan kueri harus dioptimasi di tingkat DB versus di-cache di layer aplikasi.",
        ],
        "red_flags": [
            "Mencoba mempercepat query hanya dengan coba-coba menambah indeks secara acak di semua kolom.",
            "Mengabaikan pencegahan SQL injection atau menggunakan string formatting mentah dalam query.",
            "Tidak memahami implikasi lock tabel pada query panjang di sistem produksi aktif.",
        ],
    },
    "computer networking": {
        "question": "Ceritakan insiden jaringan paling kritis (misal paket drop, latency spike, atau subnet failure) yang pernah Anda selidiki dan perbaiki.",
        "star_probe": {
            "situation": "Layanan apa yang terdampak oleh gangguan jaringan tersebut dan seberapa luas dampaknya terhadap operasional kantor/client?",
            "task": "Apa peran Anda dalam tim tanggap darurat infrastruktur dan apa batasan waktu (SLA) pemulihan?",
            "action": "Metode troubleshooting layer jaringan (OSI model) apa yang Anda terapkan? Alat analisis apa (Wireshark, traceroute, ping) yang Anda gunakan?",
            "result": "Apa akar masalah yang ditemukan (misal routing loop, switch port flap, MTU mismatch) dan langkah hardening permanen apa yang dipasang?",
        },
        "look_for": [
            "Troubleshooting metodis berbasis model OSI / TCP-IP, bukan spekulasi liar.",
            "Keahlian konfigurasi routing, switching, subnetting, VLAN, dan firewall rules.",
            "Dokumentasi topologi jaringan yang rapi dan penutupan insiden dengan post-mortem.",
        ],
        "red_flags": [
            "Melakukan restart perangkat keras secara membabi-buta tanpa mengumpulkan log diagnostik terlebih dahulu.",
            "Tidak memahami konsep dasar subnetting, gateway, DNS resolution, atau perbedaan TCP vs UDP.",
            "Mengubah routing atau rule firewall di produksi tanpa rencana rollback jika terjadi lock-out.",
        ],
    },
    "server administration": {
        "question": "Ceritakan pengalaman Anda dalam mengelola kluster server produksi agar mencapai tingkat ketersediaan (uptime) yang tinggi.",
        "star_probe": {
            "situation": "Berapa banyak instance server yang berada di bawah pengelolaan Anda dan sistem operasi apa yang digunakan?",
            "task": "Tantangan apa yang paling sering muncul terkait patching keamanan, kapasitas disk, atau load balancing?",
            "action": "Bagaimana Anda mengotomatiskan provisioning konfigurasi, manajemen akun akses, dan rotasi log?",
            "result": "Berapa persen uptime yang berhasil dipertahankan dan seberapa cepat waktu respons penanganan server hang?",
        },
        "look_for": [
            "Disiplin dalam standardisasi konfigurasi server dan pengelolaan izin hak akses berbasis least privilege.",
            "Penggunaan scripting otomatisasi untuk tugas berulang dan patch management terjadwal.",
            "Proaktif dalam monitoring kesehatan resource server (CPU, memory, disk I/O, network).",
        ],
        "red_flags": [
            "Menggunakan akun root/administrator untuk semua aktivitas harian tanpa jejak audit log.",
            "Mengabaikan pembaruan patch keamanan hingga sistem rentan terhadap eksploitasi.",
            "Tidak memiliki dokumentasi setup server sehingga instalasi baru bergantung pada ingatan pribadi.",
        ],
    },
    "system monitoring": {
        "question": "Ceritakan pengalaman Anda saat merancang sistem alerting dan monitoring yang berhasil mendeteksi anomali sebelum pengguna mengeluh.",
        "star_probe": {
            "situation": "Infrastruktur atau aplikasi apa yang dimonitor dan apa titik rentan kegagalan yang paling diwaspadai?",
            "task": "Metrik kunci apa (SLI/SLO) yang harus dipantau agar tim tidak mengalami alert fatigue (kejenuhan alarm)?",
            "action": "Bagaimana Anda mengonfigurasi threshold alert, dashboard visual, dan eskalasi otomatis ke channel on-call?",
            "result": "Berapa penurunan Mean Time to Detect (MTTD) dan Mean Time to Resolve (MTTR) setelah sistem monitoring baru aktif?",
        },
        "look_for": [
            "Mampu membedakan actionable alerts dari noise/false positives untuk mencegah alert fatigue.",
            "Memantau empat sinyal emas (latensi, traffic, error, saturasi) secara konsisten.",
            "Keterlibatan aktif dalam meninjau tren metrik untuk perencanaan kapasitas (capacity planning).",
        ],
        "red_flags": [
            "Mengatur ribuan notifikasi peringatan yang akhirnya diabaikan atau di-mute oleh tim.",
            "Hanya menyadari sistem tumbang setelah ada komplain kemarahan dari pengguna akhir.",
            "Tidak tahu cara menafsirkan grafik tren metrik atau perbedaan rata-rata vs persentil (p99).",
        ],
    },
    "backup and recovery": {
        "question": "Ceritakan simulasi disaster recovery atau situasi nyata di mana Anda harus melakukan pemulihan data dari sistem cadangan (backup).",
        "star_probe": {
            "situation": "Apa pemicu kebutuhan recovery (kegagalan storage, kesalahan manusia, ransomware, atau uji audit DR)?",
            "task": "Berapa target Recovery Point Objective (RPO) dan Recovery Time Objective (RTO) yang telah disepakati bisnis?",
            "action": "Langkah validasi integritas backup apa yang Anda jalankan dan bagaimana proses restore dijalankan secara aman?",
            "result": "Apakah data berhasil dipulihkan 100% tanpa ada data loss melebihi RPO? Berapa durasi waktu pemulihan aktual?",
        },
        "look_for": [
            "Menerapkan prinsip backup 3-2-1 dan secara rutin menguji keterbacaan data backup (bukan hanya asumsi jalan).",
            "Memahami perbedaan snapshot, incremental, differential, dan full backup.",
            "Dokumentasi prosedur Disaster Recovery Plan (DRP) yang jelas dan terverifikasi berkala.",
        ],
        "red_flags": [
            "Memiliki jadwal backup tetapi tidak pernah sekalipun menguji proses restore datanya.",
            "Menyimpan file backup di server atau disk fisik yang sama dengan data produksi.",
            "Tidak mengetahui konsep RPO dan RTO atau menganggap backup otomatis selalu bebas dari korupsi data.",
        ],
    },
    "security monitoring": {
        "question": "Ceritakan penanganan alert keamanan dari sistem SIEM/EDR yang mengindikasikan adanya upaya intrusi berbahaya pada jaringan perusahaan.",
        "star_probe": {
            "situation": "Event log atau payload anomali apa yang memicu deteksi ancaman dan aset perusahaan mana yang menjadi target?",
            "task": "Bagaimana Anda memverifikasi apakah temuan tersebut merupakan True Positive atau False Positive?",
            "action": "Langkah isolasi endpoint atau pemblokiran IP apa yang segera Anda eksekusi untuk menahan pergerakan lateral penyerang?",
            "result": "Bagaimana hasil penyelidikan forensik akhir dan rekomendasi pencegahan permanen apa yang Anda terapkan?",
        },
        "look_for": [
            "Kemampuan korelasi log dari firewall, endpoint, dan server untuk merekonstruksi timeline serangan.",
            "Tindakan cepat dan disiplin dalam containment sesuai playbook keamanan siber.",
            "Komunikasi yang jelas dan tenang kepada manajemen mengenai status risiko dan mitigasi.",
        ],
        "red_flags": [
            "Mengabaikan alert berulang karena menganggapnya selalu false positive tanpa investigasi tuntas.",
            "Panik dan mematikan server utama tanpa mengamankan bukti volatilitas memori untuk analisis forensik.",
            "Tidak memahami taktik dan teknik serangan umum (seperti kerangka kerja MITRE ATT&CK).",
        ],
    },
    "vulnerability assessment": {
        "question": "Ceritakan pengalaman Anda dalam memimpin atau menjalankan pemindaian kerentanan (vulnerability scan) pada infrastruktur perusahaan.",
        "star_probe": {
            "situation": "Berapa banyak host atau aplikasi yang dipindai dan apa pemicunya (audit berkala, rilis baru, atau zero-day baru)?",
            "task": "Bagaimana Anda memprioritaskan ratusan temuan CVE berdasarkan tingkat keparahan (CVSS) dan eksposur aset bisnis?",
            "action": "Bagaimana Anda berkoordinasi dengan tim developer/infrastruktur agar patch atau mitigasi diaplikasikan tepat waktu?",
            "result": "Berapa persen penurunan kerentanan berisiko tinggi (High/Critical) yang tercapai dalam SLA remediasi?",
        },
        "look_for": [
            "Mampu memprioritaskan risiko berdasarkan dampak bisnis riil dan exploitability, bukan hanya skor mentah CVSS.",
            "Membangun hubungan kerja kolaboratif dengan tim teknis tanpa menimbulkan friksi 'saling menyalahkan'.",
            "Melakukan re-testing secara ketat untuk memverifikasi bahwa kerentanan benar-benar tertutup rapat.",
        ],
        "red_flags": [
            "Hanya melempar dokumen laporan tebal hasil scanning otomatis ke tim lain tanpa kurasi atau bimbingan mitigasi.",
            "Tidak memahami perbedaan kerentanan teoretis dengan celah yang benar-benar bisa dieksploitasi di lingkungan aktif.",
            "Mengabaikan audit ulang setelah tim teknis mengeklaim perbaikan telah selesai.",
        ],
    },
    "candidate sourcing": {
        "question": "Ceritakan strategi pencarian kandidat (talent sourcing) paling menantang yang pernah Anda lakukan untuk posisi yang sangat langka di pasar.",
        "star_probe": {
            "situation": "Posisi spesialis apa yang dicari dan mengapa kandidat untuk peran tersebut sangat sulit ditemukan melalui lowongan biasa?",
            "task": "Berapa target kandidat terkualifikasi yang harus Anda hasilkan dalam pipeline wawancara dan apa batas waktunya?",
            "action": "Kanal alternatif apa yang Anda gunakan (misal Boolean search, komunitas tech, alumni networking) dan bagaimana personalisasi pesan outreach Anda?",
            "result": "Berapa acceptance rate dari pesan pendekatan Anda dan apakah posisi tersebut berhasil terisi oleh kandidat berkualitas tinggi?",
        },
        "look_for": [
            "Keahlian Boolean search tingkat lanjut dan eksplorasi kanal sourcing di luar LinkedIn standar.",
            "Pendekatan outreach yang dipersonalisasi dengan riset latar belakang kandidat, bukan template spam massal.",
            "Melacak metrik funnel konversi sourcing secara data-driven.",
        ],
        "red_flags": [
            "Hanya mengandalkan iklan lowongan pasif ('post and pray') lalu menyalahkan kondisi pasar jika pelamar sedikit.",
            "Mengirimkan pesan template generik yang salah menyebutkan nama kandidat atau keahlian yang relevan.",
            "Tidak memahami kualifikasi teknis dari peran yang dicari sehingga menyodorkan kandidat yang tidak relevan.",
        ],
    },
    "resume screening": {
        "question": "Ceritakan pengalaman Anda saat menyortir ratusan berkas CV pelamar dalam waktu singkat tanpa mengorbankan kualitas atau keadilan seleksi.",
        "star_probe": {
            "situation": "Berapa volume CV yang masuk dan seberapa ketat kriteria kualifikasi yang disepakati dengan hiring manager?",
            "task": "Bagaimana Anda menjaga konsistensi penyaringan agar tidak terjadi bias subjektif (seperti bias almamater atau latar belakang personal)?",
            "action": "Rubrik penilaian apa yang Anda gunakan dan bagaimana Anda memvalidasi kesesuaian bukti pengalaman kerja dengan kriteria lowongan?",
            "result": "Berapa persen kandidat hasil seleksi berkas Anda yang lolos ke tahap wawancara user dan dinilai memuaskan?",
        },
        "look_for": [
            "Menggunakan rubrik kriteria terstandardisasi dan fokus pada bukti kompetensi nyata, bukan asumsi subjektif.",
            "Kesadaran kuat terhadap mitigasi bias seleksi dan perlindungan data pribadi pelamar.",
            "Komunikasi yang transparan dan tepat waktu kepada kandidat yang tidak lolos seleksi berkas.",
        ],
        "red_flags": [
            "Menyaring kandidat berdasarkan preferensi pribadi yang diskriminatif atau tidak relevan dengan pekerjaan.",
            "Hanya melihat nama universitas atau perusahaan sebelumnya tanpa mengecek rekam jejak keterampilan.",
            "Mengabaikan kriteria wajib yang telah disepakati bersama hiring manager pada tahap intake.",
        ],
    },
    "structured interviewing": {
        "question": "Ceritakan situasi saat Anda memandu wawancara terstruktur dan menggali kandidat yang memberikan jawaban hafalan atau terlalu teoritis.",
        "star_probe": {
            "situation": "Kompetensi apa yang sedang Anda evaluasi dan mengapa jawaban awal kandidat terasa meragukan atau tidak spesifik?",
            "task": "Bagaimana Anda memandu kandidat agar menceritakan pengalaman perilakunya sendiri tanpa terkesan mengintimidasi?",
            "action": "Pertanyaan probing STAR apa yang Anda ajukan untuk membedakan kontribusi individu dari pencapaian tim secara umum?",
            "result": "Bagaimana penilaian akhir Anda terhadap kandidat tersebut dan apakah skor rubrik Anda terbukti akurat saat kandidat bekerja?",
        },
        "look_for": [
            "Disiplin menggunakan metode STAR dengan pertanyaan lanjutan mendalam pada aspek 'Action' dan 'Result'.",
            "Mencatat bukti perilaku secara objektif selama sesi daripada mengandalkan intuisi atau impresi sesaat.",
            "Mampu menciptakan suasana wawancara yang profesional, nyaman, namun tetap menguji kompetensi secara mendalam.",
        ],
        "red_flags": [
            "Membiarkan wawancara menjadi obrolan santai tanpa arah tanpa menyentuh kriteria kompetensi yang disepakati.",
            "Langsung puas dengan jawaban teoritis tanpa menanyakan contoh situasi nyata yang pernah dihadapi kandidat.",
            "Menilai kandidat semata-mata berdasarkan efek 'halo' (karena ramah atau satu almamater).",
        ],
    },
    "general ledger": {
        "question": "Ceritakan pengalaman Anda dalam mendeteksi dan mengoreksi ketidakseimbangan jurnal besar (general ledger) pada akhir periode pembukuan.",
        "star_probe": {
            "situation": "Berapa nilai selisih yang ditemukan dan transaksi apa yang diduga menjadi sumber ketidaksesuaian akun?",
            "task": "Seberapa ketat tenggat waktu penutupan buku dan siapa pihak yang memerlukan kepastian laporan keuangan tersebut?",
            "action": "Bagaimana Anda menelusuri jejak audit (audit trail), memeriksa posting ayat jurnal, dan menyusun penyesuaian (adjusting entries)?",
            "result": "Apakah neraca saldo berhasil diseimbangkan sesuai standar akuntansi dan kontrol apa yang dipasang agar kesalahan tidak terulang?",
        },
        "look_for": [
            "Pemahaman mendalam mengenai prinsip debit-kredit ganda, struktur bagan akun (COA), dan integritas jejak audit.",
            "Ketelitian tinggi dalam menelusuri transaksi janggal dan kepatuhan pada standar akuntansi keuangan (PSAK/IFRS).",
            "Menyusun dokumentasi memo penyesuaian yang lengkap dengan otorisasi yang sah.",
        ],
        "red_flags": [
            "Membuat jurnal penyeimbang semu atau 'memaksa' angka cocok tanpa menemukan akar penyebab selisih.",
            "Mengabaikan otorisasi pembukuan dan mengedit transaksi historis tanpa catatan log audit.",
            "Tidak memahami dampak penyesuaian akun terhadap pos laporan laba rugi maupun neraca.",
        ],
    },
    "financial statements": {
        "question": "Ceritakan keterlibatan Anda dalam menyusun laporan keuangan lengkap (Neraca, Laba Rugi, Arus Kas) untuk kebutuhan audit eksternal.",
        "star_probe": {
            "situation": "Entitas bisnis apa yang dilaporkan dan regulasi standar akuntansi apa yang menjadi pedoman utama?",
            "task": "Komponen laporan mana yang paling membutuhkan estimasi atau pengungkapan catatan atas laporan keuangan (CALK)?",
            "action": "Bagaimana proses konsolidasi data, rekonsiliasi antar-akun, dan penyusunan kertas kerja audit yang Anda siapkan?",
            "result": "Apakah laporan keuangan selesai tepat waktu dan mendapatkan opini wajar tanpa pengecualian (WTP) dari auditor?",
        },
        "look_for": [
            "Memahami hubungan saling terkait antara Neraca, Laporan Laba Rugi, dan Laporan Arus Kas.",
            "Menyiapkan kertas kerja audit yang rapi, transparan, dan siap dipertanggungjawabkan kepada auditor independen.",
            "Disiplin dalam memenuhi batas waktu kepatuhan pelaporan keuangan regulator.",
        ],
        "red_flags": [
            "Tidak memahami bagaimana pergerakan arus kas berelasi dengan laba bersih akrual.",
            "Panik dan tidak dapat menyajikan bukti pendukung saat diminta sampel dokumen oleh auditor.",
            "Mengabaikan pengungkapan transaksi penting atau peristiwa setelah tanggal neraca.",
        ],
    },
    "account reconciliation": {
        "question": "Ceritakan proses rekonsiliasi akun paling rumit (misal rekonsiliasi bank atau akun antar-perusahaan) yang melibatkan ribuan transaksi menggantung.",
        "star_probe": {
            "situation": "Apa penyebab utama timbulnya item menggantung (timing difference, kesalahan kurs, biaya bank, atau fraud)?",
            "task": "Berapa toleransi nilai selisih yang diizinkan dan berapa lama waktu yang diberikan untuk menyelesaikan rekonsiliasi?",
            "action": "Metode pencocokan apa yang Anda gunakan (automasi Excel, software ERP) dan bagaimana Anda memverifikasi bukti rekening koran?",
            "result": "Apakah seluruh item rekonsiliasi berhasil diselesaikan dan SOP verifikasi harian apa yang Anda perbarui?",
        },
        "look_for": [
            "Metode verifikasi transaksi dua arah yang sistematis dan tidak membiarkan item menggantung menumpuk lintas bulan.",
            "Mampu mengidentifikasi potensi kebocoran dana atau anomali transaksi mencurigakan sedini mungkin.",
            "Menggunakan formula atau tooling otomasi untuk mempercepat rekonsiliasi volume besar.",
        ],
        "red_flags": [
            "Membiarkan transaksi menggantung selama berbulan-bulan tanpa tindak lanjut atau investigasi ke bank/rekanan.",
            "Menghapus selisih kecil dengan asumsi tidak material tanpa izin manajemen.",
            "Tidak memahami perbedaan perbedaan waktu (timing differences) dengan kesalahan pencatatan riil.",
        ],
    },
    "data analysis": {
        "question": "Ceritakan pengalaman Anda dalam menganalisis kumpulan data mentah yang berantakan hingga menghasilkan wawasan bisnis yang mengubah keputusan strategis.",
        "star_probe": {
            "situation": "Masalah bisnis apa yang dihadapi perusahaan saat itu dan seperti apa kondisi data mentah yang tersedia?",
            "task": "Hipotesis awal apa yang ingin Anda buktikan dan variabel kunci apa yang harus diisolasi?",
            "action": "Teknik pembersihan data (data cleansing), pemodelan, dan analisis statistik apa yang Anda terapkan?",
            "result": "Keputusan atau efisiensi apa yang dieksekusi oleh manajemen berdasarkan rekomendasi dari temuan data Anda?",
        },
        "look_for": [
            "Keahlian membersihkan data kotor dan mengidentifikasi outlier atau bias dalam sampel.",
            "Mampu menghubungkan temuan angka statistik dengan konteks bisnis nyata dan tindakan operasional konkret.",
            "Menyajikan kesimpulan dengan visualisasi data yang lugas dan mudah dipahami oleh non-teknis.",
        ],
        "red_flags": [
            "Melompat ke kesimpulan tanpa memeriksa kebersihan dan representasi data terlebih dahulu.",
            "Memanipulasi grafik atau metrik demi membenarkan opini pribadi yang tidak didukung data riil.",
            "Menyajikan data yang rumit tanpa rekomendasi tindakan bisnis yang jelas bagi pengambil keputusan.",
        ],
    },
    "problem solving": {
        "question": "Ceritakan masalah tak terduga paling rumit di tempat kerja yang belum pernah ada preseden solusinya sebelumnya.",
        "star_probe": {
            "situation": "Kapan masalah tersebut muncul dan dampak negatif apa yang langsung terasa bagi operasional atau klien?",
            "task": "Apa target solusi jangka pendek (workaround) dan solusi jangka panjang permanen yang harus Anda capai?",
            "action": "Bagaimana Anda membedah masalah menjadi bagian-bagian terkelola (root cause analysis) dan menguji hipotesis solusi?",
            "result": "Bagaimana efektivitas solusi yang Anda terapkan dan apa langkah preventif yang Anda lembagakan agar masalah tidak muncul lagi?",
        },
        "look_for": [
            "Menggunakan kerangka pemecahan masalah terstruktur (misal 5 Whys, Fishbone diagram, atau First Principles).",
            "Mampu mengambil keputusan tegas di bawah ketidakpastian informasi.",
            "Mengevaluasi hasil pasca-implementasi dan membagikan pembelajaran kepada tim.",
        ],
        "red_flags": [
            "Hanya mengobati gejala permukaan tanpa mencari akar permasalahan yang sesungguhnya.",
            "Menyerah atau menyalahkan situasi saat solusi awal tidak langsung membuahkan hasil.",
            "Menerapkan solusi tambal sulam yang justru menciptakan masalah baru yang lebih besar di kemudian hari.",
        ],
    },
    "cross-functional collaboration": {
        "question": "Ceritakan pengalaman Anda memimpin atau berpartisipasi dalam inisiatif lintas divisi saat terjadi benturan prioritas atau kepentingan antar-tim.",
        "star_probe": {
            "situation": "Divisi apa saja yang terlibat dan apa perbedaan sudut pandang atau target KPI masing-masing tim?",
            "task": "Apa sasaran bersama yang harus dicapai perusahaan di tengah friksi komunikasi tersebut?",
            "action": "Pendekatan komunikasi dan kompromi konstruktif apa yang Anda gunakan untuk menyelaraskan roadmap kerja tim?",
            "result": "Apakah proyek berhasil diluncurkan sesuai komitmen dan bagaimana hubungan kerja antartim setelah penyelarasan tersebut?",
        },
        "look_for": [
            "Empati terhadap kendala dan KPI tim lain serta fokus pada sasaran strategis perusahaan yang lebih besar.",
            "Mampu menegosiasikan jalan tengah tanpa mengorbankan kualitas standar hasil akhir.",
            "Menjaga transparansi komunikasi secara tertulis dan berkala untuk menghindari miskomunikasi.",
        ],
        "red_flags": [
            "Bekerja dalam silo dan bersikap defensif terhadap masukan atau kritik dari divisi lain.",
            "Mencari kambing hitam atau mengeluh di belakang rekan kerja alih-alih menyelesaikan konflik secara terbuka.",
            "Memaksakan kehendak sendiri tanpa memedulikan batasan kapasitas dan kendala rekan satu tim.",
        ],
    },
}


# ---------------------------------------------------------------------------
# Helper Matching & Normalization Utilities
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Normalize text for keyword and role matching."""
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).strip()


def _resolve_role_key(job_title: str, department: str = "") -> str:
    """Map job title and optional department to canonical role key."""
    title_norm = _normalize_text(job_title)
    dept_norm = _normalize_text(department)
    combined = f"{title_norm} {dept_norm}"

    # Match specific engineering roles
    if any(k in title_norm for k in ["backend", "back end", "python dev", "api engineer"]):
        return "backend_developer"
    if any(k in title_norm for k in ["frontend", "front end", "ui dev", "react dev", "web dev"]):
        return "frontend_developer"
    if any(k in combined for k in ["software", "developer", "programmer", "mobile dev", "android", "ios", "fullstack", "full stack"]):
        return "software_developer"

    # Match infrastructure / networking
    if any(k in combined for k in ["network admin", "jaringan", "network engineer", "cisco", "network"]):
        return "network_administrator"
    if any(k in combined for k in ["sysadmin", "system admin", "systems admin", "infrastructure", "it support", "infrastruktur"]):
        return "systems_administrator"

    # Match cybersecurity
    if any(k in combined for k in ["cyber", "security", "keamanan", "infosec", "soc analyst", "pentester", "vulnerability"]):
        return "cybersecurity_analyst"

    # Match devops / cloud
    if any(k in combined for k in ["devops", "cloud engineer", "sre", "site reliability", "platform engineer"]):
        return "devops_engineer"

    # Match data
    if any(k in combined for k in ["data scientist", "machine learning", "ml engineer", "ai engineer"]):
        return "data_scientist"
    if any(k in combined for k in ["data analyst", "analis data", "business intelligence", "bi analyst", "analytics"]):
        return "data_analyst"

    # Match accounting / finance
    if any(k in combined for k in ["clerk", "ap ar", "payable", "receivable", "kasir", "bookkeeper", "pembukuan"]):
        return "accounting_clerk"
    if any(k in combined for k in ["accountant", "akuntan", "accounting", "akuntansi", "finance", "keuangan", "pajak", "tax"]):
        return "accountant"

    # Match HR / Talent
    if any(k in combined for k in ["learning", "training", "pelatihan", "l d", "instructional"]):
        return "learning_development"
    if any(k in combined for k in ["hr manager", "people lead", "head of hr", "manajer sdm"]):
        return "hr_manager"
    if any(k in combined for k in ["hr", "human resource", "recruiter", "talent", "recruitment", "rekruitmen", "personalia", "sdm"]):
        return "hr_specialist"

    # Match Product Management
    if any(k in combined for k in ["product manager", "product owner", "project manager"]):
        return "product_manager"

    # Fallback to general professional competencies
    return "general"


# ---------------------------------------------------------------------------
# Core Public Function 1: get_criteria_recommendations
# ---------------------------------------------------------------------------

def get_criteria_recommendations(job_title: str, department: str = "") -> list[dict[str, Any]]:
    """Suggest 4-6 calibrated standard criteria based on job title and department.

    Assigns required qualifications (weight 1.0) and preferred qualifications
    (weight 0.8) to establish a healthy, unbiased baseline for intake meetings.

    Args:
        job_title: Title of the requisition (e.g. "Software Developer", "Accountant").
        department: Optional department name (e.g. "Engineering", "Finance").

    Returns:
        A list of 4-6 criterion dictionaries containing label, type, weight, and category.
    """
    clean_title = (job_title or "").strip()
    if not clean_title:
        clean_title = "Umum / General"

    role_key = _resolve_role_key(clean_title, department)
    presets = ROLE_CRITERIA_CATALOG.get(role_key, ROLE_CRITERIA_CATALOG["general"])

    # Build fresh copy of recommendations ensuring required (1.0) vs preferred (0.8)
    recommendations: list[dict[str, Any]] = []
    for item in presets:
        kind = item.get("type", "required")
        weight = DEFAULT_REQUIRED_WEIGHT if kind == "required" else DEFAULT_PREFERRED_WEIGHT
        recommendations.append({
            "label": item["label"],
            "type": kind,
            "weight": float(weight),
            "category": item.get("category", "General"),
        })

    # Ensure output is strictly 4-6 criteria
    return recommendations[:6]


# ---------------------------------------------------------------------------
# Core Public Function 2: audit_criteria_calibration
# ---------------------------------------------------------------------------

def audit_criteria_calibration(criteria: list[dict[str, Any]]) -> dict[str, Any]:
    """Audit the balance, weight distribution, and calibration health of criteria.

    Evaluates:
    - Total required vs. preferred weight and counts.
    - Detection of weight monopoly risk (any criterion > 40% of total).
    - Calibration status: 'well_calibrated' | 'unbalanced' | 'too_strict'.
    - Actionable recommendations for the job intake alignment meeting.

    Args:
        criteria: List of criteria dictionaries with keys 'label', 'type', 'weight'.

    Returns:
        Audit report dictionary with metrics, status, risk flags, and intake recommendations.
    """
    if not criteria or not isinstance(criteria, list):
        return {
            "status": "unbalanced",
            "total_weight": 0.0,
            "required_weight": 0.0,
            "preferred_weight": 0.0,
            "required_ratio": 0.0,
            "preferred_ratio": 0.0,
            "criteria_count": 0,
            "required_count": 0,
            "preferred_count": 0,
            "has_monopoly_risk": False,
            "monopoly_risk": False,
            "monopoly_criterion": None,
            "monopoly_criteria": [],
            "max_weight_ratio": 0.0,
            "recommendations": [
                "Daftar kriteria kosong. Tambahkan 4-6 kriteria terkalibrasi untuk mengevaluasi kandidat secara adil."
            ],
            "intake_notes": "Belum ada kriteria yang dimasukkan untuk requisition ini.",
        }

    total_weight = 0.0
    required_weight = 0.0
    preferred_weight = 0.0
    required_count = 0
    preferred_count = 0
    parsed_items: list[tuple[str, str, float]] = []

    for c in criteria:
        if not isinstance(c, dict):
            continue
        label = str(c.get("label") or c.get("name") or c.get("criterion") or "Unnamed").strip()
        kind = str(c.get("type", "required")).strip().lower()
        try:
            weight = float(c.get("weight", DEFAULT_REQUIRED_WEIGHT if kind == "required" else DEFAULT_PREFERRED_WEIGHT))
        except (ValueError, TypeError):
            weight = DEFAULT_REQUIRED_WEIGHT if kind == "required" else DEFAULT_PREFERRED_WEIGHT

        if weight < 0:
            weight = 0.0

        total_weight += weight
        if kind == "required":
            required_weight += weight
            required_count += 1
        else:
            # any non-required is treated as preferred
            preferred_weight += weight
            preferred_count += 1

        parsed_items.append((label, kind, weight))

    criteria_count = len(parsed_items)
    required_ratio = round(required_weight / total_weight, 4) if total_weight > 0 else 0.0
    preferred_ratio = round(preferred_weight / total_weight, 4) if total_weight > 0 else 0.0

    # Monopoly check (> 40% of total weight)
    monopoly_criteria: list[str] = []
    max_weight_ratio = 0.0
    if total_weight > 0:
        for label, _kind, w in parsed_items:
            ratio = w / total_weight
            if ratio > max_weight_ratio:
                max_weight_ratio = round(ratio, 4)
            if ratio > MONOPOLY_THRESHOLD:
                monopoly_criteria.append(label)

    has_monopoly_risk = len(monopoly_criteria) > 0
    monopoly_criterion = monopoly_criteria[0] if monopoly_criteria else None

    # Status Determination Logic
    # 1. 'too_strict': If 0 preferred criteria (100% required) or required_ratio >= 0.90
    # 2. 'unbalanced': Monopoly risk, preferred > required, or abnormal count (<3 or >8)
    # 3. 'well_calibrated': Healthy mix (3-8 criteria, no monopoly, required 55%-88%)
    recommendations: list[str] = []

    if criteria_count == 0 or total_weight <= 0:
        status = "unbalanced"
        recommendations.append("Tambahkan kriteria dengan bobot positif sebelum membuka proses seleksi.")
    elif has_monopoly_risk:
        status = "unbalanced"
        for mono in monopoly_criteria:
            recommendations.append(
                f"Kriteria '{mono}' memiliki porsi bobot di atas batas aman 40% dari total ({max_weight_ratio:.1%}). "
                "Pecah kriteria ini menjadi 2 sub-kompetensi atau turunkan bobotnya agar evaluasi menyeluruh tidak terdistorsi."
            )
    elif preferred_count == 0 or (required_count > 0 and preferred_weight == 0) or required_ratio >= 0.90:
        status = "too_strict"
        recommendations.append(
            "Semua kriteria berstatus 'wajib' (required). Pertimbangkan mengubah 1-2 kriteria spesifik "
            "menjadi 'diutamakan' (preferred) dengan bobot 0.8 agar tidak menyaring kandidat potensial secara prematur."
        )
        recommendations.append(
            "Kriteria yang terlalu kaku berisiko memicu fenomena 'purple squirrel' (ekspektasi tidak realistis) "
            "dan memperpanjang time-to-hire tanpa meningkatkan kualitas rekrutmen."
        )
    elif required_weight < preferred_weight:
        status = "unbalanced"
        recommendations.append(
            "Total bobot kriteria preferensi lebih besar dari kriteria wajib. "
            "Pastikan kualifikasi inti pekerjaan memiliki bobot lebih dominan (minimal 55-65% dari total bobot)."
        )
    elif criteria_count < 3:
        status = "unbalanced"
        recommendations.append(
            f"Jumlah kriteria saat ini ({criteria_count}) terlalu sedikit. "
            "Disarankan menyusun 4-6 kriteria untuk evaluasi kompetensi yang komprehensif."
        )
    elif criteria_count > 8:
        status = "unbalanced"
        recommendations.append(
            f"Jumlah kriteria saat ini ({criteria_count}) terlalu banyak. "
            "Batasi menjadi 4-6 kriteria inti untuk menghindari kelelahan pewawancara (interviewer fatigue) dan penilaian bias."
        )
    else:
        status = "well_calibrated"
        recommendations.append(
            "Distribusi kriteria terkalibrasi dengan baik: seimbang antara kualifikasi wajib dan nilai tambah preferensi, "
            "tanpa monopoli bobot."
        )
        recommendations.append(
            "Kriteria siap dibawa ke rapat job intake untuk ditandatangani bersama oleh Recruiter dan Hiring Manager."
        )

    # Provide concise intake meeting summary note
    if status == "well_calibrated":
        intake_notes = (
            f"Terkalibrasi sehat ({criteria_count} kriteria: {required_count} wajib, {preferred_count} preferensi). "
            f"Rasio bobot wajib: {required_ratio:.0%}, preferensi: {preferred_ratio:.0%}. Bebas monopoli bobot."
        )
    elif status == "too_strict":
        intake_notes = (
            f"Terlalu ketat ({required_count} kriteria wajib, tanpa preferensi fleksibel). "
            "Perlu melonggarkan 1-2 kriteria ke preferensi (0.8) saat rapat intake."
        )
    else:
        intake_notes = (
            f"Belum seimbang ({criteria_count} kriteria). "
            f"{'Terdapat kriteria monopoli bobot > 40%. ' if has_monopoly_risk else ''}"
            "Perlu penyesuaian bobot atau jumlah kriteria sebelum disetujui."
        )

    return {
        "status": status,
        "total_weight": round(total_weight, 2),
        "required_weight": round(required_weight, 2),
        "preferred_weight": round(preferred_weight, 2),
        "required_ratio": required_ratio,
        "preferred_ratio": preferred_ratio,
        "criteria_count": criteria_count,
        "required_count": required_count,
        "preferred_count": preferred_count,
        "has_monopoly_risk": has_monopoly_risk,
        "monopoly_risk": has_monopoly_risk,
        "monopoly_criterion": monopoly_criterion,
        "monopoly_criteria": monopoly_criteria,
        "max_weight_ratio": max_weight_ratio,
        "recommendations": recommendations,
        "intake_notes": intake_notes,
    }


# ---------------------------------------------------------------------------
# Core Public Function 3: generate_star_interview_guide
# ---------------------------------------------------------------------------

def _generate_fallback_star(criterion_label: str) -> dict[str, Any]:
    """Dynamically generate robust STAR interview guide for custom criteria."""
    label = criterion_label.strip()
    return {
        "question": (
            f"Ceritakan pengalaman nyata saat Anda harus menguasai atau menerapkan '{label}' "
            "untuk menyelesaikan tantangan pekerjaan yang signifikan."
        ),
        "star_probe": {
            "situation": f"Apa latar belakang proyek atau kondisi kerja saat '{label}' menjadi sangat krusial?",
            "task": f"Apa tanggung jawab spesifik dan target terukur yang harus Anda penuhi terkait '{label}'?",
            "action": (
                f"Langkah konkret dan metodologi apa yang Anda ambil saat mengimplementasikan '{label}'? "
                "Kendala apa yang dihadapi dan bagaimana Anda mengatasinya?"
            ),
            "result": (
                f"Apa hasil akhir yang terverifikasi (metrik, efisiensi waktu, kualitas)? "
                f"Apa pembelajaran terpenting yang Anda petik dari penerapan '{label}' tersebut?"
            ),
        },
        "look_for": [
            f"Menjelaskan pemahaman mendalam dan prinsip dasar dari '{label}' secara sistematis.",
            f"Menunjukkan kepemilikan (ownership) dan akuntabilitas pribadi saat menerapkan '{label}'.",
            "Menyajikan hasil yang terukur dan pemahaman atas trade-off keputusan yang diambil.",
        ],
        "red_flags": [
            f"Hanya menyebutkan teori permukaan tanpa mampu memaparkan studi kasus nyata penggunaan '{label}'.",
            "Mengambinghitamkan rekan kerja atau sistem ketika terjadi kendala teknis/operasional.",
            "Tidak mampu menjelaskan alasan di balik keputusan atau dampak nyata dari tindakan yang diambil.",
        ],
    }


def _find_star_template(label: str) -> dict[str, Any]:
    """Find the best matching STAR template from the bank, or generate a tailored fallback."""
    clean = _normalize_text(label)

    # 1. Exact match
    if clean in STAR_QUESTION_BANK:
        return STAR_QUESTION_BANK[clean]

    # 2. Key phrase containment match
    for key, template in STAR_QUESTION_BANK.items():
        if key in clean or clean in key:
            return template

    # 3. Domain synonyms and aliases
    alias_map = {
        "python": "programming",
        "javascript": "programming",
        "typescript": "programming",
        "java": "programming",
        "golang": "programming",
        "go": "programming",
        "react": "programming",
        "api development": "rest api",
        "microservices": "rest api",
        "postgresql": "sql",
        "mysql": "sql",
        "database": "sql",
        "unit testing": "automated testing",
        "integration testing": "automated testing",
        "qa": "automated testing",
        "linux": "server administration",
        "windows server": "server administration",
        "active directory": "server administration",
        "networking": "computer networking",
        "tcp ip": "computer networking",
        "firewall": "computer networking",
        "siem": "security monitoring",
        "incident response": "security monitoring",
        "access control": "security monitoring",
        "penetration testing": "vulnerability assessment",
        "pentest": "vulnerability assessment",
        "talent sourcing": "candidate sourcing",
        "sourcing": "candidate sourcing",
        "cv screening": "resume screening",
        "screening": "resume screening",
        "behavioral interview": "structured interviewing",
        "interviewing": "structured interviewing",
        "bookkeeping": "general ledger",
        "pembukuan": "general ledger",
        "akuntansi": "general ledger",
        "financial reporting": "financial statements",
        "laporan keuangan": "financial statements",
        "bank reconciliation": "account reconciliation",
        "rekonsiliasi": "account reconciliation",
        "data visualization": "data analysis",
        "business intelligence": "data analysis",
        "bi": "data analysis",
        "collaboration": "cross-functional collaboration",
        "teamwork": "cross-functional collaboration",
        "komunikasi": "cross-functional collaboration",
        "analisis": "problem solving",
        "analytical": "problem solving",
    }

    for alias, target_key in alias_map.items():
        if alias in clean and target_key in STAR_QUESTION_BANK:
            return STAR_QUESTION_BANK[target_key]

    # 4. Tailored dynamic fallback
    return _generate_fallback_star(label)


def generate_star_interview_guide(criteria: list[dict[str, Any] | str]) -> list[dict[str, Any]]:
    """Generate structured STAR interview guide for each criterion.

    Produces:
    - `criterion`: Name of the competency.
    - `question`: Specific behavioral interview question.
    - `star_probe`: Follow-up probing questions covering Situation, Task, Action, Result.
    - `look_for`: Positive evidence indicators (Score 4-5: Strong to Outstanding).
    - `red_flags`: Negative evidence indicators (Score 1-2: Poor to Below Expectations).

    Args:
        criteria: List of criteria dicts or strings.

    Returns:
        List of structured STAR interview guide dictionaries.
    """
    if not criteria:
        return []

    guide: list[dict[str, Any]] = []

    for item in criteria:
        if isinstance(item, str):
            label = item.strip()
            kind = "required"
            weight = DEFAULT_REQUIRED_WEIGHT
        elif isinstance(item, dict):
            label = str(item.get("label") or item.get("name") or item.get("criterion") or "Kompetensi").strip()
            kind = str(item.get("type", "required")).strip().lower()
            weight = float(item.get("weight", DEFAULT_REQUIRED_WEIGHT if kind == "required" else DEFAULT_PREFERRED_WEIGHT))
        else:
            continue

        if not label:
            label = "Kompetensi Umum"

        template = _find_star_template(label)

        entry = {
            "criterion": label,
            "type": kind,
            "weight": weight,
            "question": template["question"],
            "star_probe": {
                "situation": template["star_probe"]["situation"],
                "task": template["star_probe"]["task"],
                "action": template["star_probe"]["action"],
                "result": template["star_probe"]["result"],
            },
            "look_for": list(template.get("look_for", [])),
            "red_flags": list(template.get("red_flags", [])),
        }
        guide.append(entry)

    return guide
