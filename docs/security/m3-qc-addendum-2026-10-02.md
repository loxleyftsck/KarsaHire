# M3 QC addendum — 2 October 2026

**Status: M3 remains open.** KarsaHire stays local and synthetic-only. Pilot role/job family, CV languages, and IdP are TBD. This note does not authorize real applicant data or deployment.

## Static scan result

- Codex Security scan: `294bba37-2430-4098-a2e2-98593ef6e0f4`
- Reviewed snapshot: `codex-security-snapshot/v1:sha256:8fe98ba54204624f2c272f29b0caef348db5a2557df3bc0c80d3001a9be47026`
- Result: two low-severity, local-scope findings: an unbounded burst of loopback HTTP handler threads (CWE-770), and multipart parts being fully materialized before validation (CWE-400). The upload issue is reachable only when manual uploads are explicitly enabled.
- Method: static/offline review. The scan did not run the application or tests, access the network, or inspect live environment values, host ACLs, a production deployment, or a live OCR provider.
- Coverage is partial: `scripts/smoke_test_local.py` received keyword screening rather than a full source review. CSS, `.git`, `.venv`, and generated synthetic artifacts were outside the scan. The scan report and coverage record remain the source of detailed scope and limitations.

## Source changes after the scanned snapshot

`server.py` now limits concurrent HTTP handlers to 32 and rejects excess connections with HTTP 503. The multipart path now checks the outer content type and boundary, limits part headers to 16 KiB and 64 lines, accepts only one `file` form part, rejects nested multipart/message parts, and checks the closing boundary before constructing the MIME message tree.

These changes were made after the earlier snapshot digest above. They had not received targeted dynamic QC at that point.

## Current static re-review — 2 October 2026

- Codex Security scan: `ea1ec585-b586-4a46-8d0a-a2008d194e7c`
- Reviewed snapshot: `codex-security-snapshot/v1:sha256:e6706cc372257346e555ccada6076f5cb00ab031f7fef25d569bf3e0012e3e81`
- Result: 0 reportable findings in a partial static review. The handler limit and multipart preflight were reviewed in the new snapshot; source structure bounds body size, multipart parts, and MIME parsing before materialization.
- Method: read-only source/document review. No application, tests, HTTP requests, external network, real applicant data, deployment, host ACL, live database, runtime secrets, or OCR provider were inspected.
- Residual at the time of that scan: request headers had a five-second idle timeout without a total deadline. A same-machine client could occupy the bounded handler slots by slowly sending an incomplete header. This was not reportable for the loopback-only synthetic scope; source-level follow-up is recorded below.
- The 0-finding result does not close M3. SSO/RBAC, verified reviewer identity, privacy/retention, OCR-provider approval, staging controls, dynamic QC, and formal sign-off remain open.

## Follow-up source changes — 2 October 2026

The request reader now applies the existing five-second idle timeout, a 15-second total header deadline, and a 64 KiB aggregate-header limit. It stops the header deadline after the blank line and preserves buffered bytes for body reads. Stubbed checks passed for the absolute deadline, aggregate byte cap, and buffered-body handoff. A live loopback HTTP check also passed with accelerated settings (0.35-second total deadline, one-second idle timeout) while the client continued sending header lines every 50 ms. This does not verify a production reverse proxy or network path, and this change is not included in the Codex Security scan digest.

The OCR opener now installs an empty `ProxyHandler` before the redirect-blocking handler so Python cannot inherit a proxy from environment variables or Windows system settings. Targeted checks and the full synthetic smoke suite passed on 2 October using a stubbed transport; they checked the empty proxy configuration, redirect rejection, unsafe endpoint rejection, and response cap without making network requests. The local environment has no OCR endpoint configured, and this does not approve a direct egress route, TLS inspection behavior, or an OCR provider.

The M2 ranking evaluator and packet workflow were also updated after the scan to apply per-metric and complementary stratum suppression and hide model order during adjudication. The full local synthetic smoke suite passed on 2 October, including frozen-master binding, mixed-run rejection, model-blind adjudication, ranking metrics, complementary suppression for sparse 5/5/2 strata, annotation packets, and evaluator guards. These edits are not covered by the scan digest. The suite uses synthetic labels; no independently human-adjudicated evaluation or M0-approved target is available, so M2 remains open.

The local approval form now states that reviewer names and roles are entered manually and are not verified by an account; both fields reference that notice for assistive technology. This is a transparency change only: it does not authenticate users, enforce role mapping, or alter the caller-supplied identity stored by the API. The browser flow has not been rechecked, and this edit is not covered by the scan digest.

Source review of the existing local smoke suite shows synthetic redaction probes for an inline email, a North American-style phone, and a labeled birth date; a separate Indonesian labeled block covers a `+62` phone, email, birth/address, demographic labels, NIK, passport, and disability labels. Another corpus probe checks that names, contact details, birth dates, and addresses do not appear in evidence snippets. These are defined synthetic checks, not evidence that the current source revision passes them; they do not establish redaction across natural CV layouts or all M0 languages.

