const state = {
  jobs: [],
  activeJob: null,
  reviewer: "",
  loadingSynthetic: false,
  manualUploadsEnabled: false,
  candidateFilter: "all",
  searchQuery: "",
  candidateSort: "score_desc",
};
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const percentageFormatter = new Intl.NumberFormat("id-ID", {
  style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1,
});

function calculatePercentageShares(counts, total) {
  const portions = Object.entries(counts).map(([key, count], order) => {
    const exactUnits = (count * 1000) / total;
    const units = Math.floor(exactUnits);
    return { key, units, remainder: exactUnits - units, order };
  });
  let remaining = 1000 - portions.reduce((sum, portion) => sum + portion.units, 0);
  const byRemainder = [...portions].sort((left, right) =>
    right.remainder - left.remainder || left.order - right.order);
  for (let index = 0; index < remaining; index += 1) byRemainder[index].units += 1;
  return Object.fromEntries(portions.map(({ key, units }) => [key, units / 1000]));
}

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

async function api(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const requestOptions = { ...options, headers: { ...(options.headers || {}) } };
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    requestOptions.headers["X-KarsaHire-Request"] = "same-origin-ui";
  }
  const response = await fetch(url, requestOptions);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "Permintaan gagal.");
  return payload;
}

async function updateOcrIndicator() {
  const health = await api("/api/health");
  const indicator = $("#ocr-indicator");
  if (!indicator) return;
  if (health.ocr_backend === "paddle") {
    indicator.lastChild.textContent = health.ocr_configured ? " PaddleOCR lokal" : " PaddleOCR belum terpasang";
  } else {
    indicator.lastChild.textContent = health.ocr_configured ? " OCR melalui API internal" : " API OCR belum dikonfigurasi";
  }
}

let toastTimer;
function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 2800);
}

function parseCriteria(text) {
  return text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
    const match = line.match(/^(wajib|required|diutamakan|preferred)\s*[|:]\s*(.+)$/i);
    if (!match) throw new Error(`Format kriteria tidak dikenali: “${line}”. Gunakan “Wajib | ...” atau “Diutamakan | ...”.`);
    const type = /^(diutamakan|preferred)$/i.test(match[1]) ? "preferred" : "required";
    return { type, label: match[2].trim() };
  });
}

const ROLE_TEMPLATES = {
  "software-developer": {
    title: "Software Developer",
    department: "IT / Engineering",
    description: "Menganalisis kebutuhan, mengembangkan dan memelihara perangkat lunak, serta menguji perubahan bersama tim produk dan engineering. Sesuaikan bahasa pemrograman dan stack dengan posisi yang dibuka.",
    criteria: [
      ["required", "Programming"], ["required", "Software development"], ["required", "Git"],
      ["preferred", "REST API"], ["preferred", "SQL"], ["preferred", "Automated testing"],
    ],
  },
  "systems-administrator": {
    title: "Network & Systems Administrator",
    department: "IT / Infrastructure",
    description: "Mengelola jaringan, server, akses pengguna, pemantauan sistem, pencadangan, dan pemulihan layanan. Sesuaikan platform dan teknologi dengan lingkungan perusahaan.",
    criteria: [
      ["required", "Computer networking"], ["required", "Server administration"],
      ["required", "System monitoring"], ["required", "Backup and recovery"],
      ["preferred", "Linux"], ["preferred", "Windows Server"], ["preferred", "Cloud infrastructure"],
    ],
  },
  "cybersecurity-analyst": {
    title: "Cybersecurity Analyst",
    department: "IT / Information Security",
    description: "Memantau keamanan sistem, menilai kerentanan, menyelidiki alert atau insiden, dan mendokumentasikan mitigasi risiko.",
    criteria: [
      ["required", "Security monitoring"], ["required", "Vulnerability assessment"],
      ["required", "Incident response"], ["required", "Access control"],
      ["preferred", "SIEM"], ["preferred", "ISO 27001"], ["preferred", "NIST Cybersecurity Framework"],
    ],
  },
  recruiter: {
    title: "Recruiter / Talent Acquisition Specialist",
    department: "Human Resources",
    description: "Menerjemahkan kebutuhan posisi menjadi strategi pencarian kandidat, melakukan sourcing dan screening, mengoordinasikan wawancara, serta memberi pembaruan proses kepada kandidat dan hiring manager.",
    criteria: [
      ["required", "Candidate sourcing"], ["required", "Resume screening"],
      ["required", "Structured interviewing"], ["required", "Recruitment coordination"],
      ["preferred", "Applicant tracking system"], ["preferred", "Recruitment metrics"], ["preferred", "HRIS"],
    ],
  },
  "learning-development": {
    title: "Learning & Development Specialist",
    department: "Human Resources / Learning & Development",
    description: "Mengidentifikasi kebutuhan pelatihan, merancang materi dan program belajar, memfasilitasi sesi, lalu mengevaluasi efektivitasnya.",
    criteria: [
      ["required", "Training needs analysis"], ["required", "Instructional design"],
      ["required", "Training facilitation"], ["required", "Training evaluation"],
      ["preferred", "Learning management system"], ["preferred", "E-learning"],
    ],
  },
  "hr-manager": {
    title: "HR Manager",
    department: "Human Resources",
    description: "Memimpin operasi dan tim HR, menyelaraskan kebutuhan tenaga kerja, mengelola kebijakan dan hubungan karyawan, serta memberi masukan kepada pimpinan.",
    criteria: [
      ["required", "HR operations"], ["required", "Employee relations"],
      ["required", "Workforce planning"], ["required", "HR policy and compliance"],
      ["preferred", "Compensation and benefits"], ["preferred", "HR analytics"], ["preferred", "Labor relations"],
    ],
  },
  accountant: {
    title: "Accountant / Financial Reporting",
    department: "Finance / Accounting",
    description: "Menyiapkan dan memeriksa catatan serta laporan keuangan, rekonsiliasi akun, penutupan buku, pelaporan pajak, dan kontrol internal. Sesuaikan standar akuntansi dengan entitas dan kebutuhan perusahaan.",
    criteria: [
      ["required", "General ledger"], ["required", "Financial statements"],
      ["required", "Account reconciliation"], ["required", "Month-end close"],
      ["preferred", "Tax reporting"], ["preferred", "Internal controls"], ["preferred", "ERP"],
    ],
  },
  "accounting-clerk": {
    title: "Accounting Clerk (AP/AR)",
    department: "Finance / Accounting",
    description: "Mencatat transaksi dan dokumen keuangan, mengelola invoice utang/piutang, memeriksa ketepatan data, dan membantu rekonsiliasi.",
    criteria: [
      ["required", "Bookkeeping"], ["required", "Accounts payable"],
      ["required", "Accounts receivable"], ["required", "Invoice processing"],
      ["preferred", "Excel"], ["preferred", "Bank reconciliation"], ["preferred", "Accounting software"],
    ],
  },
  "payroll-specialist": {
    title: "Payroll Specialist / Timekeeping",
    department: "Finance / HR Operations",
    description: "Memeriksa absensi dan data payroll, menghitung upah serta potongan, memproses pembayaran, dan merekonsiliasi laporan periode. Sesuaikan aturan lokal dan sistem perusahaan.",
    criteria: [
      ["required", "Payroll processing"], ["required", "Timekeeping"],
      ["required", "Wage calculation"], ["required", "Payroll reconciliation"],
      ["preferred", "Payroll system"], ["preferred", "HRIS"], ["preferred", "Payroll reporting"],
    ],
  },
};

function applyRoleTemplate(key) {
  const hint = $("#template-hint");
  if (key === "custom") {
    hint.textContent = "Mode custom aktif. Semua field bisa diisi atau diedit sendiri.";
    return;
  }
  const template = ROLE_TEMPLATES[key];
  if (!template) {
    hint.textContent = "Template mengisi posisi, ringkasan, dan kriteria awal. Semua kolom tetap bisa disunting.";
    return;
  }
  $("#job-title").value = template.title;
  $("#department").value = template.department;
  $("#description").value = template.description;
  $("#criteria").value = template.criteria
    .map(([type, label]) => `${type === "required" ? "Wajib" : "Diutamakan"} | ${label}`)
    .join("\n");
  hint.textContent = `Template ${template.title} terisi. Edit stack, tingkat senioritas, dan kriteria agar sesuai lowongan ini.`;
}

function renderJobs() {
  const list = $("#jobs-list");
  if (!state.jobs.length) { list.innerHTML = ""; return; }
  list.innerHTML = `<h4>Lowongan aktif</h4>${state.jobs.map((job) => {
    const active = state.activeJob?.id === job.id;
    return `
    <button class="job-item ${active ? "active" : ""}" data-job-id="${escapeHtml(job.id)}" aria-current="${active ? "true" : "false"}">
      <span class="job-icon" aria-hidden="true">↗</span><span><strong>${escapeHtml(job.title)}</strong><small>${escapeHtml(job.department || "Tim belum diisi")} · ${job.candidate_count || 0} kandidat</small></span><span class="job-arrow" aria-hidden="true">›</span>
    </button>`;
  }).join("")}`;
}

function statusLabel(status) {
  return ({ needs_review: "Menunggu tinjauan", advance: "Lanjut proses", needs_info: "Perlu informasi", not_selected: "Tidak dilanjutkan" })[status] || status;
}

function candidateName(candidate, index) {
  if (window.ComparisonModule && window.ComparisonModule.isBlindMode()) {
    return window.ComparisonModule.getCandidateLabel(candidate, index);
  }
  return `Kandidat · ${candidate.id.slice(-4).toUpperCase()}`;
}

function matchesCandidateSearch(candidate, query) {
  if (!query) return true;
  const q = query.trim().toLowerCase();
  if (!q) return true;

  if (candidate.id.toLowerCase().includes(q)) return true;
  if (candidate.id.slice(-4).toLowerCase().includes(q)) return true;
  if (candidateName(candidate).toLowerCase().includes(q)) return true;

  const skills = candidate.profile?.skills || [];
  if (skills.some((skill) => skill.toLowerCase().includes(q))) return true;

  const edu = candidate.profile?.education_levels_mentioned || [];
  if (edu.some((item) => item.toLowerCase().includes(q))) return true;

  const exp = candidate.profile?.experience_years_mentioned;
  if (exp != null && (String(exp).includes(q) || `${exp} tahun`.toLowerCase().includes(q))) return true;

  if ((candidate.file_type || "").toLowerCase().includes(q)) return true;

  const evidence = candidate.evidence || [];
  if (evidence.some((e) =>
    (e.criterion && e.criterion.toLowerCase().includes(q)) ||
    (e.snippet && e.snippet.toLowerCase().includes(q))
  )) return true;

  if (statusLabel(candidate.status).toLowerCase().includes(q)) return true;

  const reviews = candidate.reviews || [];
  if (reviews.some((r) =>
    (r.reviewer && r.reviewer.toLowerCase().includes(q)) ||
    (r.note && r.note.toLowerCase().includes(q))
  )) return true;

  return false;
}

