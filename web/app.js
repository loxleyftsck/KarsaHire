const state = {
  jobs: [],
  activeJob: null,
  reviewer: "",
  loadingSynthetic: false,
  candidateFilter: "all",
  searchQuery: "",
  candidateSort: "score_desc",
};
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
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
  list.innerHTML = `<h4>Requisition aktif</h4>${state.jobs.map((job) => `
    <button class="job-item ${state.activeJob?.id === job.id ? "active" : ""}" data-job-id="${escapeHtml(job.id)}">
      <span class="job-icon">↗</span><span><strong>${escapeHtml(job.title)}</strong><small>${escapeHtml(job.department || "Tim belum diisi")} · ${job.candidate_count || 0} kandidat</small></span><span class="job-arrow">›</span>
    </button>`).join("")}`;
}

function statusLabel(status) {
  return ({ needs_review: "Perlu review", advance: "Lanjut proses", needs_info: "Perlu informasi", not_selected: "Keputusan manusia: tidak lanjut" })[status] || status;
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
  if (exportCsvBtn) exportCsvBtn.disabled = !candidates.length;
  if (exportJsonBtn) exportJsonBtn.disabled = !candidates.length;

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
      const label = row.result === "matched" ? "Ada bukti" : row.result === "partial" ? "Bukti parsial" : "Belum diketahui";
      const cls = row.result === "matched" ? "status-matched" : row.result === "partial" ? "status-partial" : "status-unknown";
      const snippet = row.snippet ? `“${escapeHtml(row.snippet)}”` : "Tidak ditemukan pada teks CV yang diekstrak.";
      const page = row.page_number ? `Hal. ${row.page_number}` : "Dokumen";
      const signal = row.result === "matched" ? "Frasa ditemukan" : row.result === "partial" ? "Token parsial" : "Tidak ada sinyal";
      return `<div class="evidence-item"><div class="evidence-criterion">${escapeHtml(row.criterion)}<div class="muted">${row.requirement_type === "required" ? "Wajib · bobot 2" : "Diutamakan · bobot 1"}</div></div><div class="evidence-snippet">${snippet}</div><div><span class="evidence-status ${cls}">${label}</span><div class="evidence-page">${page} · ${signal}</div></div></div>`;
    }).join("");
    const skills = candidate.profile.skills || [];
    const tags = skills.length ? skills.slice(0, 10).map((skill) => `<span class="tag">${escapeHtml(skill)}</span>`).join("") : `<span class="tag">Skill belum terdeteksi</span>`;
    const experience = candidate.profile.experience_years_mentioned == null ? "Pengalaman: belum diketahui" : `Pengalaman disebut: ${candidate.profile.experience_years_mentioned} tahun`;
    const education = candidate.profile.education_levels_mentioned?.join(", ") || "Pendidikan: belum diketahui";
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
        <div class="score-block"><div class="score-number">${score}<small>/100</small></div><div class="score-label">indikator evidence</div><div class="score-track"><div class="score-fill" style="width:${Math.max(0, Math.min(100, score))}%"></div></div></div>
      </div>
      <button class="candidate-expand" type="button"><span class="chev">⌄</span> Buka evidence dan catat review manusia</button>
      <div class="candidate-details"><div class="candidate-detail-actions"><span class="review-hint">Data profil, evidence, dan review dapat dihapus dari antrean.</span><button class="candidate-delete" type="button" data-candidate-id="${escapeHtml(candidate.id)}">Hapus kandidat</button></div><div class="profile-tags">${tags}</div><div class="evidence-list">${evidenceRows}</div>
        <form class="review-form" data-candidate-id="${escapeHtml(candidate.id)}">
          <div class="review-grid"><input name="reviewer" aria-label="Nama reviewer" placeholder="Nama reviewer" required maxlength="100" value="${escapeHtml(state.reviewer)}"><select name="role" aria-label="Peran reviewer"><option value="recruiter">Recruiter</option><option value="hiring_manager">Hiring manager</option></select><select name="decision" aria-label="Keputusan reviewer"><option value="advance">Lanjut proses</option><option value="needs_info">Perlu informasi</option><option value="not_selected">Tidak lanjut</option></select></div>
          <textarea name="note" placeholder="Catatan berbasis kriteria/evidence (opsional)" maxlength="2000"></textarea><div class="review-actions"><span class="review-hint">Keputusan ini dicatat sebagai review manusia.</span><button class="button button-secondary" type="submit">Simpan review</button></div>
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
            <button class="scorecard-toggle-form-btn" type="button" data-candidate-id="${escapeHtml(candidate.id)}">
              <span class="btn-icon">✏️</span> Isi Scorecard
            </button>
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

