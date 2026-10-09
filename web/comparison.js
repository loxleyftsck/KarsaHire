/**
 * KarsaHire — Candidate Comparison & Blind-First Review Module
 * web/comparison.js
 */

(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ComparisonModule = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const STORAGE_KEY_BLIND = "karsahire_blind_mode";
  const MAX_SELECTION = 3;
  const MIN_SELECTION = 2;

  const state = {
    blindMode: false,
    selectedCandidateIds: new Set(),
    activeJob: null,
    onReviewCallback: null,
    onStateChangeCallback: null,
  };

  function escapeHtml(str) {
    return String(str || "").replace(/[&<>"']/g, function (char) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[char];
    });
  }

  function getToast() {
    return typeof window.toast === "function" ? window.toast : function (msg) {
      const t = document.getElementById("toast");
      if (t) {
        t.textContent = msg;
        t.classList.add("show");
        setTimeout(function () { t.classList.remove("show"); }, 2800);
      }
    };
  }

  function statusLabel(status) {
    const map = {
      needs_review: "Perlu review",
      advance: "Lanjut proses",
      needs_info: "Perlu informasi",
      not_selected: "Tidak lanjut",
    };
    return map[status] || status;
  }

  /* --------------------------------------------------------------------------
     Blind Review Mode
     -------------------------------------------------------------------------- */
  function isBlindMode() {
    return state.blindMode;
  }

  function getBlindIdentifier(candidate, index) {
    if (typeof index === "number" && index >= 0) {
      const letter = String.fromCharCode(65 + (index % 26));
      return "Kandidat Anonim " + letter;
    }
    // Fallback based on last 4 chars if index is not supplied
    const suffix = (candidate?.id || "").slice(-4).toUpperCase();
    return "Kandidat Anonim #" + (suffix || "X");
  }

  function getCandidateLabel(candidate, index) {
    if (!candidate) return "Kandidat";
    if (state.blindMode) {
      return getBlindIdentifier(candidate, index);
    }
    return "Kandidat · " + (candidate.id || "").slice(-4).toUpperCase();
  }

  function setBlindMode(enabled, notify) {
    state.blindMode = !!enabled;
    try {
      localStorage.setItem(STORAGE_KEY_BLIND, state.blindMode ? "true" : "false");
    } catch (_) {}

    if (state.blindMode) {
      document.body.classList.add("blind-mode");
    } else {
      document.body.classList.remove("blind-mode");
    }

    const toggleBtn = document.getElementById("blind-mode-toggle");
    if (toggleBtn) {
      toggleBtn.classList.toggle("active", state.blindMode);
      toggleBtn.setAttribute("aria-pressed", String(state.blindMode));
      const textSpan = toggleBtn.querySelector(".blind-text");
      if (textSpan) {
        textSpan.textContent = state.blindMode ? "Mode Buta: Aktif" : "Mode Buta";
      }
    }

    const banner = document.getElementById("blind-mode-banner");
    if (banner) {
      banner.classList.toggle("hidden", !state.blindMode);
    }

    // If modal is open, re-render it
    const modalBackdrop = document.getElementById("comparison-modal-backdrop");
    if (modalBackdrop && !modalBackdrop.classList.contains("hidden") && state.activeJob) {
      renderComparisonModal(state.activeJob);
    }

    if (typeof state.onStateChangeCallback === "function") {
      state.onStateChangeCallback();
    }

    if (notify) {
      const toast = getToast();
      toast(state.blindMode
        ? "Mode Review Buta aktif: Identitas dan avatar disamarkan."
        : "Mode Review Buta dinonaktifkan: Identitas ditampilkan normal.");
    }
  }

  function toggleBlindMode() {
    setBlindMode(!state.blindMode, true);
  }

  /* --------------------------------------------------------------------------
     Candidate Selection for Comparison
     -------------------------------------------------------------------------- */
  function getSelectedCandidateIds() {
    return Array.from(state.selectedCandidateIds);
  }

  function isCandidateSelected(candidateId) {
    return state.selectedCandidateIds.has(candidateId);
  }

  function toggleCandidateSelection(candidateId, job) {
    if (job) state.activeJob = job;
    const toast = getToast();

    if (state.selectedCandidateIds.has(candidateId)) {
      state.selectedCandidateIds.delete(candidateId);
    } else {
      if (state.selectedCandidateIds.size >= MAX_SELECTION) {
        toast("Maksimal 3 kandidat untuk dibandingkan sekaligus.");
        updateSelectionUI(state.activeJob);
        return false;
      }
      state.selectedCandidateIds.add(candidateId);
    }

    updateSelectionUI(state.activeJob);
    return true;
  }

  function clearSelection() {
    state.selectedCandidateIds.clear();
    updateSelectionUI(state.activeJob);
  }

  function updateSelectionUI(job) {
    if (job) state.activeJob = job;
    const count = state.selectedCandidateIds.size;

    // 1. Sync checkboxes on candidate cards
    const checkboxes = document.querySelectorAll(".candidate-select-check");
    checkboxes.forEach(function (chk) {
      chk.checked = state.selectedCandidateIds.has(chk.dataset.candidateId);
    });

    // 2. Sync candidate cards highlighting
    const cards = document.querySelectorAll(".candidate-card");
    cards.forEach(function (card) {
      card.classList.toggle("comparing", state.selectedCandidateIds.has(card.dataset.candidateId));
    });

    // 3. Sync toolbar compare button
    const compareBtn = document.getElementById("compare-selected-button");
    const countBadge = document.getElementById("compare-count-badge");
    if (compareBtn) {
      compareBtn.disabled = count < MIN_SELECTION;
      if (countBadge) {
        countBadge.textContent = count + "/" + MAX_SELECTION;
        countBadge.classList.toggle("hidden", count === 0);
      }
      compareBtn.title = count >= MIN_SELECTION
        ? "Bandingkan " + count + " kandidat side-by-side"
        : "Pilih minimal 2 kandidat untuk dibandingkan (maks 3)";
    }

    // 4. Sync floating comparison dock
    const dock = document.getElementById("comparison-dock");
    const dockText = document.getElementById("comparison-dock-text");
    const dockOpenBtn = document.getElementById("comparison-dock-open");

    if (dock) {
      dock.classList.toggle("hidden", count === 0);
      if (dockText) {
        dockText.textContent = count + " dari " + MAX_SELECTION + " kandidat dipilih";
      }
      if (dockOpenBtn) {
        dockOpenBtn.disabled = count < MIN_SELECTION;
        dockOpenBtn.innerHTML = count >= MIN_SELECTION
          ? "<span>⚖</span> Bandingkan Side-by-Side (" + count + ")"
          : "Pilih minimal 2 kandidat (" + count + "/" + MAX_SELECTION + ")";
      }
    }
  }

  /* --------------------------------------------------------------------------
     Modal Render & Logic
     -------------------------------------------------------------------------- */
  function openComparisonModal(job) {
    if (job) state.activeJob = job;
    const toast = getToast();

    if (state.selectedCandidateIds.size < MIN_SELECTION) {
      toast("Pilih minimal 2 kandidat untuk dibandingkan side-by-side.");
      return;
    }

    renderComparisonModal(state.activeJob);

    const backdrop = document.getElementById("comparison-modal-backdrop");
    if (backdrop) {
      backdrop.classList.remove("hidden");
      document.body.classList.add("comparison-open");
      // Focus modal for keyboard accessibility
      backdrop.querySelector(".comparison-close-btn")?.focus();
    }
  }

  function closeComparisonModal() {
    const backdrop = document.getElementById("comparison-modal-backdrop");
    if (backdrop) {
      backdrop.classList.add("hidden");
      document.body.classList.remove("comparison-open");
    }
  }

  function getEvidenceInfo(candidate, criterionLabel) {
    const list = candidate.evidence || [];
    const ev = list.find(function (e) {
      return (e.criterion || "").toLowerCase() === (criterionLabel || "").toLowerCase();
    });
    if (!ev) {
      return {
        result: "unknown",
        snippet: "",
        page: null,
        signal: "Tidak ada sinyal",
      };
    }
    return {
      result: ev.result || "unknown",
      snippet: ev.snippet || "",
      page: ev.page_number ? "Hal. " + ev.page_number : "Dokumen",
      signal: ev.result === "matched" ? "Frasa ditemukan" : ev.result === "partial" ? "Token parsial" : "Tidak ada sinyal",
    };
  }

  function renderComparisonModal(job) {
    const backdrop = document.getElementById("comparison-modal-backdrop");
    if (!backdrop || !job) return;

    // Filter and preserve order of candidates
    const allCandidates = job.candidates || [];
    const selected = allCandidates.filter(function (c) {
      return state.selectedCandidateIds.has(c.id);
    });

    if (selected.length < MIN_SELECTION) {
      closeComparisonModal();
      return;
    }

    const colCount = selected.length; // 2 or 3
    const colsClass = "cols-" + colCount;
    const criteria = job.criteria || [];

    // Precalculate divergence per criterion
    const criteriaAnalysis = criteria.map(function (crit) {
      const results = selected.map(function (cand) {
        return getEvidenceInfo(cand, crit.label).result;
      });
      const uniqueResults = new Set(results);
      const isDivergent = uniqueResults.size > 1;
      const hasMatchAndUnknown = uniqueResults.has("matched") && uniqueResults.has("unknown");
      return {
        criterion: crit,
        results: results,
        isDivergent: isDivergent,
        hasMatchAndUnknown: hasMatchAndUnknown,
      };
    });

    const divergentCount = criteriaAnalysis.filter(function (c) { return c.isDivergent; }).length;

    // Candidate Header Cards
    const headerColsHtml = selected.map(function (candidate, index) {
      const displayName = getCandidateLabel(candidate, index);
      const score = Math.round(candidate.score || 0);
      const skills = candidate.profile?.skills || [];
      const tagsHtml = skills.slice(0, 5).map(function (s) {
        return '<span class="tag">' + escapeHtml(s) + '</span>';
      }).join("") || '<span class="tag">Skill belum terdeteksi</span>';

      const exp = candidate.profile?.experience_years_mentioned != null
        ? candidate.profile.experience_years_mentioned + " thn peng."
        : "Pengalaman: -";
      const edu = candidate.profile?.education_levels_mentioned?.[0] || "Pendidikan: -";

      const matchedCount = (candidate.evidence || []).filter(function (e) { return e.result === "matched"; }).length;
      const partialCount = (candidate.evidence || []).filter(function (e) { return e.result === "partial"; }).length;
      const unknownCount = (candidate.evidence || []).filter(function (e) { return e.result === "unknown"; }).length;

      return `
        <div class="comparison-candidate-head-card">
          <div class="comparison-candidate-top">
            <div class="comparison-candidate-identity">
              <div class="comparison-candidate-avatar">${String(index + 1).padStart(2, "0")}</div>
              <div>
                <div class="comparison-candidate-title">${escapeHtml(displayName)}</div>
                <span class="comparison-candidate-status-pill">${escapeHtml(statusLabel(candidate.status))}</span>
              </div>
            </div>
            <div class="comparison-candidate-score-block">
              <div class="comparison-candidate-score">${score}<small>/100</small></div>
              <div class="comparison-score-track">
                <div class="comparison-score-fill" style="width: ${Math.max(0, Math.min(100, score))}%"></div>
              </div>
            </div>
          </div>
          <div class="comparison-candidate-meta-row">
            <span class="comparison-meta-chip">${escapeHtml(exp)}</span>
            <span class="comparison-meta-chip">${escapeHtml(edu)}</span>
          </div>
          <div class="comparison-candidate-tags">${tagsHtml}</div>
          <div class="comparison-evidence-summary-bar">
            <span class="summary-count-matched">✓ ${matchedCount} Cocok</span>
            <span class="summary-count-partial">◐ ${partialCount} Parsial</span>
            <span class="summary-count-unknown">○ ${unknownCount} Belum Bukti</span>
          </div>
        </div>
      `;
    }).join("");

    // Criteria Rows
    const criteriaRowsHtml = criteriaAnalysis.map(function (item) {
      const crit = item.criterion;
      const isDivergent = item.isDivergent;
      const divergenceBadge = isDivergent
        ? `<span class="divergence-pill" title="Hasil bukti berbeda antar kandidat">${item.hasMatchAndUnknown ? "⚡ Bukti vs Belum Ada" : "⚡ Beda Sinyal"}</span>`
        : "";

      const evidenceColsHtml = selected.map(function (candidate) {
        const ev = getEvidenceInfo(candidate, crit.label);
        const statusClass = ev.result === "matched"
          ? "status-matched"
          : ev.result === "partial"
          ? "status-partial"
          : "status-unknown";

        const statusText = ev.result === "matched"
          ? "Ada bukti"
          : ev.result === "partial"
          ? "Bukti parsial"
          : "Belum diketahui";

        let cellDiffClass = "";
        if (isDivergent) {
          if (ev.result === "matched") cellDiffClass = "cell-diff-matched";
          else if (ev.result === "unknown") cellDiffClass = "cell-diff-unknown";
        }

        const snippetHtml = ev.snippet
          ? `“${escapeHtml(ev.snippet)}”`
          : `<span class="snippet-empty">Tidak ada kutipan bukti pada teks CV.</span>`;

        return `
          <div class="comparison-evidence-cell ${cellDiffClass}">
            <div class="evidence-status-line">
              <span class="evidence-status ${statusClass}">${statusText}</span>
              <span class="evidence-loc">${escapeHtml(ev.page)} · ${escapeHtml(ev.signal)}</span>
            </div>
            <div class="comparison-evidence-snippet-box">${snippetHtml}</div>
          </div>
        `;
      }).join("");

      return `
        <div class="comparison-criterion-row ${colsClass} ${isDivergent ? "divergent-row" : ""}">
          <div class="comparison-criterion-cell">
            <span class="criterion-name-text">${escapeHtml(crit.label)}</span>
            <span class="criterion-type-pill ${crit.type === "required" ? "required" : "preferred"}">
              ${crit.type === "required" ? "Wajib · Bobot 2" : "Diutamakan · Bobot 1"}
            </span>
            ${divergenceBadge}
          </div>
          ${evidenceColsHtml}
        </div>
      `;
    }).join("");

    // Review Actions Columns
    const activeReviewer = window.state?.reviewer || "";
    const reviewColsHtml = selected.map(function (candidate, index) {
      const displayName = getCandidateLabel(candidate, index);
      const reviews = candidate.reviews || [];
      const historyHtml = reviews.length
        ? `<div class="comparison-review-history">
            <strong>Riwayat Review:</strong>
            ${reviews.map(function (r) {
              return `<div>${escapeHtml(r.reviewer)} (${r.role === "recruiter" ? "Recruiter" : "HM"}): <em>${escapeHtml(statusLabel(r.decision))}</em>${r.note ? ` — "${escapeHtml(r.note)}"` : ""}</div>`;
            }).join("")}
          </div>`
        : "";

      return `
        <div class="comparison-review-cell">
          <form class="comparison-quick-review-form" data-candidate-id="${escapeHtml(candidate.id)}">
            <div class="quick-form-row">
              <div class="quick-form-field">
                <label for="rev-name-${candidate.id}">Reviewer</label>
                <input id="rev-name-${candidate.id}" name="reviewer" value="${escapeHtml(activeReviewer)}" placeholder="Nama reviewer" required maxlength="100">
              </div>
              <div class="quick-form-field">
                <label for="rev-role-${candidate.id}">Peran</label>
                <select id="rev-role-${candidate.id}" name="role">
                  <option value="recruiter">Recruiter</option>
                  <option value="hiring_manager">Hiring manager</option>
                </select>
              </div>
            </div>
            <div class="quick-form-field">
              <label for="rev-decision-${candidate.id}">Keputusan</label>
              <select id="rev-decision-${candidate.id}" name="decision">
                <option value="advance" ${candidate.status === "advance" ? "selected" : ""}>Lanjut proses</option>
                <option value="needs_info" ${candidate.status === "needs_info" ? "selected" : ""}>Perlu informasi</option>
                <option value="not_selected" ${candidate.status === "not_selected" ? "selected" : ""}>Tidak lanjut</option>
              </select>
            </div>
            <div class="quick-form-field">
              <label for="rev-note-${candidate.id}">Catatan Penilaian</label>
              <textarea id="rev-note-${candidate.id}" name="note" placeholder="Catatan perbandingan terhadap kriteria..." maxlength="2000"></textarea>
            </div>
            <div class="quick-form-actions">
              <span class="quick-review-hint">Catat langsung ke audit trail</span>
              <button class="btn-save-quick-review" type="submit">
                <span>✓</span> Simpan Review
              </button>
            </div>
          </form>
          ${historyHtml}
        </div>
      `;
    }).join("");

    backdrop.innerHTML = `
      <div class="comparison-modal" role="dialog" aria-modal="true" aria-labelledby="comparison-modal-title">
        <header class="comparison-modal-header">
          <div class="comparison-modal-title-wrap">
            <h3 id="comparison-modal-title">
              <span>⚖</span> Perbandingan Kandidat Side-by-Side
            </h3>
            <div class="comparison-modal-subtitle">
              Posisi: <strong>${escapeHtml(job.title)}</strong> · Membandingkan ${colCount} kandidat secara sejajar
            </div>
          </div>
          <div class="comparison-modal-header-actions">
            <button id="modal-blind-toggle" class="button-blind ${state.blindMode ? "active" : ""}" type="button" aria-pressed="${state.blindMode}">
              <span class="blind-icon">👁</span>
              <span class="blind-text">${state.blindMode ? "Mode Buta: Aktif" : "Mode Buta"}</span>
            </button>
            <button class="comparison-close-btn" type="button" aria-label="Tutup perbandingan">✕</button>
          </div>
        </header>

        <div class="comparison-legend-bar">
          <div class="comparison-legend-items">
            <span class="comparison-legend-item">
              <span class="evidence-status status-matched" style="font-size:9px;padding:2px 5px;">Ada bukti</span>
            </span>
            <span class="comparison-legend-item">
              <span class="evidence-status status-partial" style="font-size:9px;padding:2px 5px;">Bukti parsial</span>
            </span>
            <span class="comparison-legend-item">
              <span class="evidence-status status-unknown" style="font-size:9px;padding:2px 5px;">Belum diketahui</span>
            </span>
            <span class="comparison-legend-item">
              <span class="diff-legend-dot"></span>
              <strong>${divergentCount} Kriteria memiliki perbedaan bukti antar kandidat</strong>
            </span>
          </div>
          <div class="legend-note">Perbedaan bukti disorot secara otomatis. Keputusan tetap di tangan reviewer manusia.</div>
        </div>

        <div class="comparison-modal-body">
          <div class="comparison-table-wrapper">
            <!-- Header Row -->
            <div class="comparison-candidates-head ${colsClass}">
              <div class="comparison-corner-cell">
                <span class="comparison-corner-title">Kriteria vs Kandidat</span>
                <span class="comparison-corner-desc">${criteria.length} kriteria terdaftar</span>
              </div>
              ${headerColsHtml}
            </div>

            <!-- Criteria Rows -->
            <div class="comparison-criteria-section">
              ${criteriaRowsHtml}
            </div>

            <!-- Review Actions Section -->
            <div class="comparison-review-section-head">
              <span>✍</span> Aksi Review Langsung dari Perbandingan
            </div>
            <div class="comparison-review-row ${colsClass}">
              <div class="comparison-review-guide-cell">
                <h4>Catat Evaluasi Manusia</h4>
                <p>Simpan keputusan review langsung untuk kandidat terkait setelah memeriksa bukti berdampingan. Catatan akan langsung terekam pada audit trail.</p>
              </div>
              ${reviewColsHtml}
            </div>
          </div>
        </div>
      </div>
    `;

    // Bind Modal Events
    const closeBtn = backdrop.querySelector(".comparison-close-btn");
    if (closeBtn) {
      closeBtn.addEventListener("click", closeComparisonModal);
    }

    const modalBlindToggle = backdrop.querySelector("#modal-blind-toggle");
    if (modalBlindToggle) {
      modalBlindToggle.addEventListener("click", function () {
        toggleBlindMode();
      });
    }

    // Bind Quick Review Submissions
    const reviewForms = backdrop.querySelectorAll(".comparison-quick-review-form");
    reviewForms.forEach(function (form) {
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        handleQuickReviewSubmit(form);
      });
    });
  }

  async function handleQuickReviewSubmit(form) {
    const candidateId = form.dataset.candidateId;
    if (!candidateId) return;

    const fd = new FormData(form);
    const reviewer = (fd.get("reviewer") || "").trim();
    const role = fd.get("role") || "recruiter";
    const decision = fd.get("decision") || "advance";
    const note = (fd.get("note") || "").trim();

    if (!reviewer) {
      const toast = getToast();
      toast("Nama reviewer wajib diisi.");
      return;
    }

    if (window.state) {
      window.state.reviewer = reviewer;
    }

    const submitBtn = form.querySelector(".btn-save-quick-review");
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = "Menyimpan…";
    }

    try {
      if (typeof state.onReviewCallback === "function") {
        await state.onReviewCallback(candidateId, { reviewer, role, decision, note });
      } else {
        const res = await fetch("/api/candidates/" + encodeURIComponent(candidateId) + "/reviews", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reviewer, role, decision, note }),
        });
        if (!res.ok) {
          const err = await res.json().catch(function () { return {}; });
          throw new Error(err.error || "Gagal menyimpan review.");
        }
      }

      const toast = getToast();
      toast("Review manusia tersimpan untuk kandidat.");

      // Refresh job data if available
      if (window.loadJobs && state.activeJob?.id) {
        await window.loadJobs(state.activeJob.id);
      }
    } catch (err) {
      const toast = getToast();
      toast(err.message || "Gagal menyimpan review.");
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = "<span>✓</span> Simpan Review";
      }
    }
  }

  /* --------------------------------------------------------------------------
     Initialization
     -------------------------------------------------------------------------- */
  function init(options) {
    options = options || {};
    state.onReviewCallback = options.onReviewSubmit || null;
    state.onStateChangeCallback = options.onStateChange || null;

    // 1. Restore blind mode from localStorage
    let savedBlind = false;
    try {
      savedBlind = localStorage.getItem(STORAGE_KEY_BLIND) === "true";
    } catch (_) {}
    setBlindMode(savedBlind, false);

    // 2. Global ESC key listener to close modal
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        const backdrop = document.getElementById("comparison-modal-backdrop");
        if (backdrop && !backdrop.classList.contains("hidden")) {
          closeComparisonModal();
        }
      }
    });

    // 3. Backdrop click listener
    const backdrop = document.getElementById("comparison-modal-backdrop");
    if (backdrop) {
      backdrop.addEventListener("click", function (e) {
        if (e.target === backdrop) {
          closeComparisonModal();
        }
      });
    }

    // 4. Bind Floating Dock Buttons
    const dockClearBtn = document.getElementById("comparison-dock-clear");
    if (dockClearBtn) {
      dockClearBtn.addEventListener("click", function () {
        clearSelection();
      });
    }

    const dockOpenBtn = document.getElementById("comparison-dock-open");
    if (dockOpenBtn) {
      dockOpenBtn.addEventListener("click", function () {
        openComparisonModal(state.activeJob || window.state?.activeJob);
      });
    }

    // 5. Bind Toolbar Compare Button
    const toolbarCompareBtn = document.getElementById("compare-selected-button");
    if (toolbarCompareBtn) {
      toolbarCompareBtn.addEventListener("click", function () {
        openComparisonModal(state.activeJob || window.state?.activeJob);
      });
    }

    // 6. Bind Toolbar Blind Mode Toggle
    const toolbarBlindBtn = document.getElementById("blind-mode-toggle");
    if (toolbarBlindBtn) {
      toolbarBlindBtn.addEventListener("click", function () {
        toggleBlindMode();
      });
    }
  }

  return {
    init: init,
    isBlindMode: isBlindMode,
    setBlindMode: setBlindMode,
    toggleBlindMode: toggleBlindMode,
    getBlindIdentifier: getBlindIdentifier,
    getCandidateLabel: getCandidateLabel,
    getSelectedCandidateIds: getSelectedCandidateIds,
    isCandidateSelected: isCandidateSelected,
    toggleCandidateSelection: toggleCandidateSelection,
    clearSelection: clearSelection,
    updateSelectionUI: updateSelectionUI,
    openComparisonModal: openComparisonModal,
    closeComparisonModal: closeComparisonModal,
    renderComparisonModal: renderComparisonModal,
  };
});