function sortCandidates(candidates, sortKey = "score_desc") {
  const list = [...candidates];
  switch (sortKey) {
    case "score_asc":
      list.sort((a, b) => a.score - b.score || (a.created_at || "").localeCompare(b.created_at || ""));
      break;
    case "date_desc":
      list.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || "") || b.score - a.score);
      break;
    case "date_asc":
      list.sort((a, b) => (a.created_at || "").localeCompare(b.created_at || "") || b.score - a.score);
      break;
    case "score_desc":
    default:
      list.sort((a, b) => b.score - a.score || (a.created_at || "").localeCompare(b.created_at || ""));
      break;
  }
  return list;
}

function renderEvidenceSummary(job) {
  const section = $("#evidence-summary");
  const candidates = job.candidates || [];
  const rows = candidates.flatMap((candidate) => candidate.evidence || []);
  const counts = { matched: 0, partial: 0, needs_verification: 0, unknown: 0 };
  rows.forEach((row) => {
    const key = Object.prototype.hasOwnProperty.call(counts, row.result) ? row.result : "unknown";
    counts[key] += 1;
  });
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  if (!total) {
    section.classList.add("hidden");
    $("#evidence-summary-bar").innerHTML = "";
    $("#evidence-summary-legend").innerHTML = "";
    return;
  }

  const statuses = [
    { key: "matched", label: "Ada bukti tekstual", className: "found" },
    { key: "partial", label: "Bukti parsial", className: "partial" },
    { key: "needs_verification", label: "Perlu verifikasi", className: "verify" },
    { key: "unknown", label: "Belum ditemukan", className: "unknown" },
  ];
  const shares = calculatePercentageShares(counts, total);
  section.classList.remove("hidden");
  $("#evidence-summary-total").textContent = `${total} pemeriksaan`;
  $("#evidence-summary-caption").textContent = `${total} pemeriksaan kriteria pada ${candidates.length} CV. Satu pemeriksaan berarti satu kriteria pada satu CV; persentase memakai seluruh pemeriksaan sebagai pembagi dan dibulatkan satu desimal agar jumlahnya 100,0%.`;
  $("#evidence-summary-bar").innerHTML = statuses.map(({ key, label, className }) => {
    const width = (counts[key] / total) * 100;
    return counts[key] ? `<span class="evidence-segment ${className}" style="width:${width}%" title="${label}: ${counts[key]}"></span>` : "";
  }).join("");
  $("#evidence-summary-legend").innerHTML = statuses.map(({ key, label, className }) => {
    const share = percentageFormatter.format(shares[key]);
    return `
    <li><span class="legend-swatch ${className}" aria-hidden="true"></span><span>${label}</span><strong>${counts[key]} <span class="legend-share">${share}</span></strong></li>`;
  }).join("");
}

function renderCandidates(job) {
  const container = $("#candidate-list");
  const candidates = job.candidates || [];
  const counts = candidates.reduce((result, candidate) => {
    result[candidate.status] = (result[candidate.status] || 0) + 1;
    return result;
  }, {});
  $("#candidate-count").textContent = candidates.length;
  $$("[data-filter-count]").forEach((node) => {
    const key = node.dataset.filterCount;
    node.textContent = key === "all" ? candidates.length : (counts[key] || 0);
  });
  $$(".candidate-filter").forEach((button) => {
    const selected = button.dataset.filter === state.candidateFilter;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });

  const exportCsvBtn = $("#export-csv-button");
  const exportJsonBtn = $("#export-json-button");
  const exportDossierBtn = $("#export-dossier-button");
  if (exportCsvBtn) exportCsvBtn.disabled = !candidates.length;
  if (exportJsonBtn) exportJsonBtn.disabled = !candidates.length;
  if (exportDossierBtn) exportDossierBtn.disabled = !job?.id;

  const filtered = candidates.filter((candidate) => {
    if (state.candidateFilter !== "all" && candidate.status !== state.candidateFilter) {
      return false;
    }
    return matchesCandidateSearch(candidate, state.searchQuery);
  });

  const visibleCandidates = sortCandidates(filtered, state.candidateSort);

  const summaryNode = $("#candidate-filter-summary");
  if (summaryNode) {
    const selectedFilter = $(`.candidate-filter[data-filter="${state.candidateFilter}"]`);
    const filterText = selectedFilter?.childNodes[0]?.textContent.trim() || state.candidateFilter;
    if (state.searchQuery && state.candidateFilter !== "all") {
      summaryNode.textContent = `Menampilkan ${visibleCandidates.length} dari ${candidates.length} kandidat (filter "${filterText}", cari "${state.searchQuery}")`;
    } else if (state.searchQuery) {
      summaryNode.textContent = `Menampilkan ${visibleCandidates.length} dari ${candidates.length} kandidat (cari "${state.searchQuery}")`;
    } else if (state.candidateFilter !== "all") {
      summaryNode.textContent = `Menampilkan ${visibleCandidates.length} dari ${candidates.length} kandidat`;
    } else {
      summaryNode.textContent = `Menampilkan ${candidates.length} kandidat`;
    }
  }

  const emptyState = $("#empty-candidates");
  emptyState.classList.toggle("hidden", visibleCandidates.length > 0);
  if (!candidates.length) {
    emptyState.querySelector("h3").textContent = "Belum ada kandidat";
    emptyState.querySelector("p").textContent = "Unggah CV PDF teks, DOCX, atau TXT untuk melihat bukti kecocokan per kriteria.";
  } else if (!visibleCandidates.length) {
    if (state.searchQuery) {
      emptyState.querySelector("h3").textContent = "Tidak ada kandidat yang cocok";
      emptyState.querySelector("p").textContent = `Tidak ada kandidat dengan ID atau skill/profil yang memuat “${escapeHtml(state.searchQuery)}”. Coba kata kunci lain atau bersihkan kotak pencarian.`;
    } else {
      const selectedFilter = $(`.candidate-filter[data-filter="${state.candidateFilter}"]`);
      const label = selectedFilter?.childNodes[0]?.textContent.trim() || "status ini";
      emptyState.querySelector("h3").textContent = `Belum ada kandidat: ${label}`;
      emptyState.querySelector("p").textContent = "Kandidat akan muncul di sini setelah status review-nya sesuai.";
    }
  }

  if (!visibleCandidates.length) {
    container.innerHTML = "";
    if (window.ComparisonModule) window.ComparisonModule.updateSelectionUI(job);
    return;
  }
  container.innerHTML = visibleCandidates.map((candidate, index) => {
    const score = Math.round(candidate.score);
    const isComparing = window.ComparisonModule?.isCandidateSelected(candidate.id) || false;
    const blindLabel = window.ComparisonModule?.getBlindIdentifier(candidate, index) || `Kandidat Anonim #${index + 1}`;
    const evidenceRows = candidate.evidence.map((row) => {
      const status = ({
        matched: { label: "Ada bukti tekstual", cls: "status-matched", signal: "Frasa ditemukan" },
        partial: { label: "Bukti parsial", cls: "status-partial", signal: "Kecocokan sebagian" },
        needs_verification: { label: "Perlu verifikasi", cls: "status-verification", signal: "Penyebutan ambigu atau negatif" },
        unknown: { label: "Belum ditemukan", cls: "status-unknown", signal: "Tidak ditemukan di teks" },
      })[row.result] || { label: "Belum ditemukan", cls: "status-unknown", signal: "Tidak ditemukan di teks" };
      const snippet = row.snippet
        ? `“${escapeHtml(row.snippet)}”`
        : row.result === "needs_verification"
          ? "Penyebutan ini perlu diperiksa reviewer."
          : "Belum ditemukan pada teks CV yang diproses.";
      const page = row.page_number ? `Hal. ${row.page_number}` : "Dokumen";
      return `<div class="evidence-item"><div class="evidence-criterion">${escapeHtml(row.criterion)}<div class="muted">${row.requirement_type === "required" ? "Wajib · bobot 2" : "Diutamakan · bobot 1"}</div></div><div class="evidence-snippet">${snippet}</div><div><span class="evidence-status ${status.cls}">${status.label}</span><div class="evidence-page">${page} · ${status.signal}</div></div></div>`;
    }).join("");
    const skills = candidate.profile.skills || [];
    const tags = skills.length ? skills.slice(0, 10).map((skill) => `<span class="tag">${escapeHtml(skill)}</span>`).join("") : `<span class="tag">Skill belum terdeteksi</span>`;
    const experience = candidate.profile.experience_duration_text
      ? `Pengalaman disebut: ${candidate.profile.experience_duration_text}`
      : candidate.profile.experience_years_mentioned == null
        ? "Pengalaman: belum diketahui"
        : `Pengalaman disebut: ${candidate.profile.experience_years_mentioned} tahun`;
    const educationMentions = candidate.profile.education_levels_mentioned || [];
    const education = educationMentions.length
      ? `Pendidikan: ${educationMentions.join(", ")}`
      : "Pendidikan: belum diketahui";
    const reviews = candidate.reviews.length ? `<div class="review-history">${candidate.reviews.map((review) => `<div><strong>${escapeHtml(review.reviewer)}</strong> · ${review.role === "recruiter" ? "Recruiter" : "Hiring manager"}: ${escapeHtml(statusLabel(review.decision))}${review.note ? ` — ${escapeHtml(review.note)}` : ""}</div>`).join("")}</div>` : "";
    return `<article class="candidate-card ${isComparing ? "comparing" : ""}" data-candidate-id="${escapeHtml(candidate.id)}">
      <div class="candidate-main">
        <label class="candidate-select-wrapper" title="Pilih kandidat untuk perbandingan (maks 3)">
          <input type="checkbox" class="candidate-select-check" data-candidate-id="${escapeHtml(candidate.id)}" ${isComparing ? "checked" : ""}>
        </label>
        <div class="candidate-avatar">${String(index + 1).padStart(2, "0")}</div>
        <div class="candidate-info">
          <div class="candidate-name">
            <span class="candidate-real-name">${candidateName(candidate, index)}</span>
            <span class="candidate-blind-name">${escapeHtml(blindLabel)}</span>
            <span class="tag">${escapeHtml(statusLabel(candidate.status))}</span>
          </div>
          <div class="candidate-meta">${escapeHtml(experience)} · ${escapeHtml(education)} · <span class="candidate-file-meta">CV ${escapeHtml(candidate.file_type.toUpperCase())}</span><span class="file-label-blind">CV Terstandarisasi</span></div>
        </div>
        <div class="score-block"><div class="score-number">${score}<small>/100</small></div><div class="score-label" title="Persentase berbobot dari kecocokan frasa dan token pada teks CV; bukan penilaian kelayakan.">indikator evidence</div><div class="score-track" role="meter" aria-label="Cakupan bukti tekstual" aria-valuenow="${score}" aria-valuemin="0" aria-valuemax="100"><div class="score-fill" style="width:${Math.max(0, Math.min(100, score))}%"></div></div></div>
      </div>
      <div class="candidate-actions">
        <button class="candidate-expand" type="button" aria-label="Buka bukti dan catat tinjauan untuk ${escapeHtml(candidateName(candidate, index))}" aria-expanded="false" aria-controls="candidate-details-${escapeHtml(candidate.id)}"><span class="chev" aria-hidden="true">⌄</span> Buka evidence dan catat review manusia</button>
        <button class="button button-secondary candidate-feedback-btn" type="button" data-candidate-id="${escapeHtml(candidate.id)}" title="Buka umpan balik transparan &amp; draft email untuk kandidat ini">
          <span class="btn-icon">✉️</span> Umpan Balik Kandidat
        </button>
        <button class="candidate-delete" type="button" data-candidate-id="${escapeHtml(candidate.id)}" aria-label="Hapus ${escapeHtml(candidateName(candidate, index))} beserta bukti dan tinjauannya">Hapus kandidat</button>
      </div>
      <div class="candidate-details" id="candidate-details-${escapeHtml(candidate.id)}"><div class="candidate-detail-actions"><span class="review-hint">Data profil, evidence, dan review dapat dihapus dari antrean.</span></div><div class="profile-tags">${tags}</div><div class="evidence-list">${evidenceRows}</div>
        <form class="review-form" data-candidate-id="${escapeHtml(candidate.id)}">
          <div class="review-grid"><input name="reviewer" aria-label="Nama reviewer" placeholder="Nama reviewer" required maxlength="100" value="${escapeHtml(state.reviewer)}"><select name="role" aria-label="Peran reviewer"><option value="recruiter">Recruiter</option><option value="hiring_manager">Hiring manager</option></select><select name="decision" aria-label="Keputusan reviewer"><option value="advance">Lanjut proses</option><option value="needs_info">Perlu informasi</option><option value="not_selected">Tidak lanjut</option></select></div>
          <label class="visually-hidden" for="review-note-${escapeHtml(candidate.id)}">Catatan berbasis kriteria/evidence (opsional)</label><textarea id="review-note-${escapeHtml(candidate.id)}" name="note" placeholder="Catatan berbasis kriteria/evidence (opsional)" maxlength="2000"></textarea><div class="review-actions"><span class="review-hint">Keputusan ini dicatat sebagai review manusia.</span><button class="button button-secondary candidate-feedback-btn" type="button" data-candidate-id="${escapeHtml(candidate.id)}" title="Lihat umpan balik transparan dan draft email"><span class="btn-icon">✉️</span> Umpan Balik Kandidat</button><button class="button button-secondary" type="submit">Simpan review</button></div>
        </form>${reviews}
        <section class="candidate-scorecard-section" data-candidate-id="${escapeHtml(candidate.id)}" id="scorecard-section-${escapeHtml(candidate.id)}">
          <div class="scorecard-section-header">
            <div class="scorecard-title-group">
              <span class="scorecard-icon">📋</span>
              <div>
                <h4 class="scorecard-heading">Scorecard Wawancara Terstruktur</h4>
                <p class="scorecard-subheading">Rubrik penilaian objektif skala 1–5 &amp; konsensus Recruiter vs Hiring Manager</p>
              </div>
            </div>
            <div class="scorecard-header-actions">
              <button class="button button-secondary star-guide-btn" type="button" data-candidate-id="${escapeHtml(candidate.id)}" title="Buka panduan pertanyaan wawancara perilaku STAR per kriteria">
                <span class="btn-icon">🎯</span> Panduan Wawancara STAR
              </button>
              <button class="scorecard-toggle-form-btn" type="button" data-candidate-id="${escapeHtml(candidate.id)}">
                <span class="btn-icon">✏️</span> Isi Scorecard
              </button>
            </div>
          </div>
          <div class="scorecard-body" id="scorecard-body-${escapeHtml(candidate.id)}" data-candidate-id="${escapeHtml(candidate.id)}">
            <div class="scorecard-loading"><span class="scorecard-spinner"></span> Memuat scorecard wawancara…</div>
          </div>
        </section></div>
    </article>`;
  }).join("");
  if (window.ScorecardModule) {
    visibleCandidates.forEach((candidate) => {
      window.ScorecardModule.loadForCandidate(candidate.id);
    });
  }
  if (window.ComparisonModule) {
    window.ComparisonModule.updateSelectionUI(job);
  }
}