function renderActivity(events) {
  const node = $("#activity-list");
  if (!events.length) { node.innerHTML = `<p class="muted">Aktivitas akan muncul setelah review dicatat.</p>`; return; }
  const labels = { criteria_submitted: "Kriteria requisition diajukan", criteria_approval_recorded: "Persetujuan kriteria dicatat", candidate_parsed: "CV diproses dan evidence dibuat", synthetic_dataset_loaded: "Batch CV sintetis dimuat", human_review_recorded: "Review manusia dicatat", candidate_deleted: "Data kandidat dihapus" };
  node.innerHTML = events.slice(0, 8).map((event) => `<div class="activity-item"><span class="activity-dot"></span><div>${escapeHtml(labels[event.event_type] || event.event_type)}<small>${escapeHtml(event.actor)} · ${new Date(event.created_at).toLocaleString("id-ID")}</small></div></div>`).join("");
}

async function loadJobs(preferredId = state.activeJob?.id) {
  state.jobs = await api("/api/jobs");
  renderJobs();
  const chosen = state.jobs.find((job) => job.id === preferredId) || state.jobs[0];
  if (chosen) await selectJob(chosen.id);
  else {
    state.activeJob = null;
    $("#active-workspace").classList.add("hidden");
    $("#setup-state").classList.remove("hidden");
    $("#active-title").textContent = "Belum ada requisition";
    $("#active-subtitle").textContent = "Buat requisition atau muat contoh sintetis untuk memulai.";
    $("#pipeline-chip").innerHTML = `<span class="pulse"></span> Setup`;
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
  $("#active-subtitle").textContent = `${state.activeJob.department || "Tim belum diisi"} · ${state.activeJob.criteria.length} kriteria · ${approved ? "disetujui dua peran" : "menunggu persetujuan"}`;
  $("#active-workspace").classList.remove("hidden");
  $("#setup-state").classList.add("hidden");
  $$(".workflow-step").forEach((step, index) => step.classList.toggle("active", approved || index === 0));
  $("#pipeline-chip").innerHTML = `<span class="pulse"></span> ${approved ? "Siap review" : "Menunggu persetujuan"}`;
  renderApprovals(state.activeJob);
  renderSyntheticLoader(state.activeJob);
  $("#resume-file").disabled = !approved;
  $("#upload-label").classList.toggle("disabled", !approved);
  $("#upload-label").setAttribute("aria-disabled", String(!approved));
  renderCandidates(state.activeJob);
  renderJobs();
  renderActivity(await api(`/api/jobs/${encodeURIComponent(jobId)}/events`));
}

function renderSyntheticLoader(job) {
  const button = $("#load-synthetic-button");
  const dataset = job?.synthetic_data || { available: 0, loaded: 0 };
  const available = Number(dataset.available) || 0;
  const loaded = Number(dataset.loaded) || 0;
  button.textContent = available ? `Muat CV uji (${loaded}/${available})` : "Dataset uji belum siap";
  button.disabled = !job || job.status !== "criteria_approved" || !available || loaded >= available || state.loadingSynthetic;
  button.title = job?.status !== "criteria_approved"
    ? "Kriteria harus disetujui recruiter dan hiring manager terlebih dahulu."
    : available ? "Impor teks referensi CV sintetis dari dataset lokal; tidak memakai OCR." : "Salin dataset ke data/synthetic-cv-32 terlebih dahulu.";
}

function renderApprovals(job) {
  const roles = [
    ["recruiter", "Recruiter"],
    ["hiring_manager", "Hiring manager"],
  ];
  const approvals = job.approvals || [];
  $("#approval-status").innerHTML = roles.map(([role, label]) => {
    const approval = approvals.find((item) => item.role === role);
    return `<span class="approval-person ${approval ? "approved" : "pending"}"><b>${approval ? "✓" : "○"}</b>${label}${approval ? ` · ${escapeHtml(approval.reviewer)}` : " · menunggu"}</span>`;
  }).join("");
  const form = $("#approval-form");
  form.classList.toggle("hidden", job.status === "criteria_approved");
  if (job.status !== "criteria_approved") {
    const selectedRole = form.elements.role.value;
    const filledRole = approvals.some((item) => item.role === selectedRole);
    form.querySelector("button").disabled = filledRole;
    form.elements.role.querySelectorAll("option").forEach((option) => {
      option.disabled = approvals.some((item) => item.role === option.value);
    });
    if (filledRole) form.elements.role.value = roles.find(([role]) => !approvals.some((item) => item.role === role))?.[0] || "recruiter";
  }
}

async function createJob(data) {
  const created = await api("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  await loadJobs(created.id);
  return created;
}

async function uploadFile(file) {
  if (!state.activeJob) return toast("Buat atau pilih requisition lebih dulu.");
  if (!file) return;
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    await api(`/api/jobs/${encodeURIComponent(state.activeJob.id)}/candidates`, { method: "POST", body: form });
    state.reviewer ||= "";
    toast("CV diproses. Periksa evidence sebelum meninjau.");
    await loadJobs(state.activeJob.id);
  } catch (error) { toast(error.message); }
  finally { $("#resume-file").value = ""; }
}

async function loadSyntheticData() {
  if (!state.activeJob || state.loadingSynthetic) return;
  const jobId = state.activeJob.id;
  state.loadingSynthetic = true;
  renderSyntheticLoader(state.activeJob);
  try {
    const result = await api(`/api/jobs/${encodeURIComponent(jobId)}/load-synthetic-data`, { method: "POST" });
    toast(result.message);
    await loadJobs(jobId);
  } catch (error) { toast(error.message); }
  finally {
    state.loadingSynthetic = false;
    renderSyntheticLoader(state.activeJob);
  }
}

$("#job-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    await createJob({ title: form.get("title"), department: form.get("department"), description: form.get("description"), criteria: parseCriteria(form.get("criteria")) });
    toast("Requisition tersimpan. Kriteria sudah masuk audit trail.");
    event.currentTarget.reset();
  } catch (error) { toast(error.message); }
});

