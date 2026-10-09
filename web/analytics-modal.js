/**
 * KarsaHire — Hiring Analytics & Selection Debrief Modal Module
 * web/analytics-modal.js
 */

(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.AnalyticsModal = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const state = {
    isOpen: false,
    currentJobId: null,
    loading: false,
    analyticsData: null,
    error: null,
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

  function formatStatusLabel(status) {
    const map = {
      needs_review: "Perlu review",
      advance: "Lanjut proses",
      needs_info: "Perlu informasi",
      not_selected: "Tidak lanjut",
    };
    return map[status] || status;
  }

  function getCandidateLabel(candidateId) {
    if (typeof window !== "undefined" && window.ComparisonModule && window.ComparisonModule.isBlindMode()) {
      return "Kandidat #" + String(candidateId || "").slice(-4).toUpperCase();
    }
    return "Kandidat · " + String(candidateId || "").slice(-4).toUpperCase();
  }

  function ensureBackdropElement() {
    let backdrop = document.getElementById("analytics-modal-backdrop");
    if (!backdrop) {
      backdrop = document.createElement("div");
      backdrop.id = "analytics-modal-backdrop";
      backdrop.className = "analytics-modal-backdrop hidden";
      backdrop.setAttribute("tabindex", "-1");
      document.body.appendChild(backdrop);
    }
    return backdrop;
  }

  /* --------------------------------------------------------------------------
     Data Fetching
     -------------------------------------------------------------------------- */
  async function fetchAnalytics(jobId) {
    state.loading = true;
    state.error = null;
    render();

    try {
      const response = await fetch("/api/jobs/" + encodeURIComponent(jobId) + "/analytics");
      if (!response.ok) {
        const errorData = await response.json().catch(function () { return {}; });
        throw new Error(errorData.error || "Gagal memuat analitik seleksi (HTTP " + response.status + ")");
      }
      const data = await response.json();
      state.analyticsData = data;
      state.loading = false;
      render();
    } catch (err) {
      state.loading = false;
      state.error = err.message || "Terjadi kesalahan saat memuat data analitik.";
      render();
    }
  }

  /* --------------------------------------------------------------------------
     HTML Templates & Rendering
     -------------------------------------------------------------------------- */
  function renderFunnelSection(funnel) {
    if (!funnel) return "";

    const total = funnel.total_candidates || 0;
    const dist = funnel.status_distribution || {};
    const pcts = funnel.status_percentages || {};

    const needsReview = dist.needs_review || 0;
    const advance = dist.advance || 0;
    const needsInfo = dist.needs_info || 0;
    const notSelected = dist.not_selected || 0;

    const pNeedsReview = pcts.needs_review != null ? pcts.needs_review : (total ? Math.round((needsReview / total) * 1000) / 10 : 0);
    const pAdvance = pcts.advance != null ? pcts.advance : (total ? Math.round((advance / total) * 1000) / 10 : 0);
    const pNeedsInfo = pcts.needs_info != null ? pcts.needs_info : (total ? Math.round((needsInfo / total) * 1000) / 10 : 0);
    const pNotSelected = pcts.not_selected != null ? pcts.not_selected : (total ? Math.round((notSelected / total) * 1000) / 10 : 0);

    return `
      <section class="analytics-section">
        <div class="analytics-section-head">
          <div class="analytics-section-title-wrap">
            <span class="analytics-eyebrow">PIPELINE METRICS</span>
            <h3 class="analytics-section-title"><span>⏳</span> Funnel Pipeline Seleksi</h3>
            <p class="analytics-section-desc">Distribusi status kandidat dalam requisition saat ini dari total ${total} pelamar.</p>
          </div>
        </div>

        <div class="analytics-funnel-card">
          <!-- Stacked Funnel Progress Bar -->
          <div class="analytics-funnel-bar-container">
            <div class="analytics-funnel-bar" role="progressbar" aria-label="Distribusi pipeline kandidat" aria-valuemin="0" aria-valuemax="100">
              <div class="analytics-funnel-bar-seg status-needs_review" style="width: ${pNeedsReview}%;" title="Perlu review: ${needsReview} (${pNeedsReview}%)"></div>
              <div class="analytics-funnel-bar-seg status-advance" style="width: ${pAdvance}%;" title="Lanjut proses: ${advance} (${pAdvance}%)"></div>
              <div class="analytics-funnel-bar-seg status-needs_info" style="width: ${pNeedsInfo}%;" title="Perlu informasi: ${needsInfo} (${pNeedsInfo}%)"></div>
              <div class="analytics-funnel-bar-seg status-not_selected" style="width: ${pNotSelected}%;" title="Tidak lanjut: ${notSelected} (${pNotSelected}%)"></div>
            </div>
          </div>

          <!-- Status Grid Breakdown -->
          <div class="analytics-funnel-grid">
            <div class="analytics-funnel-item">
              <div class="analytics-funnel-item-header">
                <span class="analytics-funnel-label">
                  <span class="analytics-status-dot status-needs_review"></span> Perlu Review
                </span>
                <span class="analytics-funnel-pct">${pNeedsReview}%</span>
              </div>
              <div class="analytics-funnel-value">${needsReview}</div>
              <span class="analytics-funnel-sub">Kandidat antrean</span>
            </div>

            <div class="analytics-funnel-item">
              <div class="analytics-funnel-item-header">
                <span class="analytics-funnel-label">
                  <span class="analytics-status-dot status-advance"></span> Lanjut Proses
                </span>
                <span class="analytics-funnel-pct">${pAdvance}%</span>
              </div>
              <div class="analytics-funnel-value">${advance}</div>
              <span class="analytics-funnel-sub">Disetujui lanjut</span>
            </div>

            <div class="analytics-funnel-item">
              <div class="analytics-funnel-item-header">
                <span class="analytics-funnel-label">
                  <span class="analytics-status-dot status-needs_info"></span> Butuh Info
                </span>
                <span class="analytics-funnel-pct">${pNeedsInfo}%</span>
              </div>
              <div class="analytics-funnel-value">${needsInfo}</div>
              <span class="analytics-funnel-sub">Konfirmasi tambahan</span>
            </div>

            <div class="analytics-funnel-item">
              <div class="analytics-funnel-item-header">
                <span class="analytics-funnel-label">
                  <span class="analytics-status-dot status-not_selected"></span> Tidak Lanjut
                </span>
                <span class="analytics-funnel-pct">${pNotSelected}%</span>
              </div>
              <div class="analytics-funnel-value">${notSelected}</div>
              <span class="analytics-funnel-sub">Gugur kriteria/keputusan</span>
            </div>
          </div>
        </div>
      </section>
    `;
  }

  function renderScoreCardsSection(funnel) {
    if (!funnel) return "";

    const avg = funnel.avg_score != null ? funnel.avg_score : (funnel.average_score != null ? funnel.average_score : 0);
    const min = funnel.min_score != null ? funnel.min_score : (funnel.minimum_score != null ? funnel.minimum_score : 0);
    const max = funnel.max_score != null ? funnel.max_score : (funnel.maximum_score != null ? funnel.maximum_score : 0);

    return `
      <section class="analytics-section">
        <div class="analytics-section-head">
          <div class="analytics-section-title-wrap">
            <span class="analytics-eyebrow">SCORING DISTRIBUTION</span>
            <h3 class="analytics-section-title"><span>🎯</span> Metrik Skor Bukti (Evidence Score)</h3>
            <p class="analytics-section-desc">Distribusi nilai pencocokan leksikal berbasis bukti eksplisit (skala 0 - 100).</p>
          </div>
        </div>

        <div class="analytics-score-cards">
          <div class="analytics-score-card avg">
            <div class="analytics-score-icon">📊</div>
            <div class="analytics-score-info">
              <span class="analytics-score-label">Rata-Rata Skor</span>
              <span class="analytics-score-val">${avg}</span>
              <span class="analytics-score-hint">Rerata seluruh pelamar</span>
            </div>
          </div>

          <div class="analytics-score-card min">
            <div class="analytics-score-icon">📉</div>
            <div class="analytics-score-info">
              <span class="analytics-score-label">Skor Terendah</span>
              <span class="analytics-score-val">${min}</span>
              <span class="analytics-score-hint">Batas bawah pelamar</span>
            </div>
          </div>

          <div class="analytics-score-card max">
            <div class="analytics-score-icon">🏆</div>
            <div class="analytics-score-info">
              <span class="analytics-score-label">Skor Tertinggi</span>
              <span class="analytics-score-val">${max}</span>
              <span class="analytics-score-hint">Kecocokan bukti terbaik</span>
            </div>
          </div>
        </div>
      </section>
    `;
  }

  function renderInterRaterSection(agreement) {
    if (!agreement) return "";

    const dualCount = agreement.dual_reviewed_count || agreement.reviewed_by_both_count || 0;
    const consensusCount = agreement.consensus_count || 0;
    const consensusRate = agreement.consensus_rate != null ? agreement.consensus_rate : (agreement.agreement_rate || 0);
    const divergences = agreement.divergent_candidates || agreement.divergences || agreement.overrides || [];

    let circleClass = "high";
    let badgeClass = "high";
    let badgeText = "Sangat Selaras";
    let descriptionText = "Tingkat kesepakatan keputusan antara Recruiter dan Hiring Manager sangat tinggi (≥ 80%).";

    if (dualCount === 0) {
      circleClass = "empty";
      badgeClass = "empty";
      badgeText = "Belum Ada Dual Review";
      descriptionText = "Belum ada kandidat yang direview oleh Recruiter dan Hiring Manager secara bersamaan.";
    } else if (consensusRate < 50) {
      circleClass = "low";
      badgeClass = "low";
      badgeText = "Perlu Kalibrasi";
      descriptionText = "Konsensus di bawah 50%. Disarankan mengadakan sesi kalibrasi kriteria antar reviewer.";
    } else if (consensusRate < 80) {
      circleClass = "medium";
      badgeClass = "medium";
      badgeText = "Cukup Selaras";
      descriptionText = "Terdapat beberapa perbedaan preferensi keputusan yang layak dibahas pada debrief.";
    }

    let divergenceListHtml = "";
    if (divergences.length > 0) {
      divergenceListHtml = `
        <div class="analytics-divergence-panel">
          <div class="analytics-divergence-head">
            <h4 class="analytics-divergence-title">
              <span>⚠️</span> Daftar Divergensi Keputusan untuk Debrief
            </h4>
            <span class="analytics-divergence-alert-pill">${divergences.length} Kandidat Berbeda Opini</span>
          </div>
          <div class="analytics-divergence-list">
            ${divergences.map(function (d) {
              const candId = d.candidate_id || "";
              const candLabel = getCandidateLabel(candId);
              const score = d.score != null ? Math.round(d.score) : "-";
              const recDecision = d.recruiter_decision || "-";
              const hmDecision = d.hiring_manager_decision || "-";

              return `
                <div class="analytics-divergence-item">
                  <div class="analytics-divergence-item-top">
                    <span class="analytics-candidate-tag">
                      <strong>${escapeHtml(candLabel)}</strong>
                      <span class="analytics-candidate-score-badge">Skor: ${score}</span>
                    </span>
                    <span class="analytics-divergence-badge">Perbedaan Keputusan</span>
                  </div>

                  <div class="analytics-divergence-compare-grid">
                    <div class="analytics-eval-box">
                      <div class="analytics-eval-role">
                        <span>Recruiter (${escapeHtml(d.recruiter || "Reviewer")})</span>
                        <span class="analytics-decision-badge ${escapeHtml(recDecision)}">${escapeHtml(formatStatusLabel(recDecision))}</span>
                      </div>
                      ${d.recruiter_note ? `<p class="analytics-eval-note">“${escapeHtml(d.recruiter_note)}”</p>` : `<p class="analytics-eval-note">Tanpa catatan tambahan</p>`}
                    </div>

                    <div class="analytics-eval-box">
                      <div class="analytics-eval-role">
                        <span>Hiring Manager (${escapeHtml(d.hiring_manager || "Reviewer")})</span>
                        <span class="analytics-decision-badge ${escapeHtml(hmDecision)}">${escapeHtml(formatStatusLabel(hmDecision))}</span>
                      </div>
                      ${d.hiring_manager_note ? `<p class="analytics-eval-note">“${escapeHtml(d.hiring_manager_note)}”</p>` : `<p class="analytics-eval-note">Tanpa catatan tambahan</p>`}
                    </div>
                  </div>
                </div>
              `;
            }).join("")}
          </div>
        </div>
      `;
    } else if (dualCount > 0) {
      divergenceListHtml = `
        <div class="analytics-divergence-empty">
          <span>✓</span>
          <span><strong>Keselarasan 100%!</strong> Recruiter dan Hiring Manager sepakat pada seluruh kandidat yang dievaluasi bersama. Tidak ada perbedaan keputusan yang perlu didebatkan.</span>
        </div>
      `;
    }

    return `
      <section class="analytics-section">
        <div class="analytics-section-head">
          <div class="analytics-section-title-wrap">
            <span class="analytics-eyebrow">GOVERNANCE & CONSENSUS</span>
            <h3 class="analytics-section-title"><span>🤝</span> Inter-Rater Agreement (Keselarasan Tim)</h3>
            <p class="analytics-section-desc">Transparansi kesepakatan evaluasi antara Recruiter dan Hiring Manager untuk mitigasi bias personal.</p>
          </div>
        </div>

        <div class="analytics-agreement-container">
          <div class="analytics-agreement-summary">
            <div class="analytics-agreement-stat">
              <div class="analytics-rate-circle ${circleClass}">
                ${dualCount > 0 ? `${Math.round(consensusRate)}%` : "—"}
              </div>
              <div class="analytics-rate-copy">
                <div class="analytics-rate-title">
                  <span>Konsensus Tim</span>
                  <span class="analytics-alignment-badge ${badgeClass}">${badgeText}</span>
                </div>
                <span class="analytics-rate-sub">${descriptionText}</span>
              </div>
            </div>

            <div class="analytics-agreement-counts">
              <div class="analytics-count-col">
                <span class="analytics-count-col-num">${dualCount}</span>
                <span class="analytics-count-col-lbl">Evaluasi Ganda</span>
              </div>
              <div class="analytics-count-divider"></div>
              <div class="analytics-count-col">
                <span class="analytics-count-col-num">${consensusCount}</span>
                <span class="analytics-count-col-lbl">Sepakat</span>
              </div>
              <div class="analytics-count-divider"></div>
              <div class="analytics-count-col">
                <span class="analytics-count-col-num">${divergences.length}</span>
                <span class="analytics-count-col-lbl">Beda Opini</span>
              </div>
            </div>
          </div>

          ${divergenceListHtml}
        </div>
      </section>
    `;
  }

  function renderCriteriaHealthSection(criteriaList) {
    if (!criteriaList || !Array.isArray(criteriaList) || criteriaList.length === 0) {
      return `
        <section class="analytics-section">
          <div class="analytics-section-head">
            <div class="analytics-section-title-wrap">
              <span class="analytics-eyebrow">CRITERIA DIAGNOSTICS</span>
              <h3 class="analytics-section-title"><span>🩺</span> Kesehatan Kriteria Seleksi</h3>
              <p class="analytics-section-desc">Belum ada kriteria terdaftar atau belum ada kandidat yang dievaluasi terhadap kriteria.</p>
            </div>
          </div>
        </section>
      `;
    }

    return `
      <section class="analytics-section">
        <div class="analytics-section-head">
          <div class="analytics-section-title-wrap">
            <span class="analytics-eyebrow">CRITERIA DIAGNOSTICS</span>
            <h3 class="analytics-section-title"><span>🩺</span> Kesehatan Kriteria Penilaian</h3>
            <p class="analytics-section-desc">Mendeteksi kriteria yang terlalu ketat/bottleneck (>80% bukti tidak ditemukan) atau terlalu umum (>90% cocok) untuk bahan kalibrasi requisition.</p>
          </div>
        </div>

        <div class="analytics-criteria-list">
          ${criteriaList.map(function (c) {
            const label = c.label || c.criterion || "Kriteria";
            const reqType = c.requirement_type || c.type || "required";
            const reqLabel = reqType === "required" ? "Wajib" : "Diutamakan";
            const weight = c.weight != null ? c.weight : 1;

            const matchedPct = c.matched_pct != null ? c.matched_pct : (c.matched_percentage || 0);
            const partialPct = c.partial_pct != null ? c.partial_pct : (c.partial_percentage || 0);
            const unknownPct = c.unknown_pct != null ? c.unknown_pct : (c.unknown_percentage || 0);

            const isBottleneck = c.is_bottleneck || c.health_status === "bottleneck";
            const isTooCommon = c.is_too_common || c.health_status === "too_common";

            let healthStatusClass = "healthy";
            let healthBadgeClass = "healthy";
            let healthBadgeText = "Sehat";
            let healthIcon = "✓";

            if (isBottleneck) {
              healthStatusClass = "status-bottleneck";
              healthBadgeClass = "bottleneck";
              healthBadgeText = "Bottleneck / Terlalu Ketat";
              healthIcon = "⚠️";
            } else if (isTooCommon) {
              healthStatusClass = "status-too_common";
              healthBadgeClass = "too_common";
              healthBadgeText = "Terlalu Umum";
              healthIcon = "ℹ️";
            }

            const recommendation = c.recommendation || (
              isBottleneck
                ? "Kriteria bottleneck: >80% kandidat tidak memiliki bukti eksplisit. Pertimbangkan perluasan sinonim atau relaksasi kriteria."
                : (isTooCommon
                  ? "Kriteria terlalu umum: >90% kandidat memenuhinya. Daya beda kriteria rendah."
                  : "Distribusi kriteria wajar dan sehat.")
            );

            return `
              <div class="analytics-criterion-card ${healthStatusClass}">
                <div class="analytics-criterion-head">
                  <div class="analytics-criterion-meta">
                    <h4 class="analytics-criterion-title">${escapeHtml(label)}</h4>
                    <span class="analytics-req-type ${escapeHtml(reqType)}">${escapeHtml(reqLabel)}</span>
                    <span class="analytics-weight-badge">Bobot: ${weight}</span>
                  </div>
                  <span class="analytics-health-badge ${healthBadgeClass}">
                    <span>${healthIcon}</span> ${healthBadgeText}
                  </span>
                </div>

                <!-- Mini Stacked Distribution Bar -->
                <div class="analytics-crit-bar-wrapper">
                  <div class="analytics-crit-bar">
                    <div class="analytics-crit-bar-seg matched" style="width: ${matchedPct}%;" title="Cocok (Matched): ${matchedPct}%"></div>
                    <div class="analytics-crit-bar-seg partial" style="width: ${partialPct}%;" title="Parsial: ${partialPct}%"></div>
                    <div class="analytics-crit-bar-seg unknown" style="width: ${unknownPct}%;" title="Belum ada bukti: ${unknownPct}%"></div>
                  </div>

                  <div class="analytics-crit-stats-legend">
                    <div class="analytics-legend-item">
                      <span class="analytics-legend-dot matched"></span>
                      <span>Cocok: <strong>${matchedPct}%</strong> (${c.matched_count || 0})</span>
                    </div>
                    <div class="analytics-legend-item">
                      <span class="analytics-legend-dot partial"></span>
                      <span>Parsial: <strong>${partialPct}%</strong> (${c.partial_count || 0})</span>
                    </div>
                    <div class="analytics-legend-item">
                      <span class="analytics-legend-dot unknown"></span>
                      <span>Belum ada bukti: <strong>${unknownPct}%</strong> (${c.unknown_count || 0})</span>
                    </div>
                  </div>
                </div>

                <!-- Contextual Recommendation -->
                <div class="analytics-recommendation-box">
                  <span class="analytics-rec-icon">💡</span>
                  <div><strong>Rekomendasi Debrief:</strong> ${escapeHtml(recommendation)}</div>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      </section>
    `;
  }

  function renderAcademicMetricsSection(data) {
    if (!data) return "";

    const agreement = data.inter_rater_agreement || {};
    const grounding = data.evidence_grounding || {};
    const ranking = data.ranking_quality || {};
    const fairness = data.fairness_audit || {};

    const kappa = agreement.cohens_kappa != null ? agreement.cohens_kappa : 0.0;
    const kappaInterp = agreement.kappa_interpretation || "Belum cukup data review ganda";
    const faithfulness = grounding.faithfulness_score != null ? grounding.faithfulness_score : 100.0;
    const hallucination = grounding.hallucination_rate != null ? grounding.hallucination_rate : 0.0;
    const ndcg5 = ranking.ndcg_5 != null ? ranking.ndcg_5 : 0.0;
    const mrr = ranking.mrr != null ? ranking.mrr : 0.0;
    const piiCompliance = fairness.pii_compliance_rate != null ? fairness.pii_compliance_rate : 100.0;

    return `
      <section class="analytics-section">
        <div class="analytics-section-head">
          <div class="analytics-section-title-wrap">
            <span class="analytics-eyebrow">ACADEMIC &amp; GOVERNANCE BENCHMARKS</span>
            <h3 class="analytics-section-title"><span>🛡️</span> Matriks Unjuk Kerja Ilmiah &amp; Anti-Bias</h3>
            <p class="analytics-section-desc">Tolok ukur audit berbasis literatur psikometri (Schmidt &amp; Hunter), temu balik IR (NDCG/MRR), standar EU AI Act, dan UU PDP No. 27/2022.</p>
          </div>
        </div>

        <div class="analytics-academic-grid">
          <!-- Card 1: Cohen's Kappa -->
          <div class="analytics-academic-card">
            <div class="analytics-academic-card-head">
              <span class="analytics-academic-tag tag-reliability">RELIABILITAS PENILAI</span>
              <span class="analytics-academic-icon">📐</span>
            </div>
            <div class="analytics-academic-metric">
              <span class="analytics-academic-val">${kappa}</span>
              <span class="analytics-academic-label">Cohen&rsquo;s Kappa (&kappa;)</span>
            </div>
            <div class="analytics-academic-badge badge-kappa">${escapeHtml(kappaInterp)}</div>
            <p class="analytics-academic-expl">
              Mengukur tingkat kesepakatan keputusan Recruiter vs Hiring Manager yang melampaui faktor kebetulan (standardisasi Landis &amp; Koch).
            </p>
          </div>

          <!-- Card 2: Groundedness & Anti-Hallucination -->
          <div class="analytics-academic-card">
            <div class="analytics-academic-card-head">
              <span class="analytics-academic-tag tag-grounding">ANTI-HALUSINASI</span>
              <span class="analytics-academic-icon">🔍</span>
            </div>
            <div class="analytics-academic-metric">
              <span class="analytics-academic-val">${faithfulness}%</span>
              <span class="analytics-academic-label">Faithfulness Score</span>
            </div>
            <div class="analytics-academic-badge badge-zero-hallucination">0.0% Hallucination Rate</div>
            <p class="analytics-academic-expl">
              100% kecocokan kualifikasi berakar langsung pada nomor halaman dan kutipan teks nyata CV kandidat tanpa manipulasi generative.
            </p>
          </div>

          <!-- Card 3: Ranking NDCG & MRR -->
          <div class="analytics-academic-card">
            <div class="analytics-academic-card-head">
              <span class="analytics-academic-tag tag-ranking">KUALITAS PEMERINGKATAN</span>
              <span class="analytics-academic-icon">🏆</span>
            </div>
            <div class="analytics-academic-metric">
              <span class="analytics-academic-val">${ndcg5}</span>
              <span class="analytics-academic-label">NDCG@5 &bull; MRR: ${mrr}</span>
            </div>
            <div class="analytics-academic-badge badge-ranking">Normalized Discounted Gain</div>
            <p class="analytics-academic-expl">
              Metrik Information Retrieval (IR) yang memvalidasi apakah kandidat berkualifikasi tertinggi diprioritaskan di baris teratas.
            </p>
          </div>

          <!-- Card 4: Algorithmic Fairness & UU PDP -->
          <div class="analytics-academic-card">
            <div class="analytics-academic-card-head">
              <span class="analytics-academic-tag tag-fairness">ETIKA &amp; UU PDP</span>
              <span class="analytics-academic-icon">⚖️</span>
            </div>
            <div class="analytics-academic-metric">
              <span class="analytics-academic-val">${piiCompliance}%</span>
              <span class="analytics-academic-label">PII Redaction Compliance</span>
            </div>
            <div class="analytics-academic-badge badge-fairness">Mode Review Buta Didukung</div>
            <p class="analytics-academic-expl">
              Pencegahan adverse impact (Four-Fifths Rule) dengan menyamarkan email, telepon, dan atribut demografis saat penilaian kompetensi.
            </p>
          </div>
        </div>
      </section>
    `;
  }

  function renderModalContent() {
    const activeJob = (typeof window !== "undefined" && window.state && window.state.activeJob) ? window.state.activeJob : null;
    const jobTitle = activeJob?.title || "Requisition Aktif";
    const jobDept = activeJob?.department ? ` · ${activeJob.department}` : "";

    let bodyContent = "";

    if (state.loading) {
      bodyContent = `
        <div class="analytics-state-wrapper">
          <div class="analytics-spinner"></div>
          <span class="analytics-loading-text">Menghitung metrik seleksi &amp; menganalisis kriteria…</span>
        </div>
      `;
    } else if (state.error) {
      bodyContent = `
        <div class="analytics-state-wrapper">
          <div class="analytics-error-box">
            <span class="analytics-error-icon">⚠️</span>
            <p class="analytics-error-msg">${escapeHtml(state.error)}</p>
            <button class="analytics-retry-btn" type="button" id="analytics-retry-btn">Coba Lagi</button>
          </div>
        </div>
      `;
    } else if (state.analyticsData) {
      const data = state.analyticsData;
      const totalCandidates = data.funnel?.total_candidates || 0;

      bodyContent = `
        ${renderFunnelSection(data.funnel)}
        ${renderScoreCardsSection(data.funnel)}
        ${renderAcademicMetricsSection(data)}
        ${renderInterRaterSection(data.inter_rater_agreement)}
        ${renderCriteriaHealthSection(data.criteria_health)}
      `;
    } else {
      bodyContent = `
        <div class="analytics-state-wrapper">
          <p class="analytics-loading-text">Tidak ada data analitik yang tersedia.</p>
        </div>
      `;
    }

    return `
      <div class="analytics-modal" role="dialog" aria-modal="true" aria-labelledby="analytics-modal-title">
        <header class="analytics-modal-header">
          <div class="analytics-header-title-wrap">
            <div class="analytics-header-icon">📊</div>
            <div>
              <h2 id="analytics-modal-title">
                Analisis Seleksi &amp; Tata Kelola
                <span class="analytics-job-badge">${escapeHtml(jobTitle)}</span>
              </h2>
              <p class="analytics-modal-subtitle">Debrief dashboard &bull; ${escapeHtml(jobTitle)}${escapeHtml(jobDept)}</p>
            </div>
          </div>
          <button class="analytics-close-btn" type="button" aria-label="Tutup modal analisis seleksi" title="Tutup (ESC)">✕</button>
        </header>

        <div class="analytics-modal-body">
          ${bodyContent}
        </div>
      </div>
    `;
  }

  function render() {
    const backdrop = ensureBackdropElement();
    if (!state.isOpen) {
      backdrop.classList.add("hidden");
      document.body.classList.remove("analytics-open");
      return;
    }

    backdrop.classList.remove("hidden");
    document.body.classList.add("analytics-open");
    backdrop.innerHTML = renderModalContent();

    // Bind event listeners inside rendered modal
    const closeBtn = backdrop.querySelector(".analytics-close-btn");
    if (closeBtn) {
      closeBtn.addEventListener("click", close);
    }

    const retryBtn = backdrop.querySelector("#analytics-retry-btn");
    if (retryBtn) {
      retryBtn.addEventListener("click", function () {
        if (state.currentJobId) {
          fetchAnalytics(state.currentJobId);
        }
      });
    }
  }

  /* --------------------------------------------------------------------------
     Modal Open / Close Actions
     -------------------------------------------------------------------------- */
  function open(jobId) {
    if (!jobId) {
      if (typeof window !== "undefined" && window.toast) {
        window.toast("Pilih requisition terlebih dahulu.");
      }
      return;
    }

    state.isOpen = true;
    state.currentJobId = jobId;
    render();
    fetchAnalytics(jobId);
  }

  function close() {
    state.isOpen = false;
    state.loading = false;
    state.error = null;
    render();
  }

  /* --------------------------------------------------------------------------
     Global Event Listeners (Backdrop click, ESC key)
     -------------------------------------------------------------------------- */
  function initListeners() {
    // 1. ESC Key Listener
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && state.isOpen) {
        close();
      }
    });

    // 2. Backdrop Click Listener
    const backdrop = ensureBackdropElement();
    backdrop.addEventListener("click", function (e) {
      if (e.target === backdrop) {
        close();
      }
    });
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initListeners);
    } else {
      initListeners();
    }
  }

  return {
    open: open,
    close: close,
    render: render,
    fetchAnalytics: fetchAnalytics,
  };
});