function focusCandidateToggle(candidateId, expand = false) {
  const card = $$(".candidate-card").find((item) => item.dataset.candidateId === candidateId);
  const toggle = card?.querySelector(".candidate-expand");
  if (!toggle) return false;
  if (expand && toggle.getAttribute("aria-expanded") !== "true") toggle.click();
  toggle.focus();
  return true;
}

function focusUploadControl() {
  const synthetic = $("#load-synthetic-button");
  (synthetic && !synthetic.disabled ? synthetic : $("#upload-label"))?.focus();
}

function renderActivity(events) {
  const node = $("#activity-list");
  if (!events.length) { node.innerHTML = `<p class="muted">Aktivitas akan muncul setelah tinjauan dicatat.</p>`; return; }
  const labels = { criteria_submitted: "Kriteria lowongan diajukan", criteria_approval_recorded: "Persetujuan kriteria dicatat", candidate_parsed: "CV diproses dan bukti dibuat", synthetic_dataset_loaded: "Dataset CV sintetis dimuat", human_review_recorded: "Tinjauan manusia dicatat", candidate_deleted: "Data kandidat dihapus" };
  node.innerHTML = events.slice(0, 8).map((event) => `<div class="activity-item"><span class="activity-dot"></span><div>${escapeHtml(labels[event.event_type] || event.event_type)}<small>${escapeHtml(event.actor)} · ${new Date(event.created_at).toLocaleString("id-ID")}</small></div></div>`).join("");
}

async function loadJobs(preferredId = state.activeJob?.id) {
  const [jobs, health] = await Promise.all([api("/api/jobs"), api("/api/health")]);
  state.jobs = jobs;
  state.manualUploadsEnabled = health.manual_uploads_enabled === true;
  renderJobs();
  const chosen = state.jobs.find((job) => job.id === preferredId) || state.jobs[0];
  if (chosen) await selectJob(chosen.id);
  else {
    state.activeJob = null;
    $("#active-workspace").classList.add("hidden");
    $("#setup-state").classList.remove("hidden");
    $("#active-title").textContent = "Belum ada lowongan";
    $("#active-subtitle").textContent = "Buat lowongan atau muat contoh sintetis untuk memulai.";
    $("#pipeline-chip").innerHTML = `<span class="pulse"></span> Persiapan`;
  }
}

async function selectJob(jobId) {
  state.activeJob = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
  if (window.ComparisonModule) window.ComparisonModule.clearSelection();
  state.searchQuery = "";
  state.candidateSort = "score_desc";
  state.candidateFilter = "all";
  const searchInput = $("#candidate-search");
  if (searchInput) searchInput.value = "";
  const searchClear = $("#candidate-search-clear");
  if (searchClear) searchClear.classList.add("hidden");
  const sortSelect = $("#candidate-sort");
  if (sortSelect) sortSelect.value = "score_desc";
  $("#active-title").textContent = state.activeJob.title;
  const approved = state.activeJob.status === "criteria_approved";
  $("#active-subtitle").textContent = `${state.activeJob.department || "Tim belum diisi"} · ${state.activeJob.criteria.length} kriteria · ${approved ? "disetujui perekrut dan manajer perekrutan" : "menunggu persetujuan"}`;
  $("#active-workspace").classList.remove("hidden");
  $("#setup-state").classList.add("hidden");
  const criteriaStep = $('[data-workflow-step="criteria"]');
  const reviewStep = $('[data-workflow-step="review"]');
  criteriaStep.classList.toggle("complete", approved);
  criteriaStep.classList.toggle("active", !approved);
  reviewStep.classList.toggle("active", approved);
  criteriaStep.querySelector("b").textContent = approved ? "✓" : "1";
  if (approved) {
    criteriaStep.removeAttribute("aria-current");
    reviewStep.setAttribute("aria-current", "step");
  }
  else {
    criteriaStep.setAttribute("aria-current", "step");
    reviewStep.removeAttribute("aria-current");
  }
  $("#pipeline-chip").innerHTML = `<span class="pulse"></span> ${approved ? "Siap ditinjau" : "Menunggu persetujuan"}`;
  renderApprovals(state.activeJob);
  renderSyntheticLoader(state.activeJob);
  const uploadButton = $("#upload-label");
  const canUploadManually = approved && state.manualUploadsEnabled;
  $("#resume-file").disabled = !canUploadManually;
  uploadButton.disabled = !canUploadManually;
  uploadButton.textContent = "＋ Tambah CV";
  $("#manual-upload-help").textContent = state.manualUploadsEnabled
    ? "Gunakan hanya CV sintetis yang diizinkan untuk pengujian lokal."
    : "Unggah CV manual dinonaktifkan. Gunakan fixture atau dataset CV sintetis lokal.";
  uploadButton.setAttribute("aria-describedby", "manual-upload-help");
  uploadButton.title = state.manualUploadsEnabled
    ? (approved ? "Unggah hanya CV sintetis yang diizinkan untuk pengujian lokal." : "Kriteria harus disetujui perekrut dan manajer perekrutan terlebih dahulu.")
    : "Unggah file dinonaktifkan. Gunakan fixture atau dataset CV sintetis lokal.";
  renderCandidates(state.activeJob);
  renderEvidenceSummary(state.activeJob);
  renderJobs();
  renderActivity(await api(`/api/jobs/${encodeURIComponent(jobId)}/events`));
}

function renderSyntheticLoader(job) {
  const button = $("#load-synthetic-button");
  const dataset = job?.synthetic_data || { available: 0, loaded: 0 };
  const available = Number(dataset.available) || 0;
  const loaded = Number(dataset.loaded) || 0;
  button.textContent = available ? `Muat CV uji (${loaded}/${available})` : "Dataset uji belum tersedia";
  button.disabled = !job || job.status !== "criteria_approved" || !available || loaded >= available || state.loadingSynthetic;
  button.title = job?.status !== "criteria_approved"
    ? "Kriteria harus disetujui perekrut dan manajer perekrutan terlebih dahulu."
    : available ? "Impor teks CV sintetis dari dataset lokal; tanpa OCR." : "Salin dataset ke data/synthetic-cv-32 terlebih dahulu.";
}

