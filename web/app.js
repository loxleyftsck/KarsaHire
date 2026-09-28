const state = { jobs: [], activeJob: null, reviewer: "", loadingSynthetic: false };
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

function candidateName(candidate) { return `Kandidat · ${candidate.id.slice(-4).toUpperCase()}`; }

function renderCandidates(job) {
  const container = $("#candidate-list");
  const candidates = job.candidates || [];
  $("#candidate-count").textContent = candidates.length;
  $("#empty-candidates").classList.toggle("hidden", candidates.length > 0);
  if (!candidates.length) { container.innerHTML = ""; return; }
  container.innerHTML = candidates.map((candidate, index) => {
    const score = Math.round(candidate.score);
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
    return `<article class="candidate-card" data-candidate-id="${escapeHtml(candidate.id)}">
      <div class="candidate-main"><div class="candidate-avatar">${String(index + 1).padStart(2, "0")}</div><div class="candidate-info"><div class="candidate-name">${candidateName(candidate)} <span class="tag">${escapeHtml(statusLabel(candidate.status))}</span></div><div class="candidate-meta">${escapeHtml(experience)} · ${escapeHtml(education)} · CV ${escapeHtml(candidate.file_type.toUpperCase())}</div></div><div class="score-block"><div class="score-number">${score}<small>/100</small></div><div class="score-label">indikator evidence</div><div class="score-track"><div class="score-fill" style="width:${Math.max(0, Math.min(100, score))}%"></div></div></div></div>
      <button class="candidate-expand" type="button"><span class="chev">⌄</span> Buka evidence dan catat review manusia</button>
      <div class="candidate-details"><div class="profile-tags">${tags}</div><div class="evidence-list">${evidenceRows}</div>
        <form class="review-form" data-candidate-id="${escapeHtml(candidate.id)}">
          <div class="review-grid"><input name="reviewer" aria-label="Nama reviewer" placeholder="Nama reviewer" required maxlength="100" value="${escapeHtml(state.reviewer)}"><select name="role" aria-label="Peran reviewer"><option value="recruiter">Recruiter</option><option value="hiring_manager">Hiring manager</option></select><select name="decision" aria-label="Keputusan reviewer"><option value="advance">Lanjut proses</option><option value="needs_info">Perlu informasi</option><option value="not_selected">Tidak lanjut</option></select></div>
          <textarea name="note" placeholder="Catatan berbasis kriteria/evidence (opsional)" maxlength="2000"></textarea><div class="review-actions"><span class="review-hint">Keputusan ini dicatat sebagai review manusia.</span><button class="button button-secondary" type="submit">Simpan review</button></div>
        </form>${reviews}</div>
    </article>`;
  }).join("");
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

$("#fill-example").addEventListener("click", () => {
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

$("#candidate-list").addEventListener("click", (event) => {
  const toggle = event.target.closest(".candidate-expand");
  if (toggle) toggle.closest(".candidate-card").classList.toggle("open");
});

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

loadJobs().catch((error) => toast(error.message));
