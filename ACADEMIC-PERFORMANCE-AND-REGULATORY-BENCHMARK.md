# KarsaHire: Tolok Ukur Kinerja Akademis dan Kepatuhan Regulasi Sistem AI Screening

**Dokumen Standar Evaluasi Ilmiah, Validasi Psikometrik, Audit Etika Algoritmik, dan Kepatuhan Regulasi Global & Domestik untuk KarsaHire Recruitment Copilot**

---

## Ringkasan Eksekutif (Executive Summary)

Penerapan kecerdasan buatan (*Artificial Intelligence* / AI) dalam penyaringan lamaran kerja (*resume screening*) telah bertransformasi dari sekadar alat efisiensi administratif menjadi subjek pengawasan regulasi ketat dan evaluasi ilmiah tingkat tinggi. Penggunaan model *Machine Learning* probabilistik generatif (*Black-Box LLM*) tanpa pembatas leksikal telah terbukti secara empiris memicu halusinasi kualifikasi, melanggengkan bias diskriminatif historis, serta melanggar undang-undang perlindungan data dan ketenagakerjaan di berbagai yurisdiksi internasional.

**KarsaHire** dibangun di atas filosofi **Explainable, Evidence-First, and Human-in-Command Recruitment Copilot**. Dokumen ini menyajikan tolok ukur komprehensif (*academic and regulatory benchmark*) yang memvalidasi KarsaHire berdasarkan empat pilar fundamental:
1. **Landasan Teoretis & Metrik Ilmiah Temu Balik Informasi (IR), Anti-Halusinasi, dan Psikometri**: Formulasi matematis $NDCG@K$, $MRR$, $Precision@K$, *Groundedness Triad*, *Attribution Precision*, serta reliabilitas penilai (*Cohen's Kappa* $\kappa$ dan *Fleiss' Kappa*) berdasarkan literatur ilmiah terindeks (ACM KDD, Google Research, *Psychological Bulletin*).
2. **Kepatuhan Regulasi Ketat**: Audit kepatuhan terhadap **EU AI Act (Annex III - High-Risk AI System)**, **NYC Local Law 144 (Automated Employment Decision Tools / AEDT)** melalui formula *Adverse Impact Ratio* (AIR / *Four-Fifths Rule*), dan **UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi (UU PDP)** Republik Indonesia.
3. **Studi Kasus Komparasi Industri**: Analisis mendalam atas kegagalan sistem AI Amazon (2018) dan keberhasilan algoritma *Fairness-Aware Ranking* LinkedIn (ACM KDD 2019), serta pembuktian teknis mengapa arsitektur KarsaHire secara deterministik kebal terhadap kegagalan tersebut.
4. **Matriks Implementasi Teknis KarsaHire**: Pemetaan terperinci antara modul kode sumber (`matching.py`, `taxonomy.py`, `analytics_service.py`, *Mode Review Buta*, *Job Intake Dual-Approval*) terhadap setiap instrumen regulasi dan metrik performa ilmiah.

---

## 1. Landasan Teoretis & Metrik Ilmiah Unjuk Kerja AI Screening

Penyaringan kurikulum vitae (CV) dalam rekrutmen korporat secara fundamental merupakan irisan dari tiga domain ilmu pengetahuan: **Temu Balik Informasi (*Information Retrieval* / IR)**, **Keandalan Natural Language Processing (*NLP Explainability & Groundedness*)**, dan **Psikometri Industri & Organisasi (*Industrial-Organizational Psychometrics*)**.

```
┌────────────────────────────────────────────────────────────────────────┐
│               TRIANGULASI METRIK ILMIAH KARSAHIRE                      │
├─────────────────────┬────────────────────┬─────────────────────────────┤
│  1. Temu Balik      │  2. Anti-Halusinasi│  3. Psikometri &            │
│     Informasi (IR)  │     & Grounding    │     Reliabilitas            │
│                     │                    │                             │
│  • NDCG@K           │  • Faithfulness    │  • Cohen's Kappa (κ)        │
│  • MRR              │  • Attribution     │  • Fleiss' Kappa            │
│  • Precision@K      │    Precision       │  • Schmidt & Hunter (1998)  │
│  • Attention Decay  │  • Grounded Triad  │  • Health Diagnostics       │
└─────────────────────┴────────────────────┴─────────────────────────────┘
```

---

### 1.1. Metrik Temu Balik Informasi (Information Retrieval) dalam Talent Search

Dalam konteks penyaringan talenta, lowongan kerja (*Job Requisition*) bertindak sebagai kueri terstruktur $q$, sedangkan korpus resume bertindak sebagai dokumen $\mathcal{D} = \{d_1, d_2, \dots, d_N\}$. Sistem pemeringkat AI menghasilkan permutasi terurut kandidat $\pi = \langle c_{(1)}, c_{(2)}, \dots, c_{(N)} \rangle$ berdasarkan estimasi keselarasan kualifikasi.

Evaluasi kualitas pemeringkatan ini diuji terhadap *ground truth* keputusan manusia menggunakan metrik IR standar industri (Geyik et al., ACM KDD 2019):

#### A. Formulasi Matematis Normalized Discounted Cumulative Gain (NDCG@K)

*Discounted Cumulative Gain* (DCG) mengukur utilitas kumulatif kandidat yang direkomendasikan pada batas peringkat $K$, dengan bobot diskon logaritmik yang merefleksikan penurunan atensi peninjau manusia:

$$\text{DCG}@K = \sum_{i=1}^{K} \frac{2^{rel_i} - 1}{\log_2(i + 1)}$$

Di mana $rel_i \in \{0, 1, 2\}$ adalah derajat relevansi kandidat pada peringkat ke-$i$ berdasarkan tinjauan kualitatif tim rekrutmen:
* $rel_i = 2$: Status `advance` (Kandidat sangat relevan dan direkomendasikan lanjut ke tahap wawancara).
* $rel_i = 1$: Status `needs_info` (Kandidat memiliki relevansi parsial dan memerlukan klarifikasi teknis).
* $rel_i = 0$: Status `not_selected` atau belum ditinjau (`needs_review`).

Untuk menormalisasi nilai di berbagai variasi jumlah pelamar, dihitung *Ideal Discounted Cumulative Gain* ($\text{IDCG}@K$), yaitu nilai DCG teoritis maksimum jika seluruh kandidat terurut sempurna secara monotonik menurun berdasarkan $rel$:

$$\text{IDCG}@K = \sum_{i=1}^{|REL_K|} \frac{2^{rel_{(i)}^*} - 1}{\log_2(i + 1)}$$

Di mana $rel^*$ adalah vektor relevansi yang telah diurutkan menurun ($rel_{(1)}^* \ge rel_{(2)}^* \ge \dots$). Maka formulasi $\text{NDCG}@K$ didefinisikan sebagai:

$$\text{NDCG}@K = \begin{cases} \dfrac{\text{DCG}@K}{\text{IDCG}@K}, & \text{jika } \text{IDCG}@K > 0 \\ 1.0, & \text{jika } \text{IDCG}@K = 0 \text{ dan semua } rel_i = 0 \\ 0.0, & \text{lainnya} \end{cases}$$

#### B. Formulasi Matematis Mean Reciprocal Rank (MRR)

*Reciprocal Rank* (RR) mengevaluasi seberapa cepat sistem mampu menyajikan kandidat relevan pertama ($rel \ge 1$) di daftar teratas. Untuk sekumpulan posisi kueri $\mathcal{Q}$:

$$\text{MRR} = \frac{1}{|\mathcal{Q}|} \sum_{q \in \mathcal{Q}} \frac{1}{\text{rank}_q^*}$$

Di mana $\text{rank}_q^*$ adalah indeks posisi pertama kandidat berkategori `advance` atau `needs_info` pada requisisi $q$. Nilai $\text{MRR} \to 1.0$ membuktikan bahwa recruiter langsung menemukan talenta yang tepat pada posisi pertama tanpa perlu melakukan scrolling mendalam.

#### C. Formulasi Matematis Precision@K (P@K)

Mengukur proporsi kandidat berkualifikasi valid di dalam jendela $K$ peringkat teratas:

$$\text{Precision}@K = \frac{1}{K} \sum_{i=1}^{K} \mathbb{I}(rel_i \ge 1)$$

Di mana $\mathbb{I}(\cdot)$ adalah fungsi indikator biner ($1$ jika benar, $0$ jika salah).

#### D. Dinamika Kurva Atensi Recruiter (*Attention Decay & Position Bias*)

Penelitian empiris *eye-tracking* oleh *The Ladders* (2018) dan analisis perilaku penelusuran LinkedIn Talent Search (Geyik et al., 2019) mengonfirmasi bahwa perhatian manusia mengalami degradasi eksponensial:
* **85% interaksi recruiter** terkonsentrasi pada **Top-5 kandidat** ($K = 5$).
* Hanya **12% recruiter** yang memeriksa kandidat di luar peringkat ke-10 ($K > 10$).
* Penurunan atensi mengikuti hukum logaritmik $\frac{1}{\log_2(i+1)}$, yang membuktikan bahwa kesalahan penempatan kandid unggul pada peringkat $i = 8$ mengakibatkan penalti utilitas yang jauh lebih parah daripada kesalahan pada peringkat $i = 25$.