function renderApprovals(job) {
  const roles = [
    ["recruiter", "Perekrut"],
    ["hiring_manager", "Manajer perekrutan"],
  ];
  const approvals = job.approvals || [];
  $("#approval-status").innerHTML = roles.map(([role, label]) => {
    const approval = approvals.find((item) => item.role === role);
    return `<span class="approval-person ${approval ? "approved" : "pending"}"><b>${approval ? "✓" : "○"}</b>${label}${approval ? ` · ${escapeHtml(approval.reviewer)}` : " · menunggu"}</span>`;
  }).join("");
  const form = $("#approval-form");
  form.classList.toggle("hidden", job.status === "criteria_approved");
  if (job.status !== "criteria_approved") {
    const approvedRoles = new Set(approvals.map((item) => item.role));
    form.elements.role.querySelectorAll("option").forEach((option) => {
      option.disabled = approvedRoles.has(option.value);
    });
    const nextRole = roles.find(([role]) => !approvedRoles.has(role))?.[0];
    if (nextRole && approvedRoles.has(form.elements.role.value)) form.elements.role.value = nextRole;
    form.querySelector("button").disabled = !nextRole || approvedRoles.has(form.elements.role.value);
  }
}

async function createJob(data) {
  const created = await api("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  await loadJobs(created.id);
  return created;
}

async function uploadFile(file) {
  if (!state.activeJob) return toast("Buat atau pilih lowongan lebih dulu.");
  if (!file) return;
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    const result = await api(`/api/jobs/${encodeURIComponent(state.activeJob.id)}/candidates`, { method: "POST", body: form });
    state.reviewer ||= "";
    toast("CV diproses. Periksa bukti sebelum meninjau.");
    await loadJobs(state.activeJob.id);
    focusCandidateToggle(result.id, true);
  } catch (error) { toast(error.message); }
  finally { $("#resume-file").value = ""; }
}

async function loadSyntheticData() {
  if (!state.activeJob || state.loadingSynthetic) return;
  const jobId = state.activeJob.id;
  const existingIds = new Set((state.activeJob.candidates || []).map((candidate) => candidate.id));
  state.loadingSynthetic = true;
  renderSyntheticLoader(state.activeJob);
  try {
    const result = await api(`/api/jobs/${encodeURIComponent(jobId)}/load-synthetic-data`, { method: "POST" });
    toast(result.message);
    await loadJobs(jobId);
    const firstAdded = state.activeJob.candidates.find((candidate) => !existingIds.has(candidate.id));
    if (firstAdded) focusCandidateToggle(firstAdded.id, true);
  } catch (error) { toast(error.message); }
  finally {
    state.loadingSynthetic = false;
    renderSyntheticLoader(state.activeJob);
  }
}

$("#job-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formElement = event.currentTarget;
  const form = new FormData(formElement);
  const titleField = $("#job-title");
  const titleError = $("#job-title-error");
  const criteriaField = $("#criteria");
  const criteriaError = $("#criteria-error");
  titleError.textContent = "";
  titleField.removeAttribute("aria-invalid");
  criteriaError.textContent = "";
  criteriaField.removeAttribute("aria-invalid");
  const title = String(form.get("title") || "").trim();
  if (!title) {
    titleError.textContent = "Masukkan nama posisi.";
    titleField.setAttribute("aria-invalid", "true");
    titleField.focus();
    return;
  }
  let criteria;
  try {
    criteria = parseCriteria(form.get("criteria"));
    if (!criteria.length) throw new Error("Masukkan minimal satu kriteria yang disetujui.");
  } catch (error) {
    criteriaError.textContent = error.message;
    criteriaField.setAttribute("aria-invalid", "true");
    criteriaField.focus();
    return;
  }
  try {
    await createJob({ title, department: form.get("department"), description: form.get("description"), criteria });
    toast("Lowongan tersimpan. Kriteria tercatat di riwayat aktivitas.");
    formElement.reset();
    $("#approval-form [name='reviewer']")?.focus();
  } catch (error) { toast(error.message); }
});

$("#role-template")?.addEventListener("change", (event) => {
  applyRoleTemplate(event.currentTarget.value);
});

$("#job-title").addEventListener("input", () => {
  const field = $("#job-title");
  if (field.getAttribute("aria-invalid") !== "true") return;
  field.removeAttribute("aria-invalid");
  $("#job-title-error").textContent = "";
});

$("#criteria").addEventListener("input", () => {
  const field = $("#criteria");
  if (field.getAttribute("aria-invalid") !== "true") return;
  field.removeAttribute("aria-invalid");
  $("#criteria-error").textContent = "";
});

$("#fill-example").addEventListener("click", () => {
  if ($("#role-template")) {
    $("#role-template").value = "custom";
    applyRoleTemplate("custom");
  }
  const titleField = $("#job-title");
  titleField.value = "Backend Engineer";
  titleField.removeAttribute("aria-invalid");
  $("#job-title-error").textContent = "";
  $("#department").value = "Platform Engineering";
  $("#description").value = "Membangun API yang aman dan andal. Berkolaborasi dengan product, data, dan infrastructure untuk merilis layanan yang terukur.";
  const criteriaField = $("#criteria");
  criteriaField.value = "Wajib | Python\nWajib | FastAPI\nWajib | PostgreSQL\nDiutamakan | Docker\nDiutamakan | Cross-functional collaboration";
  criteriaField.removeAttribute("aria-invalid");
  $("#criteria-error").textContent = "";
});

$("#demo-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const job = await createJob({
      title: "Backend Engineer · Demo", department: "Platform Engineering",
      description: "Membangun API yang aman dan andal. Berkolaborasi dengan product, data, dan infrastructure untuk merilis layanan yang terukur.",
      criteria: [
        { type: "required", label: "Python" }, { type: "required", label: "FastAPI" },
        { type: "required", label: "PostgreSQL" }, { type: "preferred", label: "Docker" },
        { type: "preferred", label: "Cross-functional collaboration" },
      ],
    });
    await api(`/api/jobs/${encodeURIComponent(job.id)}/approvals`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer: "Recruiter Demo", role: "recruiter" }),
    });
    await api(`/api/jobs/${encodeURIComponent(job.id)}/approvals`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer: "Hiring Manager Demo", role: "hiring_manager" }),
    });
    await loadJobs(job.id);
    const result = await api(`/api/jobs/${encodeURIComponent(job.id)}/load-demo-candidate`, { method: "POST" });
    await loadJobs(job.id);
    if (result.id) focusCandidateToggle(result.id, true);
    toast("Contoh sintetis siap ditinjau.");
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; }
});

$("#jobs-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-job-id]");
  if (!button) return;
  const jobId = button.dataset.jobId;
  try {
    await selectJob(jobId);
    $$("#jobs-list [data-job-id]").find((item) => item.dataset.jobId === jobId)?.focus();
  }
  catch (error) { toast(error.message); }
});

$("#approval-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeJob) return;
  const data = new FormData(event.currentTarget);
  const jobId = state.activeJob.id;
  try {
    await api(`/api/jobs/${encodeURIComponent(jobId)}/approvals`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer: data.get("reviewer"), role: data.get("role") }),
    });
    toast("Persetujuan dicatat.");
    await loadJobs(jobId);
    if ($("#approval-form").classList.contains("hidden")) focusUploadControl();
    else $("#approval-form [name='reviewer']")?.focus();
  } catch (error) { toast(error.message); }
});

$("#upload-label").addEventListener("click", () => {
  if (!$("#upload-label").disabled) $("#resume-file").click();
});
$("#resume-file").addEventListener("change", (event) => uploadFile(event.target.files?.[0]));
$("#load-synthetic-button").addEventListener("click", loadSyntheticData);

$("#candidate-filters").addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter]");
  if (!button || !state.activeJob) return;
  state.candidateFilter = button.dataset.filter;
  renderCandidates(state.activeJob);
});

$("#candidate-list").addEventListener("click", (event) => {
  const remove = event.target.closest(".candidate-delete");
  if (remove) {
    const card = remove.closest(".candidate-card");
    const candidateId = card?.dataset.candidateId;
    if (!candidateId || !state.activeJob) return;
    const candidateIndex = $$(".candidate-card").indexOf(card);
    if (!window.confirm("Hapus kandidat ini beserta bukti, tinjauan, dan riwayat aktivitas yang terhubung dari database aktif? Catatan umum penghapusan tanpa ID kandidat tetap disimpan pada lowongan. Salinan backup yang dibuat sebelumnya tidak ikut terhapus.")) return;
    remove.disabled = true;
    api(`/api/candidates/${encodeURIComponent(candidateId)}`, { method: "DELETE" })
      .then(async () => {
        await loadJobs(state.activeJob.id);
        const candidates = state.activeJob?.candidates || [];
        toast(`Kandidat, bukti, dan tinjauannya dihapus. ${candidates.length} kandidat tersisa.`);
        const nextIndex = Math.min(candidateIndex, candidates.length - 1);
        const nextCandidate = candidates[nextIndex];
        if (!nextCandidate || !focusCandidateToggle(nextCandidate.id)) $("#candidate-heading")?.focus();
      })
      .catch((error) => {
        toast(error.message);
        remove.disabled = false;
      });
    return;
  }
  const toggle = event.target.closest(".candidate-expand");
  if (toggle) {
    const card = toggle.closest(".candidate-card");
    const expanded = toggle.getAttribute("aria-expanded") !== "true";
    card.classList.toggle("open", expanded);
    toggle.setAttribute("aria-expanded", String(expanded));
    if (expanded && window.ScorecardModule) {
      window.ScorecardModule.loadForCandidate(card.dataset.candidateId);
    }
  }
});

$("#candidate-list").addEventListener("change", (event) => {
  const check = event.target.closest(".candidate-select-check");
  if (check && window.ComparisonModule && state.activeJob) {
    const candidateId = check.dataset.candidateId;
    window.ComparisonModule.toggleCandidateSelection(candidateId, state.activeJob);
  }
});

async function deleteCandidate(button) {
  const candidateId = button.dataset.candidateId;
  const candidate = state.activeJob?.candidates?.find((item) => item.id === candidateId);
  if (!candidate) return toast("Kandidat tidak ditemukan di requisition ini.");
  const label = candidateName(candidate);
  const confirmed = window.confirm(`Hapus ${label}? Profil, evidence, dan review kandidat akan dihapus. Event penghapusan tetap tercatat di audit trail.`);
  if (!confirmed) return;
  button.disabled = true;
  try {
    await api(`/api/candidates/${encodeURIComponent(candidateId)}`, { method: "DELETE" });
    toast(`${label} dihapus dari antrean.`);
    await loadJobs(state.activeJob.id);
  } catch (error) {
    button.disabled = false;
    toast(error.message);
  }
}

