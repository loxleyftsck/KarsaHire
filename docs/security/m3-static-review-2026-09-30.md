# M3 static security review — 2026-09-30

## Result

The standard Codex Security scan and an independent read-only baseline review found **no validated, reportable vulnerability** for the supplied local, synthetic-data-only scope.

- Scan ID: `0b29ff4b-4e0b-4bc1-9e50-cd51860abdf7`
- Snapshot: `codex-security-snapshot/v1:sha256:7ad40bd4a550c97ba7c1a021ba6b53b454dac55f871afc6f0ad6beedb199ca37`
- Reportable findings: 0
- Threat model: [project copy](threat-model-2026-09-30.md) and persistent Codex Security artifact `artifacts/threat_model.md`

## Reviewed surfaces

- Local HTTP binding, browser-origin checks, API routes, response headers, and SQLite query use
- Multipart uploads, TXT/PDF/DOCX/image parsing, OCR URL/secret handling, and resource limits
- Evidence persistence/redaction, audit events, candidate deletion, and local backup/restore utilities
- Browser rendering, pinned package versions, evaluation utilities, governance notes, and the local operations runbook

## Limits and remaining M3 work

The original scan and baseline review were static source/configuration/document reviews. They did not run tests or the application, inspect deployed configuration or host ACLs, verify an OCR provider, or validate real-data controls. A separate dated review of public upstream package advisory pages is recorded in [the dependency advisory review](dependency-advisory-review-2026-09-30.md); it is not an installed-environment or complete SBOM scan.

A visible synthetic-data-only notice, local Tesseract evaluator path, and server-generated request ID were added after the recorded scan snapshot; none is covered by its snapshot digest. Windows.Media.Ocr bridge, corpus runner, aggregate M2 report builder, explicit WinAnsi PDF round-trip fixture, targeted OCR preprocessing diagnostic, and local release-preflight helper were also added or updated after that scan. The bridge passes normalized synthetic PNG bytes over stdin to Windows PowerShell 5.1, runs with a bounded timeout and a filtered environment, and does not call the configured OCR API. The wrapper and release-preflight child-environment filters are covered by stubbed smoke checks; the preflight also verifies exact pins, runs the smoke suite and aggregate M2 report, and is restricted to local checks. An actual Windows OCR run covered one synthetic sample and all 32 synthetic PDFs (60 images), with no OCR text printed or persisted. This establishes only local execution behavior against synthetic references; Windows does not expose a stable OCR model fingerprint, and the run does not verify an approved provider or applicant-data flow. The UI notice is not an access-control mechanism. The completed scan remains valid for its recorded snapshot only; review and test the exact current build again before staging or production.

The local API has no authenticated users or per-user/job authorization; approver/reviewer names and roles are caller-supplied. Evidence redaction is heuristic. These remain prototype limitations and must be addressed before any broader pilot. M0 decisions are still pending, and this review is not formal privacy/security approval or production signoff.

Before M3 can close, define the pilot and IdP, implement and review SSO/RBAC and job-level access, approve privacy/retention and OCR-provider controls, and verify access isolation in the intended deployment.