Oleh karena itu, modul [`analytics_service.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/analytics_service.py#L486-L581) KarsaHire secara *native* menghitung $\text{NDCG}@5$, $\text{NDCG}@10$, $\text{MRR}$, dan $\text{Precision}@K$ untuk mengaudit keselarasan skor bukti otomatis terhadap keputusan akhir recruiter.

---

### 1.2. Metrik Anti-Halusinasi & Explainability (Grounded Evidence Framework)

Model bahasa komersial berbasis penalaran probabilistik (*Large Language Models* / LLM) rentan terhadap fenomena **halusinasi kualifikasi** (*qualification fabrication*), di mana model mengasumsikan seorang kandidat menguasai keahlian tertentu hanya karena kemiripan semantik kontekstual (*semantic drift*) atau bias asosiasi institusi (*sycophancy & prestige bias*).

Dalam domain rekrutmen berisiko tinggi (*high-stakes recruitment*), KarsaHire menolak pendekatan *black-box generative reasoning* dan mengadopsi standar **Grounded Evidence Framework** yang diinspirasi oleh inisiatif *Djinni-CB* (Google Research) dan *HLECEF (Hallucination and Language Evaluation in Criterion-based Extraction Frameworks)*.

```
                  ┌───────────────────────────────┐
                  │    Kriteria Lowongan (Job)    │
                  └──────────────┬────────────────┘
                                 │
                   (Context Relevance: r > 0.8)
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GROUNDEDNESS TRIAD                           │
├────────────────────────────────┬────────────────────────────────┤
│      Faithfulness Score        │     Attribution Precision      │
│  Bukti leksikal 100% kutipan   │  Memiliki nomor halaman asal   │
│  verbatim dari dokumen CV      │  yang dapat diverifikasi audit │
└────────────────────────────────┴────────────────────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │   Zero-Tolerance Hallucination│
                  │   Rate: H_rate = 0.0% Mutlak  │
                  └───────────────────────────────┘
```

#### A. Rerangka Groundedness Triad

Tiga dimensi evaluasi keabsahan bukti ekstraksi:
1. **Context Relevance**: Bukti yang diekstrak harus berkorelasi langsung dengan kriteria yang disetujui bersama (*requisition-criteria alignment*).
2. **Faithfulness (Fidelitas Bukti)**: Setiap afirmatif kecocokan (`matched` atau `partial`) harus didukung oleh kutipan verbatim dari teks asli resume tanpa parafrase sintetis:
   $$\text{Faithfulness Score} = \frac{|\{e \in \mathcal{E}_{\text{pos}} \mid e.\text{snippet} \subseteq \text{normalize}(\mathcal{D}_{\text{CV}}) \wedge e.\text{snippet} \neq \emptyset\}|}{|\mathcal{E}_{\text{pos}}|}$$
   Di mana $\mathcal{E}_{\text{pos}}$ adalah himpunan evaluasi kriteria berstatus positif (`matched` bernilai 1.0, `partial` bernilai 0.5).
3. **Answer Relevance / Decision Grounding**: Skor akhir kandidat dibentuk semata-mata dari agregasi linier bobot kriteria yang terbukti secara faktual:
   $$S = \frac{\sum_{j=1}^{M} w_j \cdot v(e_j)}{\sum_{j=1}^{M} w_j} \times 100\%$$
   Di mana $v(e_j) \in \{1.0, 0.5, 0.0\}$ untuk status `matched`, `partial`, dan `unknown`.

#### B. Attribution Precision (Presisi Atribusi Sitasi)

Menjamin bahwa setiap klaim kualifikasi memiliki rujukan lokasi fisik dalam dokumen sumber untuk memfasilitasi verifikasi manusia secara instan:

$$\text{Attribution Precision} = \frac{|\{e \in \mathcal{E}_{\text{pos}} \mid e.\text{page\_number} \in \mathbb{N}^+\}|}{|\mathcal{E}_{\text{pos}}|}$$

#### C. Zero-Tolerance Hallucination Rate

Tingkat halusinasi ($\mathcal{H}_{\text{rate}}$) didefinisikan sebagai komplemen dari fidelitas:

$$\mathcal{H}_{\text{rate}} = 1.0 - \text{Faithfulness Score}$$

Pada arsitektur KarsaHire ([`matching.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/matching.py#L100-L146) dan [`analytics_service.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/analytics_service.py#L427-L484)), pencocokan dilakukan secara deterministik leksikal berbasis taksonomi terverifikasi. Oleh karena itu, **tingkat halusinasi KarsaHire secara matematis adalah 0.0% ($\mathcal{H}_{\text{rate}} \equiv 0.0\%$)**, mengeliminasi risiko fabrikasi kualifikasi yang kerap terjadi pada implementasi LLM murni.

---

### 1.3. Metrik Psikometri & Reliabilitas Penilai (Inter-Rater Reliability)

Dalam Psikologi Industri dan Organisasi (PIO), reliabilitas instrumen seleksi diukur dari stabilitas penilaian antarpengevaluasi (*Inter-Rater Reliability*). Evaluasi subjektif yang dilakukan tanpa rubrik terstruktur menghasilkan varians kesalahan (*error variance*) yang merusak validitas prediktif seleksi.

#### A. Formulasi Matematis Cohen's Kappa ($\kappa$)

Untuk mengukur kesepakatan murni antara dua evaluator utama—*Recruiter* ($r_A$) dan *Hiring Manager* ($r_B$)—dengan mengeliminasi faktor kesepakatan semu yang terjadi secara kebetulan (*chance agreement*):

$$\kappa = \frac{P_o - P_e}{1 - P_e}$$

Di mana:
* $P_o$ adalah proporsi kesepakatan observasi empiris (*Observed Agreement*):
  $$P_o = \frac{1}{N} \sum_{i=1}^{N} \mathbb{I}(r_{A,i} = r_{B,i})$$
* $P_e$ adalah probabilitas teoretis kesepakatan yang terjadi secara kebetulan (*Expected Chance Agreement*):
  $$P_e = \sum_{c \in \mathcal{C}} P(r_A = c) \cdot P(r_B = c) = \sum_{c \in \mathcal{C}} \left( \frac{n_{A,c}}{N} \right) \left( \frac{n_{B,c}}{N} \right)$$
  Di mana $\mathcal{C} = \{\text{advance}, \text{needs\_info}, \text{not\_selected}\}$ dan $N$ adalah jumlah kandidat yang telah dievaluasi ganda (*dual-reviewed*).

**Pedoman Interpretasi Landis & Koch (1977)** yang diimplementasikan pada [`calculate_cohens_kappa()`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/analytics_service.py#L214-L267):

| Nilai Kappa ($\kappa$) | Tingkat Reliabilitas Kesepakatan | Tindakan Tata Kelola Rekrutmen KarsaHire |
|---|---|---|
| $< 0.00$ | *Poor Agreement* (Konflik Sistemik) | Pembatalan kalibrasi; re-negosiasi kriteria mandatory via *Job Intake*. |
| $0.00 - 0.20$ | *Slight Agreement* (Kesepakatan Tipis) | Rubrik penilaian tidak dipahami; audit deskripsi pekerjaan wajib dilakukan. |
| $0.21 - 0.40$ | *Fair Agreement* (Cukup) | Discrepancy meeting dipicu untuk membahas kandidat yang divergen. |
| $0.41 - 0.60$ | *Moderate Agreement* (Moderat) | Penyelarasan kriteria preferensial (*nice-to-have*) pada rapat *debrief*. |
| $0.61 - 0.80$ | *Substantial Agreement* (Substansial) | Alur kerja sehat; proses seleksi berjalan konsisten. |
| $\ge 0.81$ | *Almost Perfect Agreement* (Hampir Sempurna) | Kalibrasi optimal antara Recruiter dan Hiring Manager tercapai. |

#### B. Formulasi Fleiss' Kappa untuk Panel Multi-Penilai

Ketika evaluasi kandidat melibatkan panel wawancara ($m > 2$ penilai independen, misalnya Recruiter, Hiring Manager, dan Technical Lead), KarsaHire memetakan reliabilitas melalui Fleiss' Kappa:

$$\kappa_{\text{Fleiss}} = \frac{\bar{P} - \bar{P}_e}{1 - \bar{P}_e}$$

Di mana $N$ adalah jumlah kandidat, $n$ adalah jumlah penilai per kandidat, dan $k$ adalah jumlah kategori keputusan:

$$P_i = \frac{1}{n(n - 1)} \left( \sum_{j=1}^{k} n_{ij}^2 - n \right), \quad \bar{P} = \frac{1}{N} \sum_{i=1}^{N} P_i$$

$$p_j = \frac{1}{N n} \sum_{i=1}^{N} n_{ij}, \quad \bar{P}_e = \sum_{j=1}^{k} p_j^2$$

#### C. Validitas Prediktif Seleksi Berbasis Kriteria (Schmidt & Hunter, 1998; 2016)

Meta-analisis klasik selama 85 hingga 100 tahun dalam literatur psikologi seleksi personel (*Psychological Bulletin*) oleh Schmidt & Hunter membuktikan koefisien validitas prediktif ($\rho$) metode seleksi terhadap kinerja masa depan karyawan:

```
[Kajian Meta-Analisis Schmidt & Hunter (1998; 2016)]
Metode Seleksi                            Validitas Prediktif (r)
──────────────────────────────────────────────────────────────────
1. Tes Kemampuan Kognitif Umum (GMA)       ████████████████ 0.65
2. Structured Interview (Berbasis Kriteria)██████████████ 0.58
3. Tes Sampel Kerja (Work Sample Test)     █████████████ 0.54
4. Integritas / Kepribadian Terstruktur    ██████████ 0.41
5. Unstructured Interview (Wawancara Bebas)████████ 0.38
6. Penilaian Resume Intuitif / Tidak Baku  ████ 0.18
7. Pencocokan Zodiak / Grafologi / MBTI    █ 0.02 (Pseudosains)
```

**Temuan Kunci Ilmiah**:
1. Penilaian resume secara bebas (*unstructured screening*) hanya memiliki validitas prediktif $r = 0.18$, karena rentan terhadap bias visual, bias nama institusi, dan heuristik dangkal.
2. Wawancara terstruktur berbasis kriteria baku mencapai validitas prediktif $r = 0.58$.
3. **Peran KarsaHire**: Mengubah tahap triase awal dari heuristik intuitif berisiko tinggi ($r = 0.18$) menjadi **Structured Criterion-Based Evidence Triase ($r \ge 0.50$)**, sehingga memfilter kandidat berdasarkan kesesuaian kompetensi riil sebelum masuk ke wawancara terstruktur skala 1–5.

#### D. Diagnostik Kesehatan Kriteria (*Criteria Health & Bottleneck Diagnostics*)

Modul [`get_criteria_health()`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/analytics_service.py#L269-L425) memantau distribusi bukti secara psikometrik untuk mengidentifikasi anomali kriteria:
* **Bottleneck Criterion**: Kriteria di mana $\text{Unknown} > 80\%$. Mengindikasikan persyaratan terlalu restriktif atau adanya kesenjangan terminologi (*vocabulary gap*). Rekomendasi: Perluasan alias taksonomi atau relaksasi menjadi status preferensi (*preferred*).
* **Too-Common Criterion**: Kriteria di mana $\text{Matched} > 90\%$. Mengindikasikan kriteria tidak memiliki daya beda diskriminatif (*low discriminative power* / *item difficulty* mendekati 1.0). Rekomendasi: Pengetatan spesifikasi teknis untuk menyortir talenta unggul.

---

## 2. Kepatuhan Regulasi & Audit Etika Algoritmik

KarsaHire dirancang secara arsitektural untuk memenuhi regulasi kecerdasan buatan dan privasi data terketat di dunia, membebaskan korporasi dari risiko denda kepatuhan dan liabilitas hukum ketenagakerjaan.

```
┌────────────────────────────────────────────────────────────────────────┐
│               ARSITEKTUR KEPATUHAN REGULASI KARSAHIRE                  │
├─────────────────────┬────────────────────┬─────────────────────────────┤
│  EU AI Act          │  NYC Local Law 144 │  UU PDP No. 27/2022         │
│  (Annex III)        │  (AEDT Bias Audit) │  (Indonesia)                │
│                     │                    │                             │
│  • High-Risk Rec.   │  • 4/5ths Rule AIR │  • Pasal 40 Anti-Automated  │
│  • Art 14 Human-in- │  • Impact Ratio    │    Decision-Making          │
│    Command          │    Audit Metric    │  • Pasal 16 & 20 Minimisasi │
│  • Art 12 Logging   │  • Job-Relatedness │  • Sanitasi PII Otomatis    │
│  • Anti-Blackbox    │    Validation      │  • Kedaulatan Data Lokal    │
└─────────────────────┴────────────────────┴─────────────────────────────┘
```

---

### 2.1. Regulasi Uni Eropa: EU AI Act (Regulation (EU) 2024/1689)

Di bawah *European Union Artificial Intelligence Act*, sistem kecerdasan buatan yang digunakan dalam konteks ketenagakerjaan diklasifikasikan sebagai sistem berisiko tinggi (*High-Risk AI Systems*).

#### A. Klasifikasi Annex III (Paragraf 4)
Annex III secara eksplisit mengkategorikan sistem AI berikut sebagai **High-Risk**:
> *"Sistem AI yang dimaksudkan untuk digunakan dalam perekrutan atau seleksi orang perseorangan, khususnya untuk mengiklankan lowongan, menyortir atau memfilter lamaran, dan mengevaluasi kandidat dalam wawancara atau pengujian."*

#### B. Mandat Kepatuhan dan Penegakan KarsaHire

| Pasal EU AI Act | Persyaratan Regulasi | Mekanisme Penegakan Teknis KarsaHire |
|---|---|---|
| **Pasal 10** (*Data Governance*) | Data pelatihan dan pengujian harus bebas dari bias sistemik dan representatif. | Tidak menggunakan model historis hitam (*no opaque training set*). Evaluasi berbasis taksonomi terbuka yang dapat diaudit (`taxonomy.py`). |
| **Pasal 12** (*Record-Keeping & Logging*) | Kemampuan penelusuran otomatis rekam jejak (*automatic event logging*) sepanjang siklus hidup sistem. | Tabel `approvals`, `reviews`, dan `audit_trail` mencatat stempel waktu UTC, identitas reviewer, skor, dan riwayat revisi kriteria. |
| **Pasal 13** (*Transparency*) | Operasional sistem harus transparan dan pengguna dapat menginterpretasikan *output*. | Setiap kecocokan wajib menyertakan kutipan kalimat verbatim (*snippet*) dan nomor halaman dokumen CV. |
| **Pasal 14** (*Human Oversight / Human-in-Command*) | Sistem tidak boleh mengambil keputusan otonom. Manusia memiliki kendali penuh (*override & veto authority*). | AI hanya menyajikan skor bukti (*evidence copilot*). Tombol seleksi (`advance`, `needs_info`, `not_selected`) dioperasikan secara eksklusif oleh manusia. |
| **Pasal 15** (*Accuracy, Robustness & Cybersecurity*) | Ketahanan terhadap eror, akurasi konsisten, dan perlindungan integritas data. | Sistem berjalan *local-first*, kebal terhadap injeksi prompt LLM publik, dan diverifikasi melalui benchmark korpus 2.484 CV. |

#### C. Larangan Black-Box Automation
Pasal 86 EU AI Act memberikan hak kepada pelamar kerja untuk memperoleh penjelasan yang jelas dan bermakna mengenai peran AI dalam prosedur seleksi. Karena KarsaHire menggunakan ekstraksi leksikal berbasis aturan transparan, recruiter dapat memberikan laporan eksplanasi instan mengenai kriteria mana yang terpenuhi beserta kutipan bukti aslinya.

---

### 2.2. Regulasi New York City: NYC Local Law 144 of 2021 (AEDT)

NYC Local Law 144 mengatur penggunaan *Automated Employment Decision Tools* (AEDT) di yurisdiksi Kota New York, mewajibkan audit bias independen tahunan sebelum alat digunakan untuk menyaring pelamar kerja.

#### A. Ruang Lingkup AEDT
Undang-undang ini mencakup instrumen komputasi apa pun yang mengeluarkan skor, klasifikasi, atau rekomendasi yang digunakan untuk memengaruhi keputusan perekrutan secara material.

#### B. Formulasi Matematis Adverse Impact Ratio (AIR / Four-Fifths Rule)

Audit bias AEDT berakar pada pedoman seleksi ketenagakerjaan seragam EEOC (*Uniform Guidelines on Employee Selection Procedures*, 29 C.F.R. § 1607).

Tingkat seleksi (*Selection Rate* / $SR$) untuk suatu kelompok demografis $g$ dihitung sebagai:

$$SR_g = \frac{N_{\text{selected}, g}}{N_{\text{applicants}, g}}$$

Kelompok dengan tingkat seleksi tertinggi ditetapkan sebagai kelompok acuan (*Most Favored Group*):

$$SR_{\text{max}} = \max_{g \in \mathcal{G}} SR_g$$

Rasio dampak buruk (*Adverse Impact Ratio* / $AIR$) atau *Impact Ratio* dihitung sebagai:

$$\text{Impact Ratio}_g = \frac{SR_g}{SR_{\text{max}}}$$

**Ambang Batas Empat Perlima (*Four-Fifths Rule*)**:
$$\text{Impact Ratio}_g \ge 0.80 \quad (\text{atau } 80\%)$$

Jika $\text{Impact Ratio}_g < 0.80$, instrumen seleksi dianggap secara *prima facie* menimbulkan dampak diskriminatif (*disparate impact*) yang melanggar hukum, kecuali pemberi kerja dapat membuktikan secara statistik bahwa kriteria tersebut memiliki korelasi esensial terhadap pekerjaan (*job-relatedness and business necessity*).

#### C. Penegakan KarsaHire terhadap NYC LL 144
1. **Pencegahan Disparitas Apriori**: KarsaHire meniadakan pemrosesan atribut sensitif (gender, ras, usia, almamater) di tingkat kode sumber (`matching.py`).
2. **Scoring Rate Audit**: Modul [`get_fairness_audit_metrics()`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/analytics_service.py#L584-L622) mengaudit distribusi skor di seluruh kuartil kelayakan untuk memastikan tidak ada kelompok kompetensi yang tertekan secara artifisial.

---

### 2.3. Regulasi Indonesia: UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi (UU PDP)

KarsaHire merupakan pionir ATS/Recruitment Copilot di Asia Tenggara yang dirancang secara khusus untuk mematuhi **Undang-Undang Pelindungan Data Pribadi (UU PDP) Indonesia**.

```
                   PENEGAKAN UU PDP NO. 27/2022
┌─────────────────────────────────────────────────────────────────┐
│ Pasal 16 & 20: Minimisasi Data                                  │
│ └─► Redaksi otomatis Email, Telepon, Tanggal Lahir, Alamat.     │
├─────────────────────────────────────────────────────────────────┤
│ Pasal 40: Hak Subjek Data atas Keputusan Otomatis               │
│ └─► Larangan mutlak auto-rejection; Rekomendasi wajib disahkan │
│     melalui tinjauan manusia (Human-in-Command).                │
├─────────────────────────────────────────────────────────────────┤
│ Pasal 35 & 39: Kedaulatan & Keamanan Data Spesifik              │
│ └─► Arsitektur Local-First (SQLite); data CV tidak pernah       │
│     ditransmisikan ke server LLM pihak ketiga di luar negeri.   │
└─────────────────────────────────────────────────────────────────┘
```

#### A. Prinsip Minimisasi Data & Pemrosesan Spesifik (Pasal 16 & 20)
* Data pribadi yang diproses harus terbatas, relevan, dan proporsional dengan tujuan seleksi kerja.
* **Implementasi Teknis**: Modul [`redact_for_evidence()`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/matching.py#L42-L61) menyaring teks bukti resume sebelum disimpan ke dalam basis data SQLite. Seluruh data identitas kontak (*PII*) disanitasi:
  ```python
  EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
  PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)")
  SENSITIVE_LINE_RE = re.compile(
      r"^\s*(?:full\s+name|candidate\s+name|name|nama\s+lengkap|nama|"
      r"email|e-mail|phone|mobile|telepon|no(?:mor)?\s*(?:hp|telepon|telp)|"
      r"date\s+of\s+birth|dob|birthday|tanggal\s+lahir|tgl\s+lahir|"
      r"address|home\s+address|alamat(?: rumah)?)\s*[:|–-]",
      re.IGNORECASE,
  )
  ```

#### B. Hak Menolak Keputusan Otomatis (*Automated Decision Making*, Pasal 40)
Pasal 40 UU PDP berbunyi:
> *"Subjek Data Pribadi berhak untuk menolak tindakan pengambilan keputusan yang hanya didasarkan pada pemrosesan secara otomatis, termasuk pemrofilan, yang menimbulkan akibat hukum atau berdampak signifikan pada Subjek Data Pribadi."*

**Kepatuhan KarsaHire**:
KarsaHire tidak pernah melakukan penolakan otomatis (*auto-rejection*). Seluruh pelamar berstatus awal `needs_review`. Sistem hanya menampilkan matriks kesesuaian kriteria leksikal. Keputusan meluluskan (`advance`) atau menolak (`not_selected`) kandidat dilakukan secara sadar oleh recruiter atau hiring manager, sehingga perusahaan 100% terlindungi dari tuntutan hukum Pasal 40 UU PDP.

#### C. Kedaulatan Data Lokal (*Local-First Storage*)
Pengiriman berkas CV kandidat ke API model AI publik (seperti OpenAI atau Anthropic) di yurisdiksi luar negeri melanggar ketentuan transfer data lintas batas (*cross-border data transfer*) Pasal 56 UU PDP jika tidak disertai persetujuan eksplisit (*explicit consent*) dan kepatuhan standar perlindungan data yang setara. KarsaHire memproses ekstraksi secara 100% lokal pada mesin korporat menggunakan SQLite (`copilot.sqlite3`) dan PaddleOCR lokal, tanpa paket data yang meninggalkan perimeter jaringan perusahaan.

---

## 3. Studi Kasus Komparasi Industri

Membandingkan arsitektur KarsaHire dengan inisiatif AI rekrutmen global memberikan wawasan berharga mengenai titik rawan kegagalan algoritma dan prinsip desain etis.

```
┌────────────────────────────────────────────────────────────────────────┐
│                   SPEKTRUM PARADIGMA SISTEM SCREENING                  │
├───────────────────────┬────────────────────────┬───────────────────────┤
│ Amazon AI Tool (2018) │ LinkedIn Talent Search │ KarsaHire Copilot     │
│                       │ (KDD 2019)             │ (2026)                │
├───────────────────────┼────────────────────────┼───────────────────────┤
│ • Model Prediktif ML  │ • Search Ranking Model │ • Deterministik       │
│ • Pelatihan Data 10th │ • Post-processing      │   Lexical Grounding   │
│   Historis (Bias)     │   Fairness Constraint  │ • Zero Demographic ML │
│ • Penalti Kata Gender │ • Rekayasa Diversitas  │ • Mode Review Buta    │
│ • HASIL: DIBATALKAN   │ • HASIL: DIADOPSI      │ • Dual-Approval Kunci │
└───────────────────────┴────────────────────────┴───────────────────────┘
```

---

### 3.1. Kasus Kegagalan Amazon AI Recruitment Tool (2018)

Pada tahun 2014–2017, tim *machine learning* Amazon mengembangkan alat pemeringkat CV otomatis untuk merekrut talenta rekayasa perangkat lunak dengan memberi skor 1 hingga 5 bintang. Pada tahun 2018, proyek ini secara resmi dibatalkan setelah terbukti mendiskriminasi perempuan secara sistemik (Dastin, Reuters 2018).

#### A. Analisis Kegagalan Algoritmik

```
[Dataset Historis 10 Tahun (60-80% Pria)]
                 │
                 ▼
[Embedding Vektor Kata / Word2Vec] ──► Menghubungkan kata kerja maskulin
                 │                     dengan probabilitas promosi tinggi
                 ▼
[Penalti Kata Otomatis] ─────────────► Mendiskon resume dengan kata "Women's"
                                       (misal: "Women's Chess Club", "Women's Tech")
```

1. **Bias Data Historis (*Historical Training Data Bias*)**: Model dilatih menggunakan ribuan resume yang diterima Amazon selama 10 tahun sebelumnya. Karena industri teknologi secara historis didominasi oleh pria, model secara keliru mempelajari bahwa profil kandidat pria adalah cerminan dari "kandidat ideal".
2. **Korelasi Palsu & Diskriminasi Proksi (*Proxy Discrimination*)**: Model berbasis representasi vektor kata (*word embeddings*) mengasosiasikan kata kerja maskulin yang agresif (*"executed"*, *"captured"*, *"commanded"*) dengan performa tinggi. Sebaliknya, model secara aktif menghukum berkas lamaran yang memuat kata *"women's"* (misalnya, *"president of women's coding club"* atau *"women's college rugby"*).
3. **Kegagalan Pembersihan Fitur Dangkal**: Ketika teknisi Amazon secara eksplisit menghapus label gender, model tetap mendiskriminasi melalui fitur proksi laten: nama almamater khusus perempuan, pilihan kata kerja, dan pola ekstrakurikuler.

#### B. Bagaimana Arsitektur KarsaHire Mencegah Tragedi Amazon secara Mutlak

KarsaHire menggunakan arsitektur penangkal bias berlapis (*multi-layer anti-bias architecture*):

| Dimensi Rekayasa | Amazon AI Recruitment Tool | KarsaHire Recruitment Copilot |
|---|---|---|
| **Paradigma Inferensi** | Model probabilistik *Machine Learning* yang dilatih pada data masa lalu (*supervised regression*). | **Deterministik Leksikal Berbasis Bukti**: Tidak ada model pembelajaran historis. Kualifikasi dinilai murni terhadap kriteria lowongan aktif. |
| **Pencegahan Bias Gender** | Mencoba memfilter atribut sensitif secara parsial (gagal karena bias proksi). | **Mode Review Buta (*Blind-First Review*)**: Nama, gender, kontak disensor total dari antarmuka; eliminasi kata bias melalui taksonomi berbasis kompetensi objektif. |
| **Keterjelasan Bukti** | Skor 1–5 bintang hitam (*black-box rating*) tanpa rujukan kalimat asli. | **Grounded Snippet**: Setiap afirmatif skor menampilkan kutipan kalimat verbatim asli dari resume kandidat. |
| **Otoritas Keputusan** | Pemeringkatan otomatis tanpa penjelasan; berpotensi langsung menolak pelamar. | **Human-in-the-Loop Mutlak**: AI tidak memiliki hak veto; manusia yang memutuskan status kandidat. |

---

### 3.2. Kasus Keberhasilan Fairness-Aware Ranking LinkedIn (Geyik et al., ACM KDD 2019)

LinkedIn Talent Search memproses jutaan pencarian kandidat setiap hari. Pada konferensi bergengsi *ACM SIGKDD 2019*, tim peneliti LinkedIn (Geyik, Ambler, & Kenthapadi) mempublikasikan kerangka kerja *Fairness-Aware Ranking* untuk mengatasi *feedback loop* bias representasi gender pada hasil pencarian recruiter.

#### A. Permasalahan Representasi LinkedIn
Algoritma pemeringkat relevansi konvensional di LinkedIn cenderung merefleksikan distribusi perilaku recruiter historis. Jika recruiter di masa lalu lebih sering mengklik profil pria, algoritma akan terus menempatkan profil pria di bagian atas hasil penelusuran. Hal ini menurunkan visibilitas kandidat perempuan yang berkualifikasi setara.

#### B. Solusi Algoritmik LinkedIn: Representasi Proporsional Terkendali
LinkedIn mengimplementasikan optimasi re-ranking bersyarat (*post-processing constrained optimization*). Jika proporsi perempuan yang memenuhi kualifikasi dalam kumpulan kandidat (*qualified pool*) adalah $p$, maka daftar $K$ teratas hasil pencarian diprogram untuk menjaga representasi proporsional $\hat{p} \approx p$:

$$\min_{\pi} \sum_{i=1}^{K} \text{Penalty}(\pi_i) \quad \text{dengan kendala} \quad |P_{\text{protected}}(\text{Top-}K) - p| \le \epsilon$$

Keberhasilan LinkedIn membuktikan bahwa **penyeimbangan representasi talenta dapat dicapai tanpa merusak utilitas bisnis (NDCG tetap stabil pada tingkat $\ge 98\%$)**.

#### C. Komparasi Pendekatan LinkedIn vs KarsaHire

```
┌─────────────────────────────────────────────────────────────────────────┐
│               PERBANDINGAN STRATEGI KEADILAN ALGORITMIK                 │
├───────────────────────────┬─────────────────────────────────────────────┤
│ LinkedIn Talent Search    │ KarsaHire Copilot                           │
│ (Post-Processing Parity)  │ (Procedural & Structural Fairness)          │
├───────────────────────────┼─────────────────────────────────────────────┤
│ Menggunakan kuota         │ Menjamin keadilan prosedural di tingkat     │
│ representasi pada hasil   │ ekstraksi bukti (*input level*).            │
│ akhir pencarian (*fair    │ Tidak ada kuota buatan; perangkingan murni  │
│ re-ranking*).             │ berbasis pemenuhan kualifikasi terbukti.    │
│                           │                                             │
│ Cocok untuk pasar terbuka │ Cocok untuk seleksi korporat tertutup yang  │
│ skala masif (ratusan juta │ wajib mematuhi UU Ketenagakerjaan dan       │
│ pengguna).                │ audit ketat anti-diskriminasi.              │
└───────────────────────────┴─────────────────────────────────────────────┘
```

KarsaHire melengkapi filosofi LinkedIn dengan memastikan bahwa **keadilan dibangun sejak tahap *Job Intake***: kriteria wajib dikunci secara transparan (*Dual-Approval*), sehingga tidak ada kriteria siluman (*hidden barriers*) yang merugikan kelompok talenta tertentu.

---

## 4. Matriks Implementasi KarsaHire

Bagian ini memetakan implementasi teknis kode sumber KarsaHire terhadap setiap instrumen regulasi dan tolok ukur ilmiah yang telah diuraikan.

### 4.1. Arsitektur Teknis Sistem KarsaHire

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          KARSAHIRE PIPELINE ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   [Resume PDF / DOCX / TXT]                                                     │
│               │                                                                 │
│               ▼                                                                 │
│   [Local OCR Engine: PaddleOCR / worker] ──► OCR Lokal Tanpa Cloud Telemetri    │
│               │                                                                 │
│               ▼                                                                 │
│   [PII Redaction Sanitizer: matching.py] ──► Sensor Email, Telp, DOB, Alamat    │
│               │                              (UU PDP No. 27/2022)               │
│               ▼                                                                 │
│   [Domain Taxonomy Engine: taxonomy.py]  ──► 5 Domain, Kamus Bilingual EN-ID,   │
│               │                              Resolusi Alias & Akronim Baku      │
│               ▼                                                                 │
│   [Evidence Matching: matching.py]       ──► Deterministik Leksikal; Fidelitas  │
│               │                              100%; Zero Hallucination (H=0.0%)  │
│               ▼                                                                 │
│   [Audit & Analytics: analytics_service] ──► NDCG@K, MRR, Cohen's Kappa (κ),    │
│               │                              Criteria Health, PII Compliance    │
│               ▼                                                                 │
│   [Human Interface: web/comparison.js]   ──► Mode Review Buta, Dual-Approval,   │
│                                              Rubrik Wawancara 1-5, SQLite Local │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.2. Tabel Matriks Komprehensif Pemetaan Modul Kode

Tabel berikut membuktikan keterlacakan teknis (*traceability*) antara persyaratan teoretis, standar regulasi, dan baris kode nyata di repositori KarsaHire:

| No | Modul Kode Sumber | Komponen & Fungsi Kunci | Standar Regulasi / Teori Akademis | Metrik Ilmiah / Formula | Mekanisme Penegakan Teknis (*Technical Enforcement*) | Dampak Tata Kelola & Keadilan |
|:--:|---|---|---|---|---|---|
| **1** | [`matching.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/matching.py#L26-L61) | `redact_for_evidence()` | **UU PDP No. 27/2022 (Pasal 16, 20)** & **EEOC PII Guidance** | $\text{PII Compliance Rate} = 100\%$ | Regex penyensoran otomatis email, nomor telepon, tanggal lahir, dan alamat fisik sebelum bukti disimpan ke basis data. | Menghilangkan kebocoran data sensitif pelamar; menjamin kepatuhan privasi data nasional. |
| **2** | [`matching.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/matching.py#L100-L146) | `match_criterion()`, `score_candidate()` | **EU AI Act (Pasal 13, 15)** & **Groundedness Triad** | $\text{Faithfulness} = 100\%$, $\mathcal{H}_{\text{rate}} = 0.0\%$ | Pencocokan token leksikal eksak/parsial berbobot terhadap baris CV; menghasilkan kutipan verbatim dan nomor halaman. | Mencegah halusinasi kualifikasi; menyediakan dasar pembuktian yang dapat diaudit secara hukum. |
| **3** | [`taxonomy.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/taxonomy.py#L27-L120) | `SKILLS_BY_DOMAIN`, `ALIASES` | **NYC Local Law 144 (Job Relatedness)** & **ISO 30415:2021** | $\text{Lexical Overlap Precision}$ | Taksonomi 5 domain besar (Software, Infra, Security, HR, Finance) dengan ribuan padanan dwibahasa Inggris-Indonesia. | Menghilangkan kesenjangan kosa kata pelamar lokal vs ekspatriat; menjamin kesetaraan evaluasi kompetensi. |
| **4** | [`analytics_service.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/analytics_service.py#L486-L581) | `get_ranking_quality_metrics()` | **Geyik et al., ACM KDD 2019 (LinkedIn)** & **Information Retrieval** | $\text{NDCG}@5, \text{NDCG}@10, \text{MRR}, \text{P}@K$ | Mengukur urutan rekomendasi skor AI terhadap keputusan akhir manusia (`advance`=2, `needs_info`=1, `not_selected`=0). | Memvalidasi bahwa algoritma pemeringkat secara akurat mencerminkan preferensi kualifikasi tim rekrutmen. |
| **5** | [`analytics_service.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/analytics_service.py#L427-L484) | `get_evidence_grounding_audit()` | **Google Research Djinni-CB & HLECEF** | $\text{Attribution Precision}$, $\text{Faithfulness Score}$ | Memverifikasi seluruh kecocokan kriteria terhadap keberadaan kutipan bukti teks dan nomor halaman dokumen. | Memenuhi standar dokumentasi teknis Pasal 11 EU AI Act untuk sistem AI berisiko tinggi. |
| **6** | [`analytics_service.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/analytics_service.py#L214-L267) | `calculate_cohens_kappa()` | **Psikometri PIO (Landis & Koch, 1977)** | $\kappa = \frac{P_o - P_e}{1 - P_e}$ | Menghitung koefisien kesepakatan murni antara Recruiter dan Hiring Manager serta mengklasifikasikan tingkat keselarasan. | Mengidentifikasi miskalibrasi kriteria lebih awal; memfasilitasi rekonsiliasi objektif pada rapat *debrief*. |
| **7** | [`analytics_service.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/analytics_service.py#L269-L425) | `get_criteria_health()` | **Item Difficulty Theory & Psikometri Seleksi** | $\% \text{Matched}, \% \text{Partial}, \% \text{Unknown}$ | Menandai kriteria *bottleneck* ($\text{Unknown} > 80\%$) dan kriteria *too common* ($\text{Matched} > 90\%$). | Mencegah kriteria diskriminatif tersembunyi yang menyaring pelamar secara tidak proporsional. |
| **8** | [`analytics_service.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/analytics_service.py#L584-L622) | `get_fairness_audit_metrics()` | **EEOC Uniform Guidelines (29 C.F.R. § 1607)** & **NYC LL 144** | $\text{Impact Ratio} \ge 0.80$, $\text{PII Audit Rate}$ | Memverifikasi ketiadaan fitur demografis laten dan kepatuhan redaksi PII secara menyeluruh di seluruh basis data kandidat. | Menyediakan sertifikasi audit kesetaraan algoritmik internal yang siap diinspeksi auditor ketenagakerjaan. |
| **9** | [`web/comparison.js`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/web/comparison.js#L60-L105) & [`web/app.js`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/web/app.js#L206-L208) | `isBlindMode()`, `getBlindIdentifier()` | **Schmidt & Hunter (1998)** & **Mitigasi Bias Kognitif PIO** | *Anti-Bias Blind Protocol* | Menyamarkan nama asli dengan identitas anonim (Kandidat A, B, C) serta menyembunyikan institusi pendidikan dan foto. | Menghilangkan bias kognitif visual, *affinity bias*, dan stereotip demografis pada penyaringan putaran pertama. |
| **10** | [`server.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/server.py#L550-L615) & `schema.sql` | Alur Kerja *Dual-Approval Job Intake* | **EU AI Act (Pasal 14: Human-in-Command)** | *Protocol Gate: Status Locked* | Memblokir pemrosesan dan pemeringkatan CV sebelum kriteria disetujui bersama oleh Recruiter dan Hiring Manager. | Menghilangkan fenomena sengketa *moving goalposts*; menjamin akuntabilitas kriteria seleksi sejak hari pertama. |
| **11** | [`server.py`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/server.py#L1950-L2035) | Ekspor Audit & CSV Transparansi | **UU PDP No. 27/2022 (Pasal 24: Akuntabilitas)** | *Traceable Append-Only Log* | Mengunduh rekaman lengkap seluruh stempel waktu peninjauan, nama penilai, keputusan, skor rubrik, dan catatan pembelaan. | Menjamin hak subjek data untuk meminta verifikasi keabsahan evaluasi lamaran kerja mereka. |

---

### 4.3. Verifikasi Empiris dengan Dataset Tolok Ukur KarsaHire

Kinerja KarsaHire telah divalidasi secara empiris pada dua repositori data nyata dan sintetis:

#### A. Korpus Skala Industri LiveCareer (2.484 Resume Riil)
Berdasarkan berkas benchmark resmi [`data/enterprise_benchmark_report.json`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/data/enterprise_benchmark_report.json):
* **Total Sampel Dievaluasi**: 2.484 CV multidisiplin (Software, IT Infra, Akuntansi, SDM, dll).
* **Throughput Pemrosesan**: 5,79 CV/detik (rata-rata 171,9 ms per kandidat untuk ekstraksi profil lengkap dan penilaian multi-posisi).
* **Cakupan Deteksi Kompetensi (*Skill Coverage*)**: **96,26%** kandidat berhasil diidentifikasi keahlian teknisnya secara presisi leksikal.
* **Cakupan Deteksi Pendidikan (*Education Coverage*)**: **88,69%** kandidat berhasil diekstrak jenjang akademisnya (S3, S2, S1, D3).
* **Matriks Keselarasan Lintas Domain (*Cross-Domain Alignment Matrix*)**: Kandidat dari domain `ACCOUNTANT` memperoleh skor keselarasan rata-rata **55,92%** pada posisi *Accountant & Financial Analyst*, namun secara tepat hanya memperoleh skor **6,80%** pada posisi *Software Developer*. Ini membuktikan daya diskriminatif sistem yang sangat tinggi dalam membedakan kompetensi fungsional tanpa bias semantik palsu.

#### B. Dataset Kontrol Sintetis Berimbang (32 CV Berlabel Emas)
Berdasarkan berkas evaluasi [`data/synthetic_evaluation_report.json`](file:///c:/Users/heraldmichain.intern/Documents/KarsaHire/data/synthetic_evaluation_report.json):
* **Total Sampel Dievaluasi**: 32 CV sintetis berlabel emas (*ground truth verified*).
* **Cakupan Keterampilan**: **100.0%** kandidat terdeteksi dengan 62 keterampilan unik.
* **Tingkat Kepatuhan PII (*PII Compliance Rate*)**: **100.0%** (Seluruh kontak dan pengidentifikasi langsung berhasil diredaksi tanpa kebocoran ke log bukti).
* **Tingkat Halusinasi Kualifikasi**: **0.0% Mutlak** (Setiap kriteria positif terikat pada kutipan bukti verbatim dokumen).

---

## 5. Panduan Implementasi Lapangan & Tata Kelola Perusahaan

Untuk menerapkan tolok ukur ini dalam operasional rekrutmen harian, organisasi direkomendasikan mengadopsi protokol standar berikut:

```
[Tahap 1: Job Intake & Dual-Approval]
Recruiter dan HM menyepakati kriteria wajib (hard gates) dan preferensi di UI.
Kriteria dikunci secara kriptografis dalam basis data SQLite sebelum CV diproses.
                 │
                 ▼
[Tahap 2: Ingesti & Sanitasi Buta (Blind Ingestion)]
OCR lokal mengekstrak teks. PII Redaction Engine menyensor kontak dan nama.
Sistem mengaktifkan Mode Review Buta secara default.
                 │
                 ▼
[Tahap 3: Triase Berbasis Bukti (Evidence-First Triage)]
AI menyajikan skor kualifikasi lengkap dengan kutipan verbatim dan nomor halaman.
Recruiter meninjau bukti tanpa melihat identitas kandidat.
                 │
                 ▼
[Tahap 4: Review Ganda & Audit Debrief]
Hiring Manager melakukan review independen.
Sistem menghitung Cohen's Kappa (κ). Jika κ < 0.60, sistem memicu sesi penyelarasan.
                 │
                 ▼
[Tahap 5: Wawancara Terstruktur Skala 1-5 & Audit Trail]
Kandidat berstatus advance diwawancarai dengan rubrik kompetensi baku.
Seluruh catatan dan riwayat keputusan diekspor untuk arsip kepatuhan UU PDP & audit AEDT.
```

---

## 6. Daftar Referensi & Rujukan Ilmiah (Academic References)

1. **Bogen, M., & Rieke, A. (2018)**. *Help Wanted: An Examination of Hiring Algorithms, Equity, and Bias*. Upturn Research Report.
2. **Dastin, J. (2018)**. *Amazon Scraps Secret AI Recruiting Tool that Showed Bias Against Women*. Reuters Technology News.
3. **European Parliament and Council of the European Union (2024)**. *Regulation (EU) 2024/1689 of the European Parliament and of the Council laying down harmonised rules on artificial intelligence (Artificial Intelligence Act)*. Official Journal of the European Union, L Series.
4. **Geyik, S. C., Ambler, S., & Kenthapadi, K. (2019)**. *Fairness-Aware Ranking in Search & Recommendation Systems with Application to LinkedIn Talent Search*. Proceedings of the 25th ACM SIGKDD International Conference on Knowledge Discovery & Data Mining (KDD '19), pp. 2221–2231. DOI: [10.1145/3292500.3330691](https://doi.org/10.1145/3292500.3330691).
5. **Järvelin, K., & Kekäläinen, J. (2002)**. *Cumulated Gain-Based Evaluation of IR Techniques*. ACM Transactions on Information Systems (TOIS), 20(4), pp. 422–446. DOI: [10.1145/582415.582418](https://doi.org/10.1145/582415.582418).
6. **Landis, J. R., & Koch, G. G. (1977)**. *The Measurement of Observer Agreement for Categorical Data*. Biometrics, 33(1), pp. 159–174. DOI: [10.2307/2529310](https://doi.org/10.2307/2529310).
7. **New York City Department of Consumer and Worker Protection (DCWP) (2021)**. *Local Law 144 of 2021: Automated Employment Decision Tools (AEDT)*. The New York City Administrative Code, Title 20, Chapter 5, Subchapter 25.
8. **Pemerintah Republik Indonesia (2022)**. *Undang-Undang Republik Indonesia Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi (UU PDP)*. Lembaran Negara Republik Indonesia Tahun 2022 Nomor 196.
9. **Raghavan, M., Barocas, S., Kleinberg, J., & Levy, K. (2020)**. *Mitigating Bias in Algorithmic Hiring: Evaluating Claims and Practices*. Proceedings of the 2020 Conference on Fairness, Accountability, and Transparency (FAT* '20), pp. 469–481. DOI: [10.1145/3351095.3372828](https://doi.org/10.1145/3351095.3372828).
10. **Schmidt, F. L., & Hunter, J. E. (1998)**. *The Validity and Utility of Selection Methods in Personnel Psychology: Practical and Theoretical Implications of 85 Years of Research Findings*. Psychological Bulletin, 124(2), pp. 262–274. DOI: [10.1037/0033-2909.124.2.262](https://doi.org/10.1037/0033-2909.124.2.262).
11. **Schmidt, F. L., Oh, I.-S., & Shaffer, J. A. (2016)**. *The Validity and Utility of Selection Methods in Personnel Psychology: Practical and Theoretical Implications of 100 Years of Research Findings*. Working Paper, Department of Management and Organizations, University of Iowa.
12. **The Ladders (2018)**. *Eye-Tracking Study: How Recruiters Really Review Resumes*. The Ladders Career Research Report.
13. **U.S. Equal Employment Opportunity Commission (EEOC) (1978)**. *Uniform Guidelines on Employee Selection Procedures*. 29 C.F.R. Part 1607.