$("#candidate-list").addEventListener("submit", async (event) => {
  const form = event.target.closest(".review-form");
  if (!form) return;
  event.preventDefault();
  const data = new FormData(form);
  const candidateId = form.dataset.candidateId;
  state.reviewer = data.get("reviewer");
  try {
    await api(`/api/candidates/${encodeURIComponent(form.dataset.candidateId)}/reviews`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer: data.get("reviewer"), role: data.get("role"), decision: data.get("decision"), note: data.get("note") }),
    });
    toast("Tinjauan manusia tersimpan.");
    await loadJobs(state.activeJob.id);
    focusCandidateToggle(candidateId, true);
  } catch (error) { toast(error.message); }
});

$("#ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeJob) return;
  const question = $("#question").value.trim();
  if (!question) return;
  $("#ask-result").textContent = "Mencari sumber lowongan…";
  try {
    const result = await api(`/api/jobs/${encodeURIComponent(state.activeJob.id)}/ask`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
    });
    $("#ask-result").innerHTML = `${escapeHtml(result.answer)}${result.sources.length ? result.sources.map((source) => `<div class="ask-source"><strong>${escapeHtml(source.source)}</strong>${escapeHtml(source.text)}</div>`).join("") : `<div class="ask-source">Tidak ditemukan dalam deskripsi atau kriteria lowongan yang tersimpan.</div>`}`;
  } catch (error) { $("#ask-result").textContent = error.message; }
});

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 100);
}

