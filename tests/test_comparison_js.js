/**
 * Unit tests for web/comparison.js
 */

const assert = require("assert");
const fs = require("fs");
const path = require("path");

// Mock browser DOM environment
global.localStorage = {
  store: {},
  getItem(k) { return this.store[k] || null; },
  setItem(k, v) { this.store[k] = String(v); },
  removeItem(k) { delete this.store[k]; },
  clear() { this.store = {}; }
};

global.document = {
  body: {
    classList: {
      classes: new Set(),
      add(c) { this.classes.add(c); },
      remove(c) { this.classes.delete(c); },
      contains(c) { return this.classes.has(c); },
      toggle(c, force) {
        if (force === undefined) {
          if (this.classes.has(c)) this.classes.delete(c);
          else this.classes.add(c);
        } else if (force) {
          this.classes.add(c);
        } else {
          this.classes.delete(c);
        }
      }
    }
  },
  getElementById(id) {
    if (!this._elements) this._elements = {};
    if (!this._elements[id]) {
      this._elements[id] = {
        id,
        classList: {
          classes: new Set(),
          add(c) { this.classes.add(c); },
          remove(c) { this.classes.delete(c); },
          contains(c) { return this.classes.has(c); },
          toggle(c, force) {
            if (force) this.classes.add(c);
            else this.classes.delete(c);
          }
        },
        setAttribute(k, v) { this[k] = v; },
        querySelector(sel) { return null; },
        querySelectorAll(sel) { return []; },
        addEventListener() {},
        style: {},
      };
    }
    return this._elements[id];
  },
  querySelectorAll() { return []; },
  addEventListener() {}
};

global.window = {
  state: { reviewer: "Tester HM" },
  toast(msg) { global.lastToast = msg; }
};

const ComparisonModule = require("../web/comparison.js");

console.log("Testing ComparisonModule...");

// 1. Initial State
assert.strictEqual(ComparisonModule.isBlindMode(), false, "Initial blind mode should be false");

// 2. Blind Mode Toggle & Persistence
ComparisonModule.setBlindMode(true, true);
assert.strictEqual(ComparisonModule.isBlindMode(), true, "Blind mode should be active");
assert.strictEqual(global.localStorage.getItem("karsahire_blind_mode"), "true", "localStorage should persist blind mode");
assert.strictEqual(global.document.body.classList.contains("blind-mode"), true, "Body should have blind-mode class");
assert.strictEqual(global.lastToast, "Mode Review Buta aktif: Identitas dan avatar disamarkan.");

// Check candidate labeling under blind mode
const mockCand1 = { id: "cnd_abc1234", score: 85, status: "needs_review" };
const mockCand2 = { id: "cnd_def5678", score: 92, status: "advance" };
assert.strictEqual(ComparisonModule.getCandidateLabel(mockCand1, 0), "Kandidat Anonim A");
assert.strictEqual(ComparisonModule.getCandidateLabel(mockCand2, 1), "Kandidat Anonim B");

// Toggle off
ComparisonModule.setBlindMode(false, false);
assert.strictEqual(ComparisonModule.isBlindMode(), false);
assert.strictEqual(ComparisonModule.getCandidateLabel(mockCand1, 0), "Kandidat · 1234");
assert.strictEqual(ComparisonModule.getCandidateLabel(mockCand2, 1), "Kandidat · 5678");

// 3. Selection Testing (Max 3 candidates)
ComparisonModule.clearSelection();
assert.deepStrictEqual(ComparisonModule.getSelectedCandidateIds(), []);

