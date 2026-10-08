# KarsaHire threat model — 2026-09-30

**Baseline note:** findings and controls below describe the local source snapshot reviewed on 30 September 2026. Later changes are recorded in the follow-up section; they do not retroactively change the reviewed snapshot or imply M3 approval.

## Scope and deployment assumptions

This model covers the local prototype and synthetic-data-only use. The service binds to IPv4 loopback, serves a browser UI and API, stores records in local SQLite, and can optionally send image pages to an operator-configured OCR endpoint. Pilot role/job family, supported CV languages, and identity provider remain TBD. No production deployment topology or real-data authorization was supplied.

## Assets

- SQLite requisitions and criteria; asserted approver/reviewer names and roles; candidate IDs; derived profiles, lexical scores/statuses, evidence snippets and page references; human review decisions/notes; audit events.
- Uploaded source bytes, extracted text, and OCR content while processing in memory. The upload flow does not persist the complete source file or full text; saved evidence redaction is heuristic and does not establish de-identification.
- Optional OCR bearer credential, approved-origin configuration, endpoint, and any page images/transcriptions sent to that service.
- Database snapshots, local configuration, stdout logs, and process-local metrics.

## Trust boundaries and controls

1. **Browser/API client ↔ local HTTP service.** Loopback binding, loopback Host validation, and same-origin mutation checks reject common unintended network/browser traffic. They are not authentication or authorization. GET routes expose all local requisitions and candidate evidence. Approval/review names and roles are caller-supplied; there is no per-user or per-job ownership check.
2. **Uploaded bytes ↔ parser/OCR ↔ SQLite.** Request framing, body size/time, upload concurrency, PDF page and OCR-image count, image pixel count, DOCX expansion/member count, OCR request rate, and OCR response size are bounded. Malware scanning and parser process isolation are not implemented.
3. **Application ↔ local filesystem/database.** The DB is local SQLite at an operator-selected absolute path or the repository's `data/` default. Backup/restore validate integrity, avoid overwriting existing destinations, and reject targets inside the repository. Encryption, retention, deletion verification, and OS ACLs are not established by the app.
4. **Application ↔ optional OCR service.** Configuration requires HTTPS and an exact host/port allowlist, rejects redirects, and applies request/response bounds. No OCR credential or endpoint was configured in the reviewed environment. Provider approval, region, retention, secret rotation, and actual transmitted data are unverified.
5. **Local operator ↔ CSV/utilities/configuration.** Evaluation and maintenance tools read operator-selected local files. The adjudication evaluator emits aggregates and uses a provisional minimum-cell threshold; privacy approval and restricted output handling remain required.

## Attacker capabilities considered

A local client able to reach the listener can send arbitrary API requests and crafted document bytes. It can read local requisitions/evidence, invoke available mutations without verified identity, and consume bounded upload/parser/OCR capacity. A local operator can supply files, CSVs, configuration, and backup paths.

The review did not assume control of the OS account, launch environment, database file, OCR secret/allowlist, or trusted OCR provider. No remote exposure was evidenced because non-loopback binding is rejected. Port forwarding, a reverse proxy, and production deployment are outside this model until the target environment is selected.

## Security objectives

- Keep the prototype loopback-only and reject ordinary cross-site browser writes.
- Bound request, upload, parser, and OCR work.
- Avoid storing full uploaded CVs/text and redact common direct identifiers from persisted snippets/notes.
- Send OCR content and credentials only to an explicitly approved HTTPS origin without redirects.
- Delete active candidate/evidence/review data while preserving a bounded deletion audit event.
- Restrict snapshots and evaluation data; use synthetic or explicitly authorized inputs.
- Keep hiring decisions with human reviewers.

## Open controls before any broader pilot

- Decide M0 scope, authorized data sources, supported languages, retention, human decision process, and accountable owners.
- Implement verified SSO, role mapping, and per-job authorization; test for cross-user/job access.
- Replace asserted reviewer identity and define audit access, PII handling, deletion and backup expiry.
- Approve the OCR provider and its region, retention, secret management, and transfer path.
- Select and review the deployment topology, TLS, managed storage, operational monitoring, and rollback.

This model and the scan are source-review artifacts for the recorded local snapshot. They do not constitute formal privacy/security approval or production readiness.

## Follow-up to the 30 September baseline — 2 October 2026

- PDF parsing now runs in a separate resource-limited worker with a 256 MiB memory cap, a 30-second parent deadline, bounded decoded streams, bounded result size, and a restricted environment that excludes OCR credentials, endpoint, and proxy settings. The full local preflight and synthetic parser/OCR-stub checks are recorded in the [M3 QC addendum](m3-qc-addendum-2026-10-02.md). This is not host network isolation; TXT, DOCX, and direct image OCR parsing still run in the server process.
- A provider-neutral [M3 access-control draft](m3-access-control-draft.md) now lists proposed principal, tenant, job-membership, audit, and route-level authorization requirements. It is unapproved and not implemented. The API still accepts asserted reviewer names/roles and does not authorize by user, tenant, or job.
- The latest static scan snapshot predates the worker changes. A focused read-only code review found no concrete resource-bound bypass in the worker but did not replace a complete static scan, staging deployment review, or adversarial resource measurement.
- M0 scope, IdP, role mapping, authorized data, retention, OCR provider, and deployment boundary remain undecided. No applicant data was used.
