/**
 * KarsaHire — Structured Interview Scorecard & Rubric Module
 * web/scorecard.js
 */

(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ScorecardModule = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const SCORE_RUBRIC = {
    1: "Tidak memadai",
    2: "Kurang",
    3: "Memenuhi syarat",
    4: "Kuat",
    5: "Luar biasa",
  };

  const RECOMMENDATIONS = {
    advance: { label: "Lanjut proses", icon: "✓", class: "advance" },
    needs_info: { label: "Perlu informasi", icon: "ℹ", class: "needs_info" },
    not_selected: { label: "Tidak lanjut", icon: "✕", class: "not_selected" },
  };

  const ROLES = {
    recruiter: { label: "Recruiter", class: "recruiter" },
    hiring_manager: { label: "Hiring Manager", class: "hiring_manager" },
  };

  let globalOptions = {
    onScorecardSubmit: null,
  };

  const candidateScorecardCache = new Map();

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

  function showToast(msg) {
    if (typeof window.toast === "function") {
      window.toast(msg);
      return;
    }
    const t = document.getElementById("toast");
    if (t) {
      t.textContent = msg;
      t.classList.add("show");
      setTimeout(function () {
        t.classList.remove("show");
      }, 2800);
    } else {
      console.log("[Toast]", msg);
    }
  }

  async function requestApi(path, options = {}) {
    if (typeof window.api === "function") {
      return window.api(path, options);
    }
    const response = await fetch(path, options);
    if (!response.ok) {
      let message = "Terjadi kesalahan.";
      try {
        const data = await response.json();
        message = data.error || message;
      } catch {
        message = response.statusText || message;
      }
      throw new Error(message);
    }
    return response.json();
  }

  /**
   * Extract criteria list from active job or fallback to candidate evidence
   */
  function getCriteriaForCandidate(candidateId) {
    const activeJob = window.state?.activeJob;
    if (activeJob && Array.isArray(activeJob.criteria) && activeJob.criteria.length > 0) {
      return activeJob.criteria.map((c, idx) => {
        if (typeof c === "string") {
          return { id: `crit_${idx}`, label: c, type: "required" };
        }
        if (Array.isArray(c)) {
          return { id: `crit_${idx}`, type: c[0] || "required", label: c[1] || `Kriteria #${idx + 1}` };
        }
        return {
          id: c.id || `crit_${idx}`,
          label: c.label || c.criterion || c.name || `Kriteria #${idx + 1}`,
          type: c.type || c.requirement_type || "required",
        };
      });
    }

    // Fallback: check if candidate evidence exists in activeJob candidates
    const cand = activeJob?.candidates?.find((item) => item.id === candidateId);
    if (cand && Array.isArray(cand.evidence) && cand.evidence.length > 0) {
      return cand.evidence.map((ev, idx) => ({
        id: `crit_${idx}`,
        label: ev.criterion || `Kriteria #${idx + 1}`,
        type: ev.requirement_type || "required",
      }));
    }

    // Fallback default criteria
    return [
      { id: "crit_0", label: "Keahlian Teknis Utama", type: "required" },
      { id: "crit_1", label: "Pemecahan Masalah & Logika", type: "required" },
      { id: "crit_2", label: "Komunikasi & Kolaborasi", type: "preferred" },
    ];
  }

  /**
   * Render dual-role comparison header when both Recruiter and Hiring Manager have submitted scorecards
   */
  function renderComparisonHeader(summary) {
    if (!summary) return "";
    const recRole = summary.by_role?.recruiter;
    const hmRole = summary.by_role?.hiring_manager;

    const hasRec = recRole && recRole.scorecard_count > 0;
    const hasHm = hmRole && hmRole.scorecard_count > 0;

    if (!hasRec && !hasHm) {
      return "";
    }

    if (hasRec && !hasHm) {
      const recAvg = summary.recruiter_average != null ? summary.recruiter_average.toFixed(1) : "-";
      const reviewer = (recRole.reviewers || []).join(", ") || "Recruiter";
      return `
        <div class="scorecard-single-role-banner">
          <span class="single-role-icon">⏳</span>
          <div>
            <strong>Menunggu evaluasi Hiring Manager:</strong> Recruiter (<em>${escapeHtml(reviewer)}</em>) telah memberikan skor rata-rata <strong>${recAvg}/5.0</strong>. Evaluasi Hiring Manager akan memicu perbandingan dual-role otomatis.
          </div>
        </div>
      `;
    }

    if (!hasRec && hasHm) {
      const hmAvg = summary.hiring_manager_average != null ? summary.hiring_manager_average.toFixed(1) : "-";
      const reviewer = (hmRole.reviewers || []).join(", ") || "Hiring Manager";
      return `
        <div class="scorecard-single-role-banner">
          <span class="single-role-icon">⏳</span>
          <div>
            <strong>Menunggu evaluasi Recruiter:</strong> Hiring Manager (<em>${escapeHtml(reviewer)}</em>) telah memberikan skor rata-rata <strong>${hmAvg}/5.0</strong>. Evaluasi Recruiter akan memicu perbandingan dual-role otomatis.
          </div>
        </div>
      `;
    }

    // Both roles have evaluated! Render full dual comparison header
    const recAvgNum = summary.recruiter_average != null ? summary.recruiter_average : 0;
    const hmAvgNum = summary.hiring_manager_average != null ? summary.hiring_manager_average : 0;
    const delta = Math.abs(recAvgNum - hmAvgNum).toFixed(1);

    const recReviewers = (recRole.reviewers || []).join(", ") || "Recruiter";
    const hmReviewers = (hmRole.reviewers || []).join(", ") || "Hiring Manager";

    const recRecs = (recRole.recommendations || []).map((r) => RECOMMENDATIONS[r]?.label || r).join(", ") || "-";
    const hmRecs = (hmRole.recommendations || []).map((r) => RECOMMENDATIONS[r]?.label || r).join(", ") || "-";

    // Consensus determination
    const recPrimary = recRole.recommendations?.[0];
    const hmPrimary = hmRole.recommendations?.[0];
    const isAligned = recPrimary === hmPrimary;

    const consensusHtml = isAligned
      ? `<span class="consensus-badge aligned">✓ Konsensus Sejalan (${escapeHtml(RECOMMENDATIONS[recPrimary]?.label || recPrimary)})</span>`
      : `<span class="consensus-badge divergent">⚠️ Perbedaan Rekomendasi (Perlu Diskusi)</span>`;

    // Criteria comparison matrix
    let matrixHtml = "";
    const criteriaMap = summary.by_criterion || summary.criteria || {};
    const critKeys = Object.keys(criteriaMap);

    if (critKeys.length > 0) {
      const rows = critKeys.map((key) => {
        const item = criteriaMap[key];
        const label = item.criterion_label || key;
        const roleAverages = item.role_averages || {};
        const rScore = roleAverages.recruiter != null ? Number(roleAverages.recruiter).toFixed(1) : (item.by_role?.recruiter?.average_score != null ? Number(item.by_role.recruiter.average_score).toFixed(1) : "-");
        const hScore = roleAverages.hiring_manager != null ? Number(roleAverages.hiring_manager).toFixed(1) : (item.by_role?.hiring_manager?.average_score != null ? Number(item.by_role.hiring_manager.average_score).toFixed(1) : "-");

        let diffBadge = `<span class="matrix-diff-indicator">-</span>`;
        if (rScore !== "-" && hScore !== "-") {
          const rNum = parseFloat(rScore);
          const hNum = parseFloat(hScore);
          if (rNum === hNum) {
            diffBadge = `<span class="matrix-diff-indicator equal">Sama (=)</span>`;
          } else if (rNum > hNum) {
            diffBadge = `<span class="matrix-diff-indicator diff">Recruiter +${(rNum - hNum).toFixed(1)}</span>`;
          } else {
            diffBadge = `<span class="matrix-diff-indicator diff">HM +${(hNum - rNum).toFixed(1)}</span>`;
          }
        }

        return `
          <div class="matrix-data-row">
            <span class="matrix-crit-name" title="${escapeHtml(label)}">${escapeHtml(label)}</span>
            <span class="matrix-score-val is-recruiter">${rScore}</span>
            <span class="matrix-score-val is-hiring-manager">${hScore}</span>
            ${diffBadge}
          </div>
        `;
      }).join("");

      matrixHtml = `
        <div class="scorecard-criteria-matrix">
          <div class="matrix-header-row">
            <span>Kriteria</span>
            <span style="text-align:center;">Recruiter</span>
            <span style="text-align:center;">Hiring Mgr</span>
            <span style="text-align:center;">Selisih</span>
          </div>
          ${rows}
        </div>
      `;
    }

    return `
      <div class="scorecard-dual-comparison">
        <div class="comparison-banner-top">
          <div class="comparison-banner-title">
            <span>⚖️</span> Perbandingan Wawancara: Recruiter vs Hiring Manager
          </div>
          <span class="comparison-dual-tag">Evaluasi Lengkap</span>
        </div>

        <div class="comparison-grid-3col">
          <!-- Recruiter Column -->
          <div class="comparison-role-card is-recruiter">
            <div class="comparison-role-header">
              <span class="role-pill recruiter">Recruiter</span>
              <span class="comparison-reviewer-name" title="${escapeHtml(recReviewers)}">${escapeHtml(recReviewers)}</span>
            </div>
            <div class="comparison-score-display">
              <span class="comparison-score-num">${recAvgNum.toFixed(1)}</span>
              <span class="comparison-score-max">/5.0</span>
              <span class="comparison-score-rubric">(${SCORE_RUBRIC[Math.round(recAvgNum)] || ""})</span>
            </div>
            <span class="comparison-rec-badge rec-badge ${recPrimary || 'advance'}">${escapeHtml(recRecs)}</span>
          </div>

          <!-- Middle VS & Consensus -->
          <div class="comparison-vs-card">
            <span class="vs-icon-badge">VS</span>
            <div class="vs-delta-indicator">Selisih: Δ ${delta} poin</div>
            ${consensusHtml}
          </div>

          <!-- Hiring Manager Column -->
          <div class="comparison-role-card is-hiring-manager">
            <div class="comparison-role-header">
              <span class="role-pill hiring_manager">Hiring Manager</span>
              <span class="comparison-reviewer-name" title="${escapeHtml(hmReviewers)}">${escapeHtml(hmReviewers)}</span>
            </div>
            <div class="comparison-score-display">
              <span class="comparison-score-num">${hmAvgNum.toFixed(1)}</span>
              <span class="comparison-score-max">/5.0</span>
              <span class="comparison-score-rubric">(${SCORE_RUBRIC[Math.round(hmAvgNum)] || ""})</span>
            </div>
            <span class="comparison-rec-badge rec-badge ${hmPrimary || 'advance'}">${escapeHtml(hmRecs)}</span>
          </div>
        </div>

        ${matrixHtml}
      </div>
    `;
  }

  /**
   * Render history list of past recorded scorecards
   */
  function renderScorecardsList(scorecards) {
    if (!scorecards || scorecards.length === 0) {
      return `
        <div class="scorecard-empty">
          <span class="scorecard-empty-icon">📝</span>
          <strong>Belum ada scorecard wawancara untuk kandidat ini.</strong>
          <p style="margin:4px 0 0; font-size:11px;">Gunakan tombol "Isi Scorecard" untuk mendokumentasikan evaluasi wawancara terstruktur skala 1–5.</p>
        </div>
      `;
    }

    const itemsHtml = scorecards.map((sc, idx) => {
      const avg = sc.average_score != null ? Number(sc.average_score).toFixed(1) : "-";
      const rubricText = sc.average_score != null ? SCORE_RUBRIC[Math.round(sc.average_score)] : "";
      const rec = RECOMMENDATIONS[sc.overall_recommendation] || {
        label: sc.overall_recommendation,
        icon: "•",
        class: "advance",
      };
      const roleLabel = ROLES[sc.role]?.label || sc.role;
      const roleClass = sc.role === "hiring_manager" ? "hiring_manager" : "recruiter";
      const dateStr = sc.created_at ? new Date(sc.created_at).toLocaleString("id-ID") : "";

      const critScores = sc.criterion_scores || sc.scores || [];
      const criteriaBreakdownHtml = critScores.length > 0
        ? `
          <div class="scorecard-breakdown-details">
            <button type="button" class="scorecard-breakdown-toggle" data-toggle-breakdown="${escapeHtml(sc.id)}">
              <span>Rincian Nilai per Kriteria (${critScores.length})</span> ▾
            </button>
            <div class="scorecard-breakdown-list hidden" id="breakdown-list-${escapeHtml(sc.id)}">
              ${critScores.map((cs) => {
                const s = Number(cs.score) || 0;
                const rubricDesc = SCORE_RUBRIC[s] || "";
                return `
                  <div class="scorecard-breakdown-item">
                    <div>
                      <span class="breakdown-crit-label">${escapeHtml(cs.criterion_label)}</span>
                      ${cs.evidence_notes ? `<span class="breakdown-crit-evidence">Observasi: “${escapeHtml(cs.evidence_notes)}”</span>` : ""}
                    </div>
                    <span class="breakdown-crit-score-chip rating-btn-label selected-${s}">
                      ${s}/5 · ${escapeHtml(rubricDesc)}
                    </span>
                  </div>
                `;
              }).join("")}
            </div>
          </div>
        `
        : "";

      return `
        <article class="scorecard-history-item" data-scorecard-id="${escapeHtml(sc.id)}">
          <div class="scorecard-item-topbar">
            <div class="scorecard-item-reviewer-group">
              <span class="scorecard-reviewer-name">${escapeHtml(sc.reviewer)}</span>
              <span class="role-pill ${roleClass}">${escapeHtml(roleLabel)}</span>
              ${dateStr ? `<span class="scorecard-date">${escapeHtml(dateStr)}</span>` : ""}
            </div>
            <div class="scorecard-item-badges">
              <span class="scorecard-avg-badge" title="Rata-rata rubrik 1-5">
                ⭐ ${avg} <span class="max-label">/5.0</span> ${rubricText ? `(${escapeHtml(rubricText)})` : ""}
              </span>
              <span class="rec-badge ${rec.class}">
                ${rec.icon} ${escapeHtml(rec.label)}
              </span>
            </div>
          </div>

          ${sc.notes ? `<div class="scorecard-item-notes">“${escapeHtml(sc.notes)}”</div>` : ""}
          ${criteriaBreakdownHtml}
        </article>
      `;
    }).join("");

    return `
      <div class="scorecard-history-section">
        <h5 class="scorecard-history-title">Riwayat Evaluasi Pewawancara (${scorecards.length})</h5>
        <div class="scorecard-history-list">
          ${itemsHtml}
        </div>
      </div>
    `;
  }

  /**
   * Load candidate scorecards from API and render history & comparison
   */
  async function loadCandidateScorecards(candidateId, containerEl) {
    if (!containerEl) {
      containerEl = document.getElementById(`scorecard-body-${candidateId}`);
    }
    if (!containerEl) return;

    try {
      const data = await requestApi(`/api/candidates/${encodeURIComponent(candidateId)}/scorecards`);
      const scorecards = data.scorecards || [];
      const summary = data.summary || null;

      // Cache data
      candidateScorecardCache.set(candidateId, { scorecards, summary });

      const comparisonHeaderHtml = renderComparisonHeader(summary);
      const listHtml = renderScorecardsList(scorecards);

      // Preserve existing open form state if user was already typing
      const existingForm = containerEl.querySelector(`#scorecard-form-${candidateId}`);
      const isFormVisible = existingForm && !existingForm.classList.contains("hidden");

      containerEl.innerHTML = `
        ${comparisonHeaderHtml}
        ${listHtml}
        <div class="scorecard-form-wrapper ${isFormVisible ? "" : "hidden"}" id="scorecard-form-${escapeHtml(candidateId)}"></div>
      `;

      // If form was visible, re-render it
      if (isFormVisible) {
        const formWrap = containerEl.querySelector(`#scorecard-form-${candidateId}`);
        renderForm(candidateId, formWrap);
      }

      // Update button text in section header
      const btn = document.querySelector(`.scorecard-toggle-form-btn[data-candidate-id="${candidateId}"]`);
      if (btn) {
        btn.classList.toggle("active", isFormVisible);
        btn.innerHTML = isFormVisible
          ? `<span class="btn-icon">✕</span> Tutup Form`
          : `<span class="btn-icon">✏️</span> Isi Scorecard`;
      }
    } catch (err) {
      containerEl.innerHTML = `
        <div class="scorecard-empty">
          <span style="color:#a04c4c;">Gagal memuat data scorecard: ${escapeHtml(err.message)}</span>
        </div>
      `;
    }
  }

  /**
   * Alias for loadCandidateScorecards by candidateId
   */
  function loadForCandidate(candidateId) {
    const container = document.getElementById(`scorecard-body-${candidateId}`);
    return loadCandidateScorecards(candidateId, container);
  }

  /**
   * Render structured scorecard input form
   */
  function renderForm(candidateId, containerEl) {
    if (!containerEl) {
      containerEl = document.getElementById(`scorecard-form-${candidateId}`);
    }
    if (!containerEl) return;

    const criteria = getCriteriaForCandidate(candidateId);
    const defaultReviewer = window.state?.reviewer || "";

    const criteriaCardsHtml = criteria.map((crit, idx) => {
      const typeClass = crit.type === "required" ? "required" : "preferred";
      const typeLabel = crit.type === "required" ? "Wajib" : "Diutamakan";

      // Rating selector buttons 1..5
      const ratingOptionsHtml = [1, 2, 3, 4, 5].map((score) => {
        const rubricText = SCORE_RUBRIC[score];
        return `
          <label class="rating-btn-label" data-score="${score}" data-crit-id="${escapeHtml(crit.id)}">
            <input type="radio" name="score_${escapeHtml(crit.id)}" value="${score}" required>
            <span class="rating-score-num">${score}</span>
            <span class="rating-score-text" title="${escapeHtml(rubricText)}">${escapeHtml(rubricText)}</span>
          </label>
        `;
      }).join("");

      return `
        <div class="scorecard-criterion-card" data-criterion-id="${escapeHtml(crit.id)}" data-criterion-label="${escapeHtml(crit.label)}">
          <div class="scorecard-crit-header">
            <span class="scorecard-crit-title">${idx + 1}. ${escapeHtml(crit.label)}</span>
            <span class="scorecard-crit-type-badge ${typeClass}">${typeLabel}</span>
          </div>

          <div class="scorecard-rating-scale-wrap">
            <div class="scorecard-rating-selector-bar">
              ${ratingOptionsHtml}
            </div>
          </div>

          <div class="scorecard-crit-notes-wrap">
            <textarea
              class="scorecard-textarea scorecard-evidence-input"
              name="notes_${escapeHtml(crit.id)}"
              placeholder="Catatan bukti observasi kriteria ini (opsional)..."
              maxlength="1000"
            ></textarea>
          </div>
        </div>
      `;
    }).join("");

    containerEl.innerHTML = `
      <div class="scorecard-form-title-bar">
        <h5 class="scorecard-form-title">Formulir Scorecard Wawancara Terstruktur</h5>
        <button type="button" class="scorecard-form-close-btn" data-candidate-id="${escapeHtml(candidateId)}" aria-label="Tutup form">✕</button>
      </div>

      <form class="scorecard-input-form" data-candidate-id="${escapeHtml(candidateId)}">
        <!-- Reviewer and Role -->
        <div class="scorecard-form-reviewer-row">
          <div class="scorecard-field-group">
            <label class="scorecard-field-label">
              Nama Pewawancara <span class="required-star">*</span>
            </label>
            <input
              type="text"
              class="scorecard-input-text"
              name="reviewer"
              placeholder="Contoh: Budi Santoso"
              value="${escapeHtml(defaultReviewer)}"
              required
              maxlength="100"
            >
          </div>

          <div class="scorecard-field-group">
            <label class="scorecard-field-label">
              Peran Pewawancara <span class="required-star">*</span>
            </label>
            <div class="scorecard-role-toggle-group">
              <label class="scorecard-role-radio-label is-selected">
                <input type="radio" name="role" value="recruiter" checked>
                <span>Recruiter</span>
              </label>
              <label class="scorecard-role-radio-label">
                <input type="radio" name="role" value="hiring_manager">
                <span>Hiring Manager</span>
              </label>
            </div>
          </div>
        </div>

        <!-- STAR Guide Helper Banner -->
        <div class="scorecard-star-guide-banner">
          <div class="scorecard-star-guide-copy">
            <strong>🎯 Panduan Wawancara STAR:</strong> Butuh referensi pertanyaan perilaku berbasis Situation, Task, Action, Result untuk kriteria lowongan ini?
          </div>
          <button type="button" class="button button-secondary button-sm star-guide-btn" data-candidate-id="${escapeHtml(candidateId)}" title="Buka panduan pertanyaan wawancara STAR">
            <span class="btn-icon">🎯</span> Panduan Wawancara STAR
          </button>
        </div>

        <!-- Criteria List -->
        <div class="scorecard-field-label" style="margin-bottom:8px;">
          Penilaian Rubrik per Kriteria (Skala 1–5) <span class="required-star">*</span>
        </div>
        <div class="scorecard-form-criteria-list">
          ${criteriaCardsHtml}
        </div>

        <!-- Overall Recommendation -->
        <div class="scorecard-rec-selector-section">
          <label class="scorecard-field-label">
            Rekomendasi Akhir Wawancara <span class="required-star">*</span>
          </label>
          <div class="scorecard-rec-options-grid">
            <label class="rec-option-label is-selected advance">
              <input type="radio" name="overall_recommendation" value="advance" checked>
              <span>✓ Lanjut proses</span>
            </label>
            <label class="rec-option-label needs_info">
              <input type="radio" name="overall_recommendation" value="needs_info">
              <span>ℹ Perlu informasi</span>
            </label>
            <label class="rec-option-label not_selected">
              <input type="radio" name="overall_recommendation" value="not_selected">
              <span>✕ Tidak lanjut</span>
            </label>
          </div>
        </div>

        <!-- General Notes -->
        <div class="scorecard-general-notes-section">
          <label class="scorecard-field-label">Catatan &amp; Sintesis Keseluruhan (Opsional)</label>
          <textarea
            class="scorecard-textarea"
            name="notes"
            placeholder="Catatan umum mengenai kecocokan budaya, kedalaman teknis, dan kesiapan kandidat..."
            maxlength="2000"
          ></textarea>
        </div>

        <!-- Actions -->
        <div class="scorecard-form-actions">
          <button type="button" class="scorecard-btn-cancel" data-candidate-id="${escapeHtml(candidateId)}">
            Batal
          </button>
          <button type="submit" class="scorecard-btn-submit">
            <span>💾</span> Simpan Scorecard Wawancara
          </button>
        </div>
      </form>
    `;

    containerEl.classList.remove("hidden");
  }

  /**
   * Toggle visibility of form
   */
  function toggleForm(candidateId) {
    const formWrap = document.getElementById(`scorecard-form-${candidateId}`);
    const toggleBtn = document.querySelector(`.scorecard-toggle-form-btn[data-candidate-id="${candidateId}"]`);

    if (!formWrap) return;

    const isHidden = formWrap.classList.contains("hidden");
    if (isHidden) {
      renderForm(candidateId, formWrap);
      formWrap.classList.remove("hidden");
      if (toggleBtn) {
        toggleBtn.classList.add("active");
        toggleBtn.innerHTML = `<span class="btn-icon">✕</span> Tutup Form`;
      }
    } else {
      formWrap.classList.add("hidden");
      if (toggleBtn) {
        toggleBtn.classList.remove("active");
        toggleBtn.innerHTML = `<span class="btn-icon">✏️</span> Isi Scorecard`;
      }
    }
  }

  /**
   * Submit Scorecard Form
   */
  async function submitScorecard(formEl) {
    const candidateId = formEl.dataset.candidateId;
    if (!candidateId) return;

    const submitBtn = formEl.querySelector(".scorecard-btn-submit");
    if (submitBtn) submitBtn.disabled = true;

    try {
      const formData = new FormData(formEl);
      const reviewer = String(formData.get("reviewer") || "").trim();
      const role = String(formData.get("role") || "").trim();
      const overallRec = String(formData.get("overall_recommendation") || "").trim();
      const notes = String(formData.get("notes") || "").trim();

      if (!reviewer) {
        showToast("Nama pewawancara wajib diisi.");
        if (submitBtn) submitBtn.disabled = false;
        return;
      }

      // Collect criterion scores
      const criteriaCards = formEl.querySelectorAll(".scorecard-criterion-card");
      const criterionScores = [];
      let missingCrit = null;

      criteriaCards.forEach((card) => {
        const critId = card.dataset.criterionId;
        const critLabel = card.dataset.criterionLabel;
        const scoreInput = card.querySelector(`input[name="score_${critId}"]:checked`);
        const evidenceInput = card.querySelector(`textarea[name="notes_${critId}"]`);

        if (!scoreInput) {
          card.classList.add("has-error");
          if (!missingCrit) missingCrit = critLabel;
        } else {
          card.classList.remove("has-error");
          criterionScores.push({
            criterion_id: critId,
            criterion_label: critLabel,
            score: parseInt(scoreInput.value, 10),
            evidence_notes: evidenceInput ? evidenceInput.value.trim() : "",
          });
        }
      });

      if (missingCrit) {
        showToast(`Mohon pilih nilai skala 1–5 untuk kriteria: ${missingCrit}`);
        if (submitBtn) submitBtn.disabled = false;
        return;
      }

      const payload = {
        reviewer: reviewer,
        role: role,
        overall_recommendation: overallRec,
        notes: notes,
        criterion_scores: criterionScores,
      };

      const result = await requestApi(`/api/candidates/${encodeURIComponent(candidateId)}/scorecards`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      showToast(result.message || "Scorecard wawancara tersimpan.");

      // Store reviewer in state for future fills
      if (window.state) {
        window.state.reviewer = reviewer;
      }

      // Hide the form
      const formWrap = document.getElementById(`scorecard-form-${candidateId}`);
      if (formWrap) {
        formWrap.classList.add("hidden");
      }
      const toggleBtn = document.querySelector(`.scorecard-toggle-form-btn[data-candidate-id="${candidateId}"]`);
      if (toggleBtn) {
        toggleBtn.classList.remove("active");
        toggleBtn.innerHTML = `<span class="btn-icon">✏️</span> Isi Scorecard`;
      }

      // Refresh candidate scorecards display
      await loadCandidateScorecards(candidateId);

      // Trigger callback if registered
      if (typeof globalOptions.onScorecardSubmit === "function") {
        await globalOptions.onScorecardSubmit(candidateId, payload);
      }
    } catch (err) {
      showToast(err.message || "Gagal menyimpan scorecard.");
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  /**
   * Setup global event delegation for rating selectors, role toggles, recommendations, and forms
   */
  function init(options = {}) {
    globalOptions = Object.assign(globalOptions, options);

    // Event delegation on document body
    document.addEventListener("click", function (event) {
      // Toggle form button
      const toggleBtn = event.target.closest(".scorecard-toggle-form-btn");
      if (toggleBtn) {
        const candId = toggleBtn.dataset.candidateId;
        toggleForm(candId);
        return;
      }

      // Close form button or cancel button
      const closeBtn = event.target.closest(".scorecard-form-close-btn, .scorecard-btn-cancel");
      if (closeBtn) {
        const candId = closeBtn.dataset.candidateId;
        toggleForm(candId);
        return;
      }

      // Toggle breakdown list
      const breakdownBtn = event.target.closest(".scorecard-breakdown-toggle");
      if (breakdownBtn) {
        const scId = breakdownBtn.dataset.toggleBreakdown;
        const list = document.getElementById(`breakdown-list-${scId}`);
        if (list) {
          list.classList.toggle("hidden");
          breakdownBtn.querySelector("span").textContent = list.classList.contains("hidden")
            ? breakdownBtn.querySelector("span").textContent.replace("▴", "▾")
            : breakdownBtn.querySelector("span").textContent.replace("▾", "▴");
        }
        return;
      }
    });

    // Change event delegation for rating buttons, roles, recommendations
    document.addEventListener("change", function (event) {
      // Rating radio selection
      const ratingRadio = event.target.closest(".rating-btn-label input[type='radio']");
      if (ratingRadio) {
        const label = ratingRadio.closest(".rating-btn-label");
        const bar = label.closest(".scorecard-rating-selector-bar");
        const score = ratingRadio.value;
        const card = label.closest(".scorecard-criterion-card");

        bar.querySelectorAll(".rating-btn-label").forEach((lbl) => {
          lbl.className = "rating-btn-label";
        });
        label.classList.add(`selected-${score}`);
        if (card) card.classList.remove("has-error");
        return;
      }

      // Role radio selection
      const roleRadio = event.target.closest(".scorecard-role-radio-label input[type='radio']");
      if (roleRadio) {
        const group = roleRadio.closest(".scorecard-role-toggle-group");
        group.querySelectorAll(".scorecard-role-radio-label").forEach((lbl) => {
          lbl.classList.remove("is-selected");
        });
        roleRadio.closest(".scorecard-role-radio-label").classList.add("is-selected");
        return;
      }

      // Recommendation radio selection
      const recRadio = event.target.closest(".rec-option-label input[type='radio']");
      if (recRadio) {
        const grid = recRadio.closest(".scorecard-rec-options-grid");
        grid.querySelectorAll(".rec-option-label").forEach((lbl) => {
          lbl.classList.remove("is-selected");
        });
        recRadio.closest(".rec-option-label").classList.add("is-selected");
        return;
      }
    });

    // Form submit delegation
    document.addEventListener("submit", function (event) {
      const form = event.target.closest(".scorecard-input-form");
      if (form) {
        event.preventDefault();
        submitScorecard(form);
      }
    });
  }

  return {
    init: init,
    loadCandidateScorecards: loadCandidateScorecards,
    loadForCandidate: loadForCandidate,
    renderForm: renderForm,
    toggleForm: toggleForm,
    renderComparisonHeader: renderComparisonHeader,
    renderScorecardsList: renderScorecardsList,
    getRubric: function () {
      return SCORE_RUBRIC;
    },
  };
});