const jobMock = {
  id: "job_test",
  title: "Backend Engineer",
  criteria: [
    { label: "Python", type: "required" },
    { label: "FastAPI", type: "required" },
    { label: "Docker", type: "preferred" }
  ],
  candidates: [
    {
      id: "cnd_1",
      score: 90,
      status: "needs_review",
      profile: { skills: ["Python", "FastAPI"], experience_years_mentioned: 4 },
      evidence: [
        { criterion: "Python", result: "matched", snippet: "Experienced in Python." },
        { criterion: "FastAPI", result: "matched", snippet: "FastAPI REST API." },
        { criterion: "Docker", result: "unknown" }
      ]
    },
    {
      id: "cnd_2",
      score: 70,
      status: "needs_review",
      profile: { skills: ["Python"], experience_years_mentioned: 2 },
      evidence: [
        { criterion: "Python", result: "matched", snippet: "Python script development." },
        { criterion: "FastAPI", result: "unknown" },
        { criterion: "Docker", result: "matched", snippet: "Docker containerization." }
      ]
    },
    {
      id: "cnd_3",
      score: 60,
      status: "needs_info",
      profile: { skills: ["Django"], experience_years_mentioned: 1 },
      evidence: [
        { criterion: "Python", result: "partial", snippet: "Learned Python in college." },
        { criterion: "FastAPI", result: "unknown" },
        { criterion: "Docker", result: "unknown" }
      ]
    },
    {
      id: "cnd_4",
      score: 50,
      status: "not_selected",
      profile: { skills: [] },
      evidence: []
    }
  ]
};

// Select 1
assert.strictEqual(ComparisonModule.toggleCandidateSelection("cnd_1", jobMock), true);
assert.strictEqual(ComparisonModule.isCandidateSelected("cnd_1"), true);
assert.strictEqual(ComparisonModule.getSelectedCandidateIds().length, 1);

// Select 2
assert.strictEqual(ComparisonModule.toggleCandidateSelection("cnd_2", jobMock), true);
assert.strictEqual(ComparisonModule.getSelectedCandidateIds().length, 2);

// Select 3
assert.strictEqual(ComparisonModule.toggleCandidateSelection("cnd_3", jobMock), true);
assert.strictEqual(ComparisonModule.getSelectedCandidateIds().length, 3);

// Attempt to select 4th (should be rejected by MAX_SELECTION rule)
assert.strictEqual(ComparisonModule.toggleCandidateSelection("cnd_4", jobMock), false);
assert.strictEqual(ComparisonModule.getSelectedCandidateIds().length, 3);
assert.strictEqual(global.lastToast, "Maksimal 3 kandidat untuk dibandingkan sekaligus.");

// Toggle existing candidate unselects it
assert.strictEqual(ComparisonModule.toggleCandidateSelection("cnd_3", jobMock), true);
assert.strictEqual(ComparisonModule.getSelectedCandidateIds().length, 2);
assert.strictEqual(ComparisonModule.isCandidateSelected("cnd_3"), false);

// 4. Modal Rendering and Divergence Analysis
const modalBackdrop = global.document.getElementById("comparison-modal-backdrop");
ComparisonModule.renderComparisonModal(jobMock);

assert.ok(modalBackdrop.innerHTML.includes("Perbandingan Kandidat Side-by-Side"), "Modal header rendered");
assert.ok(modalBackdrop.innerHTML.includes("cols-2"), "Rendered 2 columns comparison table");

// Candidate 1 has FastAPI matched, Candidate 2 has FastAPI unknown -> must be divergent!
assert.ok(modalBackdrop.innerHTML.includes("divergent-row"), "Found divergent row");
assert.ok(modalBackdrop.innerHTML.includes("⚡ Bukti vs Belum Ada") || modalBackdrop.innerHTML.includes("⚡ Beda Sinyal"), "Divergence badge displayed");
assert.ok(modalBackdrop.innerHTML.includes("cell-diff-matched"), "Cell diff matched highlighted");
assert.ok(modalBackdrop.innerHTML.includes("cell-diff-unknown"), "Cell diff unknown gap highlighted");

// Check quick review forms
assert.ok(modalBackdrop.innerHTML.includes('data-candidate-id="cnd_1"'), "Quick review form for cnd_1 present");
assert.ok(modalBackdrop.innerHTML.includes('data-candidate-id="cnd_2"'), "Quick review form for cnd_2 present");
assert.ok(modalBackdrop.innerHTML.includes("Simpan Review"), "Submit review button present");

console.log("All ComparisonModule tests passed successfully!");