$("#role-template").addEventListener("change", (event) => {
  applyRoleTemplate(event.currentTarget.value);
});

$("#fill-example").addEventListener("click", () => {
  $("#role-template").value = "custom";
  applyRoleTemplate("custom");
  $("#job-title").value = "Backend Engineer";
  $("#department").value = "Platform Engineering";
  $("#description").value = "Membangun API yang aman dan andal. Berkolaborasi dengan product, data, dan infrastructure untuk merilis layanan yang terukur.";
  $("#criteria").value = "Wajib | Python\nWajib | FastAPI\nWajib | PostgreSQL\nDiutamakan | Docker\nDiutamakan | Cross-functional collaboration";
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
    const cv = new File([`Candidate Demo 001\nSUMMARY\nBackend engineer with 4 years of experience building API services.\nSKILLS\nPython, FastAPI, PostgreSQL, Docker, Git\nEXPERIENCE\nBuilt FastAPI services backed by PostgreSQL and deployed containers with Docker.\nWorked across product, data, and infrastructure teams to launch customer-facing APIs.\nEDUCATION\nBachelor of Science in Computer Science`], "candidate-demo.txt", { type: "text/plain" });
    await uploadFile(cv);
    toast("Contoh sintetis siap ditinjau.");
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; }
});

$("#jobs-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-job-id]");
  if (!button) return;
  try { await selectJob(button.dataset.jobId); }
  catch (error) { toast(error.message); }
});

$("#approval-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeJob) return;
  const data = new FormData(event.currentTarget);
  try {
    await api(`/api/jobs/${encodeURIComponent(state.activeJob.id)}/approvals`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer: data.get("reviewer"), role: data.get("role") }),
    });
    toast("Persetujuan dicatat.");
    await loadJobs(state.activeJob.id);
  } catch (error) { toast(error.message); }
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
  const toggle = event.target.closest(".candidate-expand");
  if (toggle) {
    const card = toggle.closest(".candidate-card");
    card.classList.toggle("open");
    if (card.classList.contains("open") && window.ScorecardModule) {
      window.ScorecardModule.loadForCandidate(card.dataset.candidateId);
    }
  }
  const deleteButton = event.target.closest(".candidate-delete");
  if (deleteButton) deleteCandidate(deleteButton);
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
  state.reviewer = data.get("reviewer");
  try {
    await api(`/api/candidates/${encodeURIComponent(form.dataset.candidateId)}/reviews`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer: data.get("reviewer"), role: data.get("role"), decision: data.get("decision"), note: data.get("note") }),
    });
    toast("Review manusia tersimpan.");
    await loadJobs(state.activeJob.id);
  } catch (error) { toast(error.message); }
});

$("#ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.activeJob) return;
  const question = $("#question").value.trim();
  if (!question) return;
  $("#ask-result").textContent = "Mencari sumber requisition…";
  try {
    const result = await api(`/api/jobs/${encodeURIComponent(state.activeJob.id)}/ask`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
    });
    $("#ask-result").innerHTML = `${escapeHtml(result.answer)}${result.sources.length ? result.sources.map((source) => `<div class="ask-source"><strong>${escapeHtml(source.source)}</strong>${escapeHtml(source.text)}</div>`).join("") : `<div class="ask-source">Tidak ditemukan dalam sumber requisition yang disimpan.</div>`}`;
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