function generateClientCsv(job) {
  const candidates = job.candidates || [];
  const statusMap = {
    needs_review: "Perlu review",
    advance: "Lanjut proses",
    needs_info: "Perlu informasi",
    not_selected: "Tidak lanjut",
  };
  const headers = [
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
  ];
  const rows = [headers];
  for (const c of candidates) {
    const matched = (c.evidence || []).filter((e) => e.result === "matched").length;
    const partial = (c.evidence || []).filter((e) => e.result === "partial").length;
    const unknown = (c.evidence || []).filter((e) => e.result === "unknown").length;
    const lastRev = (c.reviews || [])[0];
    const skills = (c.profile?.skills || []).join(", ");
    const edu = (c.profile?.education_levels_mentioned || []).join(", ");
    const exp = c.profile?.experience_years_mentioned != null ? String(c.profile.experience_years_mentioned) : "-";
    const statusText = statusMap[c.status] || c.status;
    const revDecision = lastRev ? (statusMap[lastRev.decision] || lastRev.decision) : "-";
    rows.push([
      c.id,
      candidateName(c),
      String(Math.round(c.score)),
      statusText,
      (c.file_type || "").toUpperCase(),
      exp,
      edu,
      skills,
      String(matched),
      String(partial),
      String(unknown),
      lastRev?.reviewer || "-",
      lastRev?.role || "-",
      revDecision,
      lastRev?.note || "",
      c.created_at || "",
    ]);
  }
  const csvContent = "\ufeff" + rows.map((r) => r.map((val) => `"${String(val).replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const safeSlug = (job.title || "job").replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 30);
  downloadBlob(blob, `rekap-kandidat-${safeSlug}-${job.id.slice(0, 8)}.csv`);
}

function generateClientJson(job) {
  const payload = {
    job_id: job.id,
    title: job.title,
    department: job.department,
    description: job.description,
    criteria: job.criteria || [],
    approvals: job.approvals || [],
    exported_at: new Date().toISOString(),
    candidate_count: (job.candidates || []).length,
    candidates: job.candidates || [],
  };
  const jsonContent = JSON.stringify(payload, null, 2);
  const blob = new Blob([jsonContent], { type: "application/json;charset=utf-8;" });
  const safeSlug = (job.title || "job").replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 30);
  downloadBlob(blob, `debrief-kandidat-${safeSlug}-${job.id.slice(0, 8)}.json`);
}

async function exportCandidatesCsv() {
  if (!state.activeJob) return toast("Pilih requisition lebih dulu.");
  const job = state.activeJob;
  const button = $("#export-csv-button");
  if (button) button.disabled = true;
  try {
    const res = await fetch(`/api/jobs/${encodeURIComponent(job.id)}/export/csv`);
    if (res.ok) {
      const blob = await res.blob();
      const safeSlug = (job.title || "job").replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 30);
      downloadBlob(blob, `rekap-kandidat-${safeSlug}-${job.id.slice(0, 8)}.csv`);
      toast("Rekap CSV berhasil diunduh.");
      return;
    }
    generateClientCsv(job);
    toast("Rekap CSV berhasil dibuat dan diunduh.");
  } catch (err) {
    generateClientCsv(job);
    toast("Rekap CSV berhasil dibuat dan diunduh.");
  } finally {
    if (button) button.disabled = false;
  }
}

async function exportCandidatesJson() {
  if (!state.activeJob) return toast("Pilih requisition lebih dulu.");
  const job = state.activeJob;
  const button = $("#export-json-button");
  if (button) button.disabled = true;
  try {
    const res = await fetch(`/api/jobs/${encodeURIComponent(job.id)}/export/json`);
    if (res.ok) {
      const blob = await res.blob();
      const safeSlug = (job.title || "job").replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 30);
      downloadBlob(blob, `debrief-kandidat-${safeSlug}-${job.id.slice(0, 8)}.json`);
      toast("Debrief JSON berhasil diunduh.");
      return;
    }
    generateClientJson(job);
    toast("Debrief JSON berhasil dibuat dan diunduh.");
  } catch (err) {
    generateClientJson(job);
    toast("Debrief JSON berhasil dibuat dan diunduh.");
  } finally {
    if (button) button.disabled = false;
  }
}

$("#export-csv-button")?.addEventListener("click", exportCandidatesCsv);
$("#export-json-button")?.addEventListener("click", exportCandidatesJson);
$("#export-dossier-button")?.addEventListener("click", () => {
  const job = state.activeJob;
  if (!job?.id) {
    toast("Pilih requisition terlebih dahulu.");
    return;
  }
  window.open(`/api/jobs/${encodeURIComponent(job.id)}/export/dossier`, "_blank");
});
$("#analytics-button")?.addEventListener("click", () => {
  if (!state.activeJob?.id) {
    toast("Pilih requisition lebih dulu.");
    return;
  }
  if (window.AnalyticsModal) {
    window.AnalyticsModal.open(state.activeJob.id);
  }
});

$("#candidate-search")?.addEventListener("input", (event) => {
  state.searchQuery = event.target.value;
  const clearBtn = $("#candidate-search-clear");
  if (clearBtn) clearBtn.classList.toggle("hidden", !state.searchQuery);
  if (state.activeJob) renderCandidates(state.activeJob);
});

$("#candidate-search-clear")?.addEventListener("click", () => {
  state.searchQuery = "";
  const input = $("#candidate-search");
  if (input) {
    input.value = "";
    input.focus();
  }
  const clearBtn = $("#candidate-search-clear");
  if (clearBtn) clearBtn.classList.add("hidden");
  if (state.activeJob) renderCandidates(state.activeJob);
});

$("#candidate-sort")?.addEventListener("change", (event) => {
  state.candidateSort = event.target.value;
  if (state.activeJob) renderCandidates(state.activeJob);
});

/* --------------------------------------------------------------------------
   Candidate Feedback Modal & PDP Transparency Logic
   -------------------------------------------------------------------------- */
async function copyToClipboard(text, successMsg = "Berhasil disalin ke clipboard.") {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    toast(successMsg);
  } catch (err) {
    toast("Gagal menyalin: " + err.message);
  }
}

function closeFeedbackModal() {
  const backdrop = $("#feedback-modal-backdrop");
  if (backdrop) backdrop.classList.add("hidden");
  document.body.classList.remove("feedback-modal-open");
}

function generateClientCandidateFeedback(candidate, job) {
  const candId = candidate.id;
  const isBlind = window.ComparisonModule?.isBlindMode() || false;
  const candIndex = (job.candidates || []).indexOf(candidate);
  const candLabel = isBlind
    ? (window.ComparisonModule?.getBlindIdentifier(candidate, candIndex) || `Kandidat Anonim #${candIndex + 1}`)
    : candidateName(candidate, candIndex);

  const evidence = candidate.evidence || [];
  const strengths = [];
  const growthAreas = [];

  evidence.forEach((e) => {
    const isRequired = e.requirement_type === "required";
    const reqBadge = isRequired ? "Wajib" : "Diutamakan";
    if (e.result === "matched" || e.result === "partial") {
      strengths.push({
        criterion_id: e.criterion_id || e.criterion,
        criterion: e.criterion,
        requirement_type: e.requirement_type,
        weight: e.weight || (isRequired ? 2.0 : 1.0),
        result: e.result,
        snippet: e.snippet || "Bukti kualifikasi teridentifikasi pada teks CV.",
        explanation: e.result === "matched"
          ? `Kandidat menunjukkan bukti kuat untuk kualifikasi ${reqBadge} (${e.criterion}).`
          : `Kandidat memiliki keselarasan awal untuk kualifikasi ${reqBadge} (${e.criterion}), namun disarankan untuk verifikasi kedalaman teknis.`,
      });
    } else {
      growthAreas.push({
        criterion_id: e.criterion_id || e.criterion,
        criterion: e.criterion,
        requirement_type: e.requirement_type,
        weight: e.weight || (isRequired ? 2.0 : 1.0),
        result: e.result,
        explanation: `Bukti eksplisit untuk kualifikasi ${reqBadge} (${e.criterion}) belum teridentifikasi pada berkas CV yang diproses.`,
        recommendation: `Disarankan untuk melengkapi portofolio proyek terapan atau sertifikasi relevan pada bidang ${e.criterion} untuk memperkuat profil profesional.`,
      });
    }
  });

  const metList = strengths.length
    ? strengths.slice(0, 4).map((s) => `  • ${s.criterion}: ${s.snippet}`).join("\n")
    : "  • Profil menunjukkan latar belakang umum yang potensial.";
  const devList = growthAreas.length
    ? growthAreas.slice(0, 3).map((g) => `  • ${g.criterion}: ${g.recommendation}`).join("\n")
    : "  • Terus kembangkan portofolio dan proyek mandiri.";

  let emailDraft = "";
  if (candidate.status === "advance") {
    emailDraft = `Halo ${candLabel},\n\nTerima kasih atas minat dan waktu yang Anda luangkan dalam melamar posisi ${job.title} di tim kami.\n\nBerdasarkan peninjauan bukti berkas yang disepakati bersama, Anda menunjukkan kecocokan kuat pada kompetensi berikut:\n${metList}\n\nDengan senang hati kami mengundang Anda untuk melanjutkan ke tahapan wawancara terstruktur berikutnya. Tim kami akan segera menghubungi Anda terkait detail jadwal pertemuan.\n\nSalam hangat,\nTim Rekrutmen KarsaHire`;
  } else if (candidate.status === "needs_info") {
    emailDraft = `Halo ${candLabel},\n\nTerima kasih atas lamaran Anda untuk posisi ${job.title}.\n\nDalam proses peninjauan bukti awal, tim kami melihat potensi baik pada:\n${metList}\n\nUntuk melengkapi evaluasi kualifikasi, kami membutuhkan informasi tambahan atau portofolio pendukung terkait:\n${devList}\n\nMohon membalas email ini dengan dokumen atau tautan portofolio pendukung agar kami dapat memperbarui status review Anda.\n\nSalam hangat,\nTim Rekrutmen KarsaHire`;
  } else {
    emailDraft = `Halo ${candLabel},\n\nTerima kasih banyak atas ketertarikan Anda untuk bergabung sebagai ${job.title} bersama kami.\n\nSebagai bagian dari komitmen transparansi rekrutmen berbasis bukti di KarsaHire, kami ingin membagikan umpan balik terstruktur mengenai profil Anda:\n\nKualifikasi Terpenuhi:\n${metList}\n\nArea Rekomendasi Pengembangan:\n${devList}\n\nSaat ini kami memutuskan untuk melanjutkan kandidat lain yang memiliki keselarasan kriteria lebih mendesak dengan kebutuhan tim. Namun, profil Anda tetap kami simpan dalam talent pool kami untuk kesempatan mendatang.\n\nSemoga sukses dalam perjalanan karier Anda!\n\nSalam hangat,\nTim Rekrutmen KarsaHire`;
  }

  return {
    candidate_id: candId,
    job_title: job.title,
    candidate_label: candLabel,
    score: Math.round(candidate.score || 0),
    status: candidate.status || "needs_review",
    strengths,
    growth_areas: growthAreas,
    decision_summary: `Status saat ini: ${statusLabel(candidate.status)}. Keputusan berbasis tinjauan manusia (Recruiter & Hiring Manager) dengan bukti kriteria nyata.`,
    transparency_notice: "Sesuai Pasal 40 UU No. 27/2022 tentang Pelindungan Data Pribadi (UU PDP), keputusan rekrutmen di KarsaHire sepenuhnya dipimpin oleh peninjau manusia (Human-in-the-Loop), bukan keputusan algoritma AI otomatis.",
    feedback_email_draft: emailDraft,
  };
}

function buildEmailDraftBody(tone, data, candidateDisplayName, jobTitle) {
  const metList = (data.strengths || data.qualifications_met || []).slice(0, 4)
    .map((s) => `  • ${s.criterion}: ${s.snippet || s.explanation || "Terverifikasi"}`).join("\n")
    || "  • Resume menunjukkan latar belakang umum yang potensial.";
  const devList = (data.growth_areas || data.development_areas || []).slice(0, 3)
    .map((g) => `  • ${g.criterion}: ${g.recommendation || g.growth_recommendation || "Perluas portofolio terkait"}`).join("\n")
    || "  • Terus kembangkan portofolio teknis dan kepemimpinan proyek.";

  if (tone === "advance") {
    return `Halo ${candidateDisplayName},\n\nTerima kasih atas minat dan waktu yang Anda luangkan dalam melamar posisi ${jobTitle} di tim kami.\n\nBerdasarkan peninjauan bukti berkas yang disepakati bersama, Anda menunjukkan kecocokan kuat pada kompetensi berikut:\n${metList}\n\nDengan senang hati kami mengundang Anda untuk melanjutkan ke tahapan wawancara terstruktur berikutnya. Tim kami akan segera menghubungi Anda terkait detail jadwal pertemuan.\n\nSalam hangat,\nTim Rekrutmen KarsaHire`;
  }
  if (tone === "needs_info") {
    return `Halo ${candidateDisplayName},\n\nTerima kasih atas lamaran Anda untuk posisi ${jobTitle}.\n\nDalam proses peninjauan bukti awal, tim kami melihat potensi baik pada:\n${metList}\n\nUntuk melengkapi evaluasi kualifikasi, kami membutuhkan informasi tambahan atau portofolio pendukung terkait:\n${devList}\n\nMohon membalas email ini dengan dokumen atau tautan portofolio pendukung agar kami dapat memperbarui status review Anda.\n\nSalam hangat,\nTim Rekrutmen KarsaHire`;
  }
  if (tone === "not_selected") {
    return `Halo ${candidateDisplayName},\n\nTerima kasih banyak atas ketertarikan Anda untuk bergabung sebagai ${jobTitle} bersama kami.\n\nSebagai bagian dari komitmen transparansi rekrutmen berbasis bukti di KarsaHire, kami ingin membagikan umpan balik terstruktur mengenai profil Anda:\n\nKualifikasi Terpenuhi:\n${metList}\n\nArea Rekomendasi Pengembangan:\n${devList}\n\nSaat ini kami memutuskan untuk melanjutkan kandidat lain yang memiliki keselarasan kriteria lebih mendesak dengan kebutuhan tim. Namun, profil Anda tetap kami simpan dalam talent pool kami untuk kesempatan mendatang.\n\nSemoga sukses dalam perjalanan karier Anda!\n\nSalam hangat,\nTim Rekrutmen KarsaHire`;
  }
  return data.feedback_email_draft || data.email_draft?.body || "";
}

function renderFeedbackModalContent(modal, data, candidateDisplayName, isBlind, activeTone = "auto") {
  const strengths = data.strengths || data.qualifications_met || [];
  const growthAreas = data.growth_areas || data.development_areas || [];
  const score = data.score != null ? data.score : "-";
  const status = data.status || "needs_review";
  const jobTitle = data.job_title || state.activeJob?.title || "Lowongan";

  let emailBody = buildEmailDraftBody(activeTone === "auto" ? status : activeTone, data, candidateDisplayName, jobTitle);
  let emailSubject = `Pembaruan Proses Seleksi: ${jobTitle} — ${candidateDisplayName}`;

  const strengthsHtml = strengths.length ? strengths.map((s, idx) => {
    const isRequired = s.requirement_type === "required";
    const badgeCls = isRequired ? "badge-required" : "badge-preferred";
    const badgeLabel = isRequired ? "Wajib · Bobot 2" : "Diutamakan · Bobot 1";
    const snippetText = s.snippet ? `“${escapeHtml(s.snippet)}”` : "Bukti kualifikasi terverifikasi pada teks CV.";
    const explanationText = s.explanation || s.strength_note || "Kualifikasi ini selaras dengan kriteria yang disepakati.";
    const pageText = s.page_number ? `Hal. ${s.page_number} · ` : "";

    return `
      <div class="feedback-card strength">
        <div class="feedback-card-header">
          <div class="feedback-card-title">
            <span class="feedback-check-icon">✓</span>
            <strong>${escapeHtml(s.criterion)}</strong>
          </div>
          <span class="badge ${badgeCls}">${badgeLabel}</span>
        </div>
        <div class="feedback-snippet-box">
          <span class="feedback-snippet-quote">${pageText}${snippetText}</span>
        </div>
        <p class="feedback-explanation">${escapeHtml(explanationText)}</p>
      </div>
    `;
  }).join("") : `
    <div class="feedback-empty-card">
      <p>Belum ada bukti kriteria yang teridentifikasi secara eksplisit pada berkas CV yang diproses.</p>
    </div>
  `;

  const growthHtml = growthAreas.length ? growthAreas.map((g, idx) => {
    const isRequired = g.requirement_type === "required";
    const badgeCls = isRequired ? "badge-required" : "badge-preferred";
    const badgeLabel = isRequired ? "Wajib · Bobot 2" : "Diutamakan · Bobot 1";
    const explanationText = g.explanation || g.gap_reason || "Bukti belum ditemukan pada resume.";
    const recText = g.recommendation || g.growth_recommendation || "Disarankan untuk memperkuat bukti portofolio atau sertifikasi pada kompetensi ini.";

    return `
      <div class="feedback-card growth">
        <div class="feedback-card-header">
          <div class="feedback-card-title">
            <span class="feedback-growth-icon">💡</span>
            <strong>${escapeHtml(g.criterion)}</strong>
          </div>
          <span class="badge ${badgeCls}">${badgeLabel}</span>
        </div>
        <p class="feedback-gap-text">${escapeHtml(explanationText)}</p>
        <div class="feedback-rec-box">
          <strong>Rekomendasi Peningkatan:</strong>
          <span>${escapeHtml(recText)}</span>
        </div>
      </div>
    `;
  }).join("") : `
    <div class="feedback-empty-card">
      <p>Kandidat telah memenuhi seluruh bukti kriteria lowongan tanpa area kesenjangan yang signifikan.</p>
    </div>
  `;

  modal.innerHTML = `
    <header class="modal-header">
      <div class="modal-title-group">
        <div class="modal-title-icon">✉️</div>
        <div>
          <h2 id="feedback-modal-title">Umpan Balik Kandidat &amp; Transparansi Kualifikasi</h2>
          <p class="modal-subtitle">
            <strong>${escapeHtml(candidateDisplayName)}</strong> · Posisi: <strong>${escapeHtml(jobTitle)}</strong>
            ${isBlind ? '<span class="badge badge-blind">Mode Buta Aktif</span>' : ""}
          </p>
        </div>
      </div>
      <button class="modal-close-btn" id="feedback-modal-close" type="button" aria-label="Tutup modal umpan balik" title="Tutup (ESC)">✕</button>
    </header>

    <div class="modal-body feedback-modal-body">
      <!-- Candidate Overview Banner -->
      <div class="feedback-overview-banner">
        <div class="feedback-overview-left">
          <span class="badge badge-${escapeHtml(status)} status-large">${escapeHtml(statusLabel(status))}</span>
          <span class="feedback-score-pill">Indikator Bukti: <strong>${score}%</strong></span>
        </div>
        <div class="feedback-pdp-notice">
          <span class="pdp-badge">UU PDP No. 27/2022</span>
          <span>Prinsip Human-in-the-Loop: Evaluasi dilakukan manusia berdasarkan bukti objektif, bebas penolakan otomatis algoritma black-box.</span>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <div class="feedback-tabs" role="tablist">
        <button class="feedback-tab active" type="button" role="tab" data-tab="tab-strengths" aria-selected="true">
          <span>✅ Kualifikasi Terpenuhi</span>
          <span class="feedback-tab-count">${strengths.length}</span>
        </button>
        <button class="feedback-tab" type="button" role="tab" data-tab="tab-growth" aria-selected="false">
          <span>💡 Area Pengembangan</span>
          <span class="feedback-tab-count">${growthAreas.length}</span>
        </button>
        <button class="feedback-tab" type="button" role="tab" data-tab="tab-email" aria-selected="false">
          <span>📧 Draft Email Transparan</span>
        </button>
      </div>

      <!-- Tab Content: Strengths -->
      <div id="tab-strengths" class="feedback-tab-panel active" role="tabpanel">
        <div class="feedback-panel-intro">
          <p>Kriteria dan kompetensi yang terverifikasi memiliki kecocokan bukti tekstual pada resume kandidat:</p>
        </div>
        <div class="feedback-cards-grid">
          ${strengthsHtml}
        </div>
      </div>

      <!-- Tab Content: Growth Areas -->
      <div id="tab-growth" class="feedback-tab-panel hidden" role="tabpanel">
        <div class="feedback-panel-intro">
          <p>Kriteria yang belum ditemukan buktinya pada berkas (unknown), disertai saran konstruktif untuk pengembangan profesional kandidat:</p>
        </div>
        <div class="feedback-cards-grid">
          ${growthHtml}
        </div>
      </div>

      <!-- Tab Content: Email Draft -->
      <div id="tab-email" class="feedback-tab-panel hidden" role="tabpanel">
        <div class="feedback-email-controls">
          <div class="email-tone-selector-wrap">
            <label for="email-tone-select">Template / Nada Pesan:</label>
            <div class="email-tone-buttons" role="group">
              <button class="email-tone-btn ${activeTone === 'auto' ? 'active' : ''}" type="button" data-tone="auto">Sesuai Status</button>
              <button class="email-tone-btn ${activeTone === 'advance' ? 'active' : ''}" type="button" data-tone="advance">Lanjut Wawancara</button>
              <button class="email-tone-btn ${activeTone === 'needs_info' ? 'active' : ''}" type="button" data-tone="needs_info">Permintaan Info</button>
              <button class="email-tone-btn ${activeTone === 'not_selected' ? 'active' : ''}" type="button" data-tone="not_selected">Penolakan Apresiatif</button>
            </div>
          </div>
        </div>

        <div class="feedback-email-form">
          <div class="feedback-email-field">
            <label for="feedback-email-subject">Subjek Email:</label>
            <input id="feedback-email-subject" class="feedback-email-input" value="${escapeHtml(emailSubject)}" />
          </div>
          <div class="feedback-email-field">
            <label for="feedback-email-textarea">Isi Pesan Umpan Balik (Dapat disunting langsung):</label>
            <textarea id="feedback-email-textarea" class="feedback-email-textarea" rows="12">${escapeHtml(emailBody)}</textarea>
          </div>
        </div>

        <div class="feedback-email-actions">
          <button id="copy-feedback-email-btn" class="button button-primary" type="button">
            <span>📋</span> Salin Draft Email
          </button>
          <a id="mailto-feedback-btn" class="button button-secondary" href="mailto:?subject=${encodeURIComponent(emailSubject)}&body=${encodeURIComponent(emailBody)}" target="_blank" rel="noopener">
            <span>✉️</span> Buka di Mail Client
          </a>
        </div>
      </div>
    </div>

    <footer class="modal-footer">
      <span class="muted footer-legal-note">KarsaHire · Umpan balik transparan memprioritaskan privasi kandidat dan standar etika AI.</span>
      <button class="button button-secondary" id="feedback-modal-close-btn" type="button">Tutup</button>
    </footer>
  `;

  // Attach tab switching listeners
  const tabs = modal.querySelectorAll(".feedback-tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
      });
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");

      const targetId = tab.dataset.tab;
      modal.querySelectorAll(".feedback-tab-panel").forEach((panel) => {
        panel.classList.toggle("hidden", panel.id !== targetId);
        panel.classList.toggle("active", panel.id === targetId);
      });
    });
  });

  // Attach tone switcher listeners
  const toneBtns = modal.querySelectorAll(".email-tone-btn");
  toneBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const selectedTone = btn.dataset.tone;
      renderFeedbackModalContent(modal, data, candidateDisplayName, isBlind, selectedTone);
      // Ensure email tab stays active
      const emailTab = modal.querySelector('.feedback-tab[data-tab="tab-email"]');
      if (emailTab) emailTab.click();
    });
  });

  // Attach copy email listener
  const copyBtn = modal.querySelector("#copy-feedback-email-btn");
  copyBtn?.addEventListener("click", () => {
    const text = modal.querySelector("#feedback-email-textarea")?.value || emailBody;
    copyToClipboard(text, "Draft email umpan balik berhasil disalin ke clipboard.");
  });

  // Close listeners
  modal.querySelector("#feedback-modal-close")?.addEventListener("click", closeFeedbackModal);
  modal.querySelector("#feedback-modal-close-btn")?.addEventListener("click", closeFeedbackModal);
}

