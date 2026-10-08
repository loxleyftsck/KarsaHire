# M0 scope and governance decision record

**Status: Draft — not approved.** This record is a working template, not evidence of company authorization. Do not use real applicant data until the accountable owners have completed the decisions and approvals below.

Use it alongside [the architecture plan](../../KarsaHire-Architecture-Plan.md). Write `N/A` only with a reason. Keep approval names and dates blank until the named owner has reviewed and accepted the decision.

## Verified starting point — not governance decisions

- The current development instruction is to continue with synthetic or specifically authorized test data only. This does not authorize processing real applicant data.
- The user explicitly left pilot role, supported CV languages, and identity provider as `TBD`; development must remain local and use synthetic data until those decisions are made.
- The prototype is a local loopback app without authenticated users or SSO. Names entered for approvals/reviews are not verified identities.
- The bundled 32-CV evaluation corpus is synthetic and English-language. The app interface is Indonesian; supported applicant languages remain undecided.
- The OCR key, URL, and approved-origin allowlist are not configured in the reviewed environment. A local Windows OCR run now measures only the bundled synthetic English corpus; no approved OCR provider result, authorized applicant sample, or provider approval exists.
- M1 demo QC passed on synthetic data. M2 has offline evaluation and an empty adjudication template, but no independently reviewed and adjudicated sample.
- M2 annotation and ranking reports currently suppress metric outputs below five distinct candidate pseudonyms. This is one shared, fingerprinted provisional policy in `scripts/evaluation_policy.py`, not an approved privacy threshold.
- Local synthetic smoke on 2 October verifies deletion removes candidate-linked audit rows and leaves a job-level `candidate_deleted` event without a candidate ID; the stored actor is the generic value `user`. Deletion affects the active database only; existing backup snapshots can still contain the candidate and no expiry/purge or restore-reconciliation process is implemented. Production deletion, backup expiry, restore reconciliation, and audit-retention policy remain pending.

These facts describe the prototype only. They do not resolve the pending pilot role, intended user groups, authorized data source, language scope, identity provider, retention rules, or required approvals below.

## Product scope

| Decision | Agreed value | Owner | Status |
|---|---|---|---|
| First job family / pilot role | TBD — keputusan belum dibuat | HR product owner + hiring manager | Pending |
| Geography and supported CV languages | TBD — keputusan belum dibuat | HR product owner | Pending |
| Intended users and workflow | Recruiter, hiring manager, HRBP, other: | HR product owner | Pending |
| Intended use of match/evidence output |  | HR product owner + legal/privacy | Pending |
| ATS and approved integration method |  | HRIS/ATS owner + engineering | Pending |
| Decision authority and override process | Human decision owner: | HR product owner | Pending |
| Out-of-scope uses | No automatic rejection is the current design proposal; confirm or revise: | HR + legal/privacy | Pending |

## Data and model boundaries

| Decision | Agreed value | Owner | Status |
|---|---|---|---|
| Authorized CV/JD sources and rights |  | Data owner + legal/privacy | Pending |
| Evaluation sample source, consent/notice, size, and permitted purpose |  | Data owner + privacy | Pending |
| Approved criteria, rubric, weights, and version owner |  | Hiring manager + recruiter | Pending |
| Fields permitted for parsing and matching |  | HR + privacy | Pending |
| Sensitive attributes and proxy signals prohibited from ranking |  | Privacy + DEI/legal | Pending |
| Human correction and candidate dispute path |  | HR product owner | Pending |
| OCR service, region, retention, subprocessors, egress proxy/TLS inspection, and transfer approval |  | Security + privacy | Pending |
| Internal knowledge sources permitted for retrieval/Q&A |  | Knowledge owner + privacy | Pending |

## Identity, retention, and operating controls

| Decision | Agreed value | Owner | Status |
|---|---|---|---|
| Identity provider / SSO protocol and tenant boundary | TBD — keputusan belum dibuat | Identity/security owner | Pending |
| Role/group mapping and job-level access rules | TBD — review the [provider-neutral M3 access-control draft](../security/m3-access-control-draft.md) after intended user groups and job-membership source are selected | Identity/security owner + HR | Pending |
| Data residency, hosting environment, and database owner |  | Platform owner + security | Pending |
| Retention periods for source files, extracted fields, evidence, reviews, and audit |  | Privacy + records owner | Pending |
| Deletion triggers, backup expiry, and deletion verification |  | Privacy + platform owner | Pending |
| Audit access, fairness-monitoring data, demographic-data separation, and minimum reporting cell size | Current local implementation: provisional floor of 5 distinct candidates; approve or replace and define permitted report sharing | Privacy + DEI + security | Pending |
| Encryption/key owner, incident process, and breach notification path |  | Security owner | Pending |
| On-call owner, pilot pause authority, and rollback contact |  | Operations owner | Pending |

## Approval gate

Record an explicit decision, approver, and date for each required role. A blank, `Pending`, or verbal assumption is not approval.

| Required approver | Name | Decision (approve / revise / reject) | Date | Conditions or reference |
|---|---|---|---|---|
| HR product owner |  |  |  |  |
| Hiring manager for pilot role |  |  |  |  |
| Privacy / legal |  |  |  |  |
| Security / identity |  |  |  |  |
| ATS / data owner |  |  |  |  |
| Platform / operations owner |  |  |  |  |

M0 exits only after the pilot scope, data authority, human decision process, identity/access design, retention/deletion policy, risk owners, and required approvals are complete. M2 evaluation and M3 controls must then satisfy their own exit gates before shadow use.

The user's `TBD` response records unresolved scope; it is not an approval or authorization to process real applicant data.
