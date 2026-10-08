const state = { jobs: [], activeJob: null, reviewer: "", loadingSynthetic: false, manualUploadsEnabled: false };
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

function candidateName(candidate) { return `Kandidat · ${candidate.id.slice(-4).toUpperCase()}`; }

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
  $("#candidate-count").textContent = candidates.length;
  $("#empty-candidates").classList.toggle("hidden", candidates.length > 0);
  if (!candidates.length) { container.innerHTML = ""; return; }
  container.innerHTML = candidates.map((candidate, index) => {
    const score = Math.round(candidate.score);
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
      ? `Pendidikan disebut: ${educationMentions.join(", ")}`
      : "Pendidikan: belum diketahui";
    const reviews = candidate.reviews.length ? `<div class="review-history">${candidate.reviews.map((review) => `<div><strong>${escapeHtml(review.reviewer)}</strong> · ${review.role === "recruiter" ? "Perekrut" : "Manajer perekrutan"}: ${escapeHtml(statusLabel(review.decision))}${review.note ? ` — ${escapeHtml(review.note)}` : ""}</div>`).join("")}</div>` : "";
    return `<article class="candidate-card" data-candidate-id="${escapeHtml(candidate.id)}">
      <div class="candidate-main"><div class="candidate-avatar">${String(index + 1).padStart(2, "0")}</div><div class="candidate-info"><div class="candidate-name">${candidateName(candidate)} <span class="tag">${escapeHtml(statusLabel(candidate.status))}</span></div><div class="candidate-meta">${escapeHtml(experience)} · ${escapeHtml(education)} · CV ${escapeHtml(candidate.file_type.toUpperCase())}</div></div><div class="score-block"><div class="score-number">${score}<small>%</small></div><div class="score-label" title="Persentase berbobot dari kecocokan frasa dan token pada teks CV; bukan penilaian kelayakan.">Cakupan bukti</div><div class="score-track" role="meter" aria-label="Cakupan bukti tekstual" aria-valuenow="${score}" aria-valuemin="0" aria-valuemax="100"><div class="score-fill" style="width:${Math.max(0, Math.min(100, score))}%"></div></div></div></div>
      <div class="candidate-actions">
        <button class="candidate-expand" type="button" aria-label="Buka bukti dan catat tinjauan untuk ${escapeHtml(candidateName(candidate))}" aria-expanded="false" aria-controls="candidate-details-${escapeHtml(candidate.id)}"><span class="chev" aria-hidden="true">⌄</span> Buka bukti dan catat tinjauan manusia</button>
        <button class="candidate-delete" type="button" aria-label="Hapus ${escapeHtml(candidateName(candidate))} beserta bukti dan tinjauannya">Hapus kandidat</button>
      </div>
      <div class="candidate-details" id="candidate-details-${escapeHtml(candidate.id)}"><div class="profile-tags">${tags}</div><div class="evidence-list">${evidenceRows}</div>
        <form class="review-form" data-candidate-id="${escapeHtml(candidate.id)}">
          <div class="review-grid"><input name="reviewer" aria-label="Nama peninjau" placeholder="Nama peninjau" required maxlength="100" value="${escapeHtml(state.reviewer)}"><select name="role" aria-label="Peran peninjau"><option value="recruiter">Perekrut</option><option value="hiring_manager">Manajer perekrutan</option></select><select name="decision" aria-label="Keputusan peninjau"><option value="advance">Lanjut proses</option><option value="needs_info">Perlu informasi</option><option value="not_selected">Tidak lanjut</option></select></div>
          <label class="visually-hidden" for="review-note-${escapeHtml(candidate.id)}">Catatan berdasarkan kriteria dan bukti (opsional)</label><textarea id="review-note-${escapeHtml(candidate.id)}" name="note" placeholder="Catatan berdasarkan kriteria dan bukti (opsional)" maxlength="2000"></textarea><div class="review-actions"><span class="review-hint">Keputusan ini dicatat oleh peninjau.</span><button class="button button-secondary" type="submit">Simpan tinjauan</button></div>
        </form>${reviews}</div>
    </article>`;
  }).join("");
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
    const expanded = toggle.getAttribute("aria-expanded") !== "true";
    toggle.closest(".candidate-card").classList.toggle("open", expanded);
    toggle.setAttribute("aria-expanded", String(expanded));
  }
});

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

loadJobs().catch((error) => toast(error.message));