The evidence redactor now also removes explicit inline age forms such as `age: 32`, `berusia 31 tahun`, and `30 years old`, while preserving explicit experience-duration phrases such as `12 years of experience`. The redaction check passed in the full synthetic smoke suite on 2 October. The patterns do not infer age from dates or ambiguous durations and do not establish coverage across natural CV layouts or the undecided M0 languages.

Python's default `urllib.request.build_opener()` includes proxy handling and can use proxy environment variables or Windows system settings. The OCR origin allowlist constrains the configured destination URL but does not approve the proxy route or TLS inspection. The local environment has no OCR endpoint configured; before OCR is enabled, M0/M3 owners must approve the outbound route and proxy/TLS-inspection handling. See the [Python `ProxyHandler` documentation](https://docs.python.org/3.12/library/urllib.request.html#urllib.request.ProxyHandler).

Candidate deletion removes audit events linked to that candidate before deleting the row and leaves one generic job-level `candidate_deleted` event without the candidate pseudonym or caller-supplied reviewer name. The synthetic smoke suite now dynamically verifies that active-database behavior. This does not set a production audit-retention policy. Previously created snapshots can still contain the deleted candidate, and no backup expiry/purge or restore-reconciliation process exists yet. The smoke suite does not verify the browser confirmation disclosure, focus restoration, or live remaining-count announcement; those M5 checks remain open.

## Remaining gates

- M0 decisions for role/job family, CV languages, IdP, data authority, retention, deletion, and acceptable use remain TBD.
- The API still has no authenticated user identity or per-job authorization; approver/reviewer names remain caller supplied.
- A provider-neutral [M3 access-control design draft](m3-access-control-draft.md) is available for owner review; it does not select an IdP or implement authorization.
- Privacy and retention approval (including backup expiry and deletion-aware restore), trusted actor audit, OCR-provider review, staging controls, and formal security/privacy sign-off remain open.
- No live or real applicant data was used. `production_ready` remains `false`.

## Current source scan — 2 October 2026

- Codex Security scan: `52afa2ba-f864-4f4c-bbb3-07bdd6012f41`
- Reviewed snapshot: `codex-security-snapshot/v1:sha256:7aa1f1ef136b6414d0768731f0aadac2d3b5756f5d7bff278eaaa7bfd3bb0ce2`
- Result: one low-severity, medium-confidence static finding. `page.extract_text()` constructs PDF page text before the application enforces its 1,000,000-character budget (`server.py:858-866`). The local review found pypdf 6.19.0's default decoded-stream limit is 75,000,000 bytes. Manual uploads are off by default, access is loopback-only, and two uploads may run concurrently; no adversarial PDF or resource-impact measurement was run.
- Coverage is partial. The main API, UI rendering, OCR, storage/backup, and selected utility surfaces were reviewed. `.git/`, `.venv/`, and the generated synthetic corpus were excluded from product-source review; remaining evaluation/diagnostic scripts, the large smoke-test file, and CSS still need review.
- Method: read-only static review. The scan did not run the application or tests, access the network, use real applicant data, inspect deployed settings/host ACLs, or verify a live OCR provider.
- At the time of this snapshot the PDF resource finding was open; its out-of-snapshot remediation and synthetic verification are recorded below. This result does not close M3: identity, access, data-governance, retention, OCR-provider, and production controls remain open.

## PDF parser isolation follow-up — 2 October 2026

- PDF parsing now runs in `pdf_parser_worker.py`, a separate process. On Windows the parent assigns it to a Job Object before sending the document; the job caps aggregate and per-process memory at 256 MiB and kills child processes when the job closes. On POSIX the worker applies a 256 MiB address-space limit before importing the application parser. The parent stops a parse after 30 seconds. The worker receives only runtime environment variables; OCR credentials, endpoints, and proxy settings remain in the parent process.
- pypdf decoded streams are capped at 2 MiB for text extraction and 8 MiB while decoding OCR images. The worker enforces the existing 40-page and 1,000,000-character limits, caps embedded OCR images at six and their normalized aggregate at 32 MiB, and caps its serialized response at 48 MiB.
- Local Windows checks exercised worker startup, Job Object assignment/cleanup, timeout termination, oversized-output rejection, environment filtering with synthetic secret values, and ordinary synthetic text PDFs, page attribution, character and decoded-stream rejection, malformed PDFs, scanned-PDF OCR gating, image-count rejection, and a synthetic image-only PDF handoff to the OCR stub. After environment filtering, the synthetic TXT/DOCX/text-PDF evaluator matched text and profiles for 32/32 samples under pipeline `local-163cb9f352f87d967f26ba6129440b1ccc1746c880d4a49d0f9c8ebe4b`; page attribution also matched. The OCR stub test made no OCR request or network call; no live applicant data or deployment was used.
- This is source and synthetic-behavior evidence, not an adversarial memory/CPU measurement or production-host validation. The 256 MiB and 30-second budgets need review against staging workloads. These edits postdate the static-scan snapshot above; that scan does not cover the worker implementation. M3 remains open.
- The full local release preflight was rerun after the worker and environment-filtering changes. It passed the full smoke suite, dependency checks, and aggregate M2 checks; the report is [local-release-preflight-2026-10-02-160731.json](../../data/evaluation/local-release-preflight-2026-10-02-160731.json). It records `production_ready: false`, zero OCR requests, and that host network isolation is not enforced.