async function openFeedbackModal(candidateId) {
  const backdrop = $("#feedback-modal-backdrop");
  const modal = $("#feedback-modal");
  if (!backdrop || !modal) return;

  const candidate = (state.activeJob?.candidates || []).find((c) => c.id === candidateId);
  const isBlind = window.ComparisonModule?.isBlindMode() || false;
  let candidateDisplayName = candidate?.id || candidateId;
  if (candidate) {
    const candIndex = (state.activeJob?.candidates || []).indexOf(candidate);
    candidateDisplayName = isBlind
      ? (window.ComparisonModule?.getBlindIdentifier(candidate, candIndex) || `Kandidat Anonim #${candIndex + 1}`)
      : candidateName(candidate, candIndex);
  }

  backdrop.classList.remove("hidden");
  document.body.classList.add("feedback-modal-open");

  modal.innerHTML = `
    <header class="modal-header">
      <div class="modal-title-group">
        <div class="modal-title-icon">✉️</div>
        <div>
          <h2 id="feedback-modal-title">Umpan Balik Kandidat &amp; Transparansi Kualifikasi</h2>
          <p class="modal-subtitle">Memuat data untuk ${escapeHtml(candidateDisplayName)}…</p>
        </div>
      </div>
      <button class="modal-close-btn" type="button" aria-label="Tutup modal umpan balik" title="Tutup (ESC)">✕</button>
    </header>
    <div class="modal-body feedback-modal-body">
      <div class="modal-loading-state">
        <span class="scorecard-spinner"></span>
        <p>Menghubungkan ke layanan umpan balik transparan &amp; menganalisis bukti…</p>
      </div>
    </div>
  `;

  modal.querySelector(".modal-close-btn")?.addEventListener("click", closeFeedbackModal);

  try {
    let data;
    try {
      data = await api(`/api/candidates/${encodeURIComponent(candidateId)}/feedback`);
    } catch (apiErr) {
      if (candidate && state.activeJob) {
        data = generateClientCandidateFeedback(candidate, state.activeJob);
      } else {
        throw apiErr;
      }
    }
    renderFeedbackModalContent(modal, data, candidateDisplayName, isBlind);
  } catch (err) {
    modal.innerHTML = `
      <header class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title-icon">⚠️</div>
          <div><h2>Gagal Memuat Umpan Balik</h2></div>
        </div>
        <button class="modal-close-btn" id="err-close-btn" type="button">✕</button>
      </header>
      <div class="modal-body feedback-modal-body">
        <div class="feedback-error-box">
          <p>${escapeHtml(err.message)}</p>
          <button class="button button-secondary" id="retry-feedback-btn">Coba Lagi</button>
        </div>
      </div>
    `;
    modal.querySelector("#err-close-btn")?.addEventListener("click", closeFeedbackModal);
    modal.querySelector("#retry-feedback-btn")?.addEventListener("click", () => openFeedbackModal(candidateId));
  }
}

/* --------------------------------------------------------------------------
   STAR Interview Guide Modal & Drawer Logic
   -------------------------------------------------------------------------- */
function closeStarModal() {
  const backdrop = $("#star-modal-backdrop");
  if (backdrop) backdrop.classList.add("hidden");
  document.body.classList.remove("star-modal-open");
}

function generateClientStarQuestions(job) {
  const criteria = job.criteria || [];
  const starQuestions = criteria.map((c, idx) => {
    const label = typeof c === "string" ? c : Array.isArray(c) ? c[1] : c.label || c.criterion || `Kriteria #${idx+1}`;
    const type = Array.isArray(c) ? c[0] : (typeof c === "object" ? c.type : "required");
    const weight = type === "required" ? 2.0 : 1.0;
    const lowered = String(label).toLowerCase();

    return {
      criterion: label,
      type: type,
      weight: weight,
      question: `Ceritakan situasi atau proyek nyata paling menantang di mana Anda harus menerapkan atau menangani ${label}.`,
      star_probe: {
        situation: `Apa latar belakang masalah dan konteks spesifik dari proyek yang melibatkan ${label} tersebut?`,
        task: `Apa target teknis/operasional dan batasan (waktu/sumber daya) yang menjadi tanggung jawab Anda?`,
        action: `Langkah nyata dan metodologi apa yang Anda ambil sendiri atau bersama tim dalam mengimplementasikan ${label}?`,
        result: `Apa dampak atau metrik terukur yang membuktikan keberhasilan solusi ${label} tersebut?`,
      },
      look_for: [
        `Menunjukkan pemahaman mendalam tentang konsep dan eksekusi ${label}.`,
        `Mampu mengartikulasikan kontribusi dan keputusan individual secara spesifik.`,
        `Menyertakan dampak atau metrik bisnis/teknis yang terukur.`,
      ],
      red_flags: [
        `Jawaban murni teoretis tanpa bukti pengalaman langsung pada ${label}.`,
        `Menyalahkan pihak lain ketika mendiskusikan kendala atau kegagalan.`,
        `Tidak memahami logika di balik keputusan atau kode yang diklaim ditulis sendiri.`,
      ],
    };
  });

  return {
    job_id: job.id,
    title: job.title,
    department: job.department || "",
    criteria: criteria,
    star_questions: starQuestions,
  };
}

function renderStarModalContent(modal, data, job, activeFilter = "all") {
  const jobTitle = data.title || job.title || "Posisi Rekrutmen";
  const starQuestions = data.star_questions || [];

  const filterTabsHtml = `
    <button class="star-filter-tab ${activeFilter === 'all' ? 'active' : ''}" type="button" data-crit="all">
      Semua Kriteria (${starQuestions.length})
    </button>
    ${starQuestions.map((sq, idx) => `
      <button class="star-filter-tab ${activeFilter === sq.criterion ? 'active' : ''}" type="button" data-crit="${escapeHtml(sq.criterion)}">
        ${idx + 1}. ${escapeHtml(sq.criterion)}
      </button>
    `).join("")}
  `;

  const visibleQuestions = activeFilter === "all"
    ? starQuestions
    : starQuestions.filter((q) => q.criterion === activeFilter);

  const questionsCardsHtml = visibleQuestions.map((sq, idx) => {
    const isRequired = sq.type === "required";
    const badgeCls = isRequired ? "badge-required" : "badge-preferred";
    const badgeLabel = isRequired ? "Wajib · Bobot 2" : "Diutamakan · Bobot 1";
    const probes = sq.star_probe || sq.questions || {};
    const lookForList = sq.look_for || sq.positive_indicators || [];
    const redFlagsList = sq.red_flags || [];

    const copyText = `[Panduan Wawancara STAR: ${sq.criterion}]\nPertanyaan Utama: ${sq.question || ""}\n- Situasi: ${probes.situation || ""}\n- Tugas: ${probes.task || ""}\n- Aksi: ${probes.action || ""}\n- Hasil: ${probes.result || ""}`;

    return `
      <article class="star-card" data-criterion="${escapeHtml(sq.criterion)}">
        <header class="star-card-header">
          <div class="star-card-title-group">
            <span class="star-card-badge-num">${idx + 1}</span>
            <div>
              <h3 class="star-card-heading">${escapeHtml(sq.criterion)}</h3>
              <span class="badge ${badgeCls}">${badgeLabel}</span>
            </div>
          </div>
          <button class="button button-ghost button-sm copy-star-btn" type="button" data-copy="${escapeHtml(copyText)}" title="Salin pertanyaan kriteria ini">
            <span>📋</span> Salin Pertanyaan
          </button>
        </header>

        <!-- Core Behavioral Question Box -->
        <div class="star-main-question-box">
          <span class="star-quote-icon">“</span>
          <p class="star-main-question-text">${escapeHtml(sq.question || probes.situation || "Ceritakan pengalaman Anda terkait kriteria ini.")}</p>
        </div>

        <!-- 4-Quadrant STAR Probe Grid -->
        <div class="star-quadrant-grid">
          <div class="star-probe-item probe-situation">
            <div class="probe-header">
              <span class="probe-letter">S</span>
              <strong>Situasi (Situation)</strong>
            </div>
            <p class="probe-text">${escapeHtml(probes.situation || "Apa konteks dan tantangan utama yang dihadapi?")}</p>
          </div>

          <div class="star-probe-item probe-task">
            <div class="probe-header">
              <span class="probe-letter">T</span>
              <strong>Tugas (Task)</strong>
            </div>
            <p class="probe-text">${escapeHtml(probes.task || "Apa peran spesifik dan ekspektasi yang harus Anda capai?")}</p>
          </div>

          <div class="star-probe-item probe-action">
            <div class="probe-header">
              <span class="probe-letter">A</span>
              <strong>Aksi (Action)</strong>
            </div>
            <p class="probe-text">${escapeHtml(probes.action || "Langkah nyata dan teknologi apa yang Anda terapkan?")}</p>
          </div>

          <div class="star-probe-item probe-result">
            <div class="probe-header">
              <span class="probe-letter">R</span>
              <strong>Hasil (Result)</strong>
            </div>
            <p class="probe-text">${escapeHtml(probes.result || "Bagaimana hasil terukur dan evaluasi dari inisiatif tersebut?")}</p>
          </div>
        </div>

        <!-- Behavioral Indicators -->
        <div class="star-indicators-grid">
          <div class="star-indicators-col positive">
            <div class="indicators-header">
              <span>🌟</span>
              <strong>Indikator Skor Tinggi (Skor 4–5 / Kuat &amp; Luar Biasa)</strong>
            </div>
            <ul class="indicators-list">
              ${lookForList.map((lf) => `<li>${escapeHtml(lf)}</li>`).join("")}
            </ul>
          </div>

          <div class="star-indicators-col negative">
            <div class="indicators-header">
              <span>⚠️</span>
              <strong>Sinyal Waspada / Red Flags (Skor 1–2 / Tidak Memadai)</strong>
            </div>
            <ul class="indicators-list">
              ${redFlagsList.map((rf) => `<li>${escapeHtml(rf)}</li>`).join("")}
            </ul>
          </div>
        </div>
      </article>
    `;
  }).join("");

  modal.innerHTML = `
    <header class="modal-header">
      <div class="modal-title-group">
        <div class="modal-title-icon">🎯</div>
        <div>
          <h2 id="star-modal-title">Panduan Wawancara Perilaku STAR</h2>
          <p class="modal-subtitle">Situation · Task · Action · Result untuk posisi <strong>${escapeHtml(jobTitle)}</strong></p>
        </div>
      </div>
      <button class="modal-close-btn" id="star-modal-close" type="button" aria-label="Tutup panduan STAR" title="Tutup (ESC)">✕</button>
    </header>

    <div class="modal-body star-modal-body">
      <!-- Educational Framework Ribbon -->
      <div class="star-method-ribbon">
        <div class="star-method-col">
          <span class="star-pill star-s">S · Situasi</span>
          <p>Minta kandidat menggambarkan konteks spesifik masa lalu.</p>
        </div>
        <div class="star-method-col">
          <span class="star-pill star-t">T · Tugas</span>
          <p>Eksplorasi tanggung jawab dan target yang harus diselesaikan.</p>
        </div>
        <div class="star-method-col">
          <span class="star-pill star-a">A · Aksi</span>
          <p>Gali tindakan nyata, tools, dan keputusan individual kandidat.</p>
        </div>
        <div class="star-method-col">
          <span class="star-pill star-r">R · Hasil</span>
          <p>Ukur dampak keberhasilan, metrik terukur, dan refleksi diri.</p>
        </div>
      </div>

      <!-- Quick Criteria Jump Filter -->
      <div class="star-filter-nav" role="tablist">
        ${filterTabsHtml}
      </div>

      <!-- Questions List -->
      <div class="star-questions-list">
        ${questionsCardsHtml}
      </div>
    </div>

    <footer class="modal-footer">
      <span class="muted footer-legal-note">Gunakan panduan ini saat mengisi Scorecard Wawancara 1–5 untuk memastikan konsistensi evaluasi.</span>
      <button class="button button-secondary" id="star-modal-close-btn" type="button">Tutup</button>
    </footer>
  `;

  // Attach filter click listeners
  modal.querySelectorAll(".star-filter-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      renderStarModalContent(modal, data, job, tab.dataset.crit);
    });
  });

  // Attach copy question listeners
  modal.querySelectorAll(".copy-star-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      copyToClipboard(btn.dataset.copy, "Pertanyaan STAR berhasil disalin ke clipboard.");
    });
  });

  // Close listeners
  modal.querySelector("#star-modal-close")?.addEventListener("click", closeStarModal);
  modal.querySelector("#star-modal-close-btn")?.addEventListener("click", closeStarModal);
}

async function openStarModal(candidateId = null) {
  if (!state.activeJob?.id) {
    toast("Pilih requisition terlebih dahulu.");
    return;
  }

  const backdrop = $("#star-modal-backdrop");
  const modal = $("#star-modal");
  if (!backdrop || !modal) return;

  const job = state.activeJob;
  backdrop.classList.remove("hidden");
  document.body.classList.add("star-modal-open");

  modal.innerHTML = `
    <header class="modal-header">
      <div class="modal-title-group">
        <div class="modal-title-icon">🎯</div>
        <div>
          <h2 id="star-modal-title">Panduan Wawancara Perilaku STAR</h2>
          <p class="modal-subtitle">Menyiapkan panduan pertanyaan terstruktur untuk ${escapeHtml(job.title)}…</p>
        </div>
      </div>
      <button class="modal-close-btn" type="button" aria-label="Tutup panduan STAR" title="Tutup (ESC)">✕</button>
    </header>
    <div class="modal-body star-modal-body">
      <div class="modal-loading-state">
        <span class="scorecard-spinner"></span>
        <p>Menyusun rubrik pertanyaan perilaku STAR berbasis kriteria yang disepakati…</p>
      </div>
    </div>
  `;

  modal.querySelector(".modal-close-btn")?.addEventListener("click", closeStarModal);

  try {
    let data;
    try {
      data = await api(`/api/jobs/${encodeURIComponent(job.id)}/star-questions`);
    } catch (apiErr) {
      data = generateClientStarQuestions(job);
    }
    renderStarModalContent(modal, data, job);
  } catch (err) {
    modal.innerHTML = `
      <header class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title-icon">⚠️</div>
          <div><h2>Gagal Memuat Panduan STAR</h2></div>
        </div>
        <button class="modal-close-btn" id="star-err-close-btn" type="button">✕</button>
      </header>
      <div class="modal-body star-modal-body">
        <div class="feedback-error-box">
          <p>${escapeHtml(err.message)}</p>
          <button class="button button-secondary" id="retry-star-btn">Coba Lagi</button>
        </div>
      </div>
    `;
    modal.querySelector("#star-err-close-btn")?.addEventListener("click", closeStarModal);
    modal.querySelector("#retry-star-btn")?.addEventListener("click", () => openStarModal());
  }
}

// Global click delegation for candidate feedback and star guide buttons
document.addEventListener("click", (event) => {
  const feedbackBtn = event.target.closest(".candidate-feedback-btn");
  if (feedbackBtn) {
    const candidateId = feedbackBtn.dataset.candidateId;
    if (candidateId) {
      openFeedbackModal(candidateId);
    }
    return;
  }

  const starBtn = event.target.closest(".star-guide-btn");
  if (starBtn) {
    const candidateId = starBtn.dataset.candidateId;
    openStarModal(candidateId);
    return;
  }
});

// ESC key listener for modals
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!$("#feedback-modal-backdrop")?.classList.contains("hidden")) {
      closeFeedbackModal();
    }
    if (!$("#star-modal-backdrop")?.classList.contains("hidden")) {
      closeStarModal();
    }
  }
});

// Backdrop click listener to close modals
$("#feedback-modal-backdrop")?.addEventListener("click", (e) => {
  if (e.target === $("#feedback-modal-backdrop")) {
    closeFeedbackModal();
  }
});

$("#star-modal-backdrop")?.addEventListener("click", (e) => {
  if (e.target === $("#star-modal-backdrop")) {
    closeStarModal();
  }
});

window.state = state;
window.loadJobs = loadJobs;
window.api = api;
window.toast = toast;

if (window.ComparisonModule) {
  window.ComparisonModule.init({
    onReviewSubmit: async (candidateId, reviewData) => {
      await api(`/api/candidates/${encodeURIComponent(candidateId)}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reviewData),
      });
      await loadJobs(state.activeJob?.id);
    },
    onStateChange: () => {
      if (state.activeJob) renderCandidates(state.activeJob);
    },
  });
}

if (window.ScorecardModule) {
  window.ScorecardModule.init({
    onScorecardSubmit: async (candidateId) => {
      if (state.activeJob?.id) {
        renderActivity(await api(`/api/jobs/${encodeURIComponent(state.activeJob.id)}/events`));
      }
    },
  });
}

updateOcrIndicator().catch(() => {});
loadJobs().catch((error) => toast(error.message));
