# M3 access-control design — draft

**Status: proposal for M0/M3 owner review; not approved or implemented.** KarsaHire remains a loopback-only, synthetic-data prototype. Pilot role, intended user groups, tenant boundary, and IdP are TBD. This draft does not authorize real applicant data or select an identity provider.

## Current API facts

- The service accepts browser/API requests on loopback. Host, Origin, and the UI request marker are request-origin safeguards; they do not identify a person or authorize access.
- `GET /api/jobs` lists every local job. Job detail and event routes use a job ID but do not verify membership. Candidate reviews and deletion use a candidate ID without checking an actor's job membership.
- Approval and review requests accept caller-supplied reviewer names and role strings. Those values are not verified and must not become production authorization claims or trusted audit identity.
- Manual uploads are disabled by default. The built-in local demo is not a tenant or an authenticated session.

## Proposed authorization requirements

These are implementation requirements for owner review, not current controls:

1. Authenticate each human through the IdP and validate issuer, audience, signature, expiry, and the selected browser/API session design at a trusted server boundary.
2. Resolve the principal from a stable identity subject and an approved organization/tenant membership. Never derive identity, role, or tenant from request JSON, query parameters, a display name, or the UI marker.
3. Apply default-deny authorization to each route and each referenced object. Read routes must filter by the caller's tenant and job membership before returning job, candidate, evidence, review, or event data. A guessed ID must not reveal whether another tenant's record exists; owners must select the consistent 403/404 behavior.
4. Persist the validated actor subject in approvals, reviews, deletion events, and other audit records. Keep display names as presentation fields only. Distinct-person approval checks must use stable subject IDs rather than comparing typed names.
5. Separate business decisions from operations. A platform operator should not receive candidate-content access by default. Any break-glass content access requires an approved purpose, expiry, and immutable audit event.
6. Preserve CSRF protection for cookie-backed browser sessions. The existing same-origin check may remain as defense in depth, but cannot substitute for a session-bound CSRF token or authorization.
7. Give health probes only the minimum unauthenticated information needed by the selected deployment. Protect metrics and diagnostic routes according to the eventual hosting boundary.

## Draft action matrix

All roles and actions below need approval against the chosen workflow. The current product supports only recruiter and hiring-manager role labels; the other rows describe possible separation of duties for review.

| Proposed role | Read assigned job and candidate evidence | Edit job criteria | Approve criteria | Review candidates | Delete candidate | Read audit metadata |
|---|---:|---:|---:|---:|---:|---:|
| Recruiter | Yes | Before approval | Recruiter approval only | Assigned jobs | Pending policy | Assigned jobs, limited |
| Hiring manager | Yes | Before approval | Hiring-manager approval only | Assigned jobs | Pending policy | Assigned jobs, limited |
| Adjudicator | No by default; use pseudonymized packets | No | No | Evaluation labels only | No | No |
| Privacy/security auditor | No content by default | No | No | No | No | Approved scope, read-only |
| Platform operator | No content by default | No | No | No | No | Operational events only |

“Assigned job” requires an explicit, server-checked membership relation. A role alone must not grant access to every job. Candidate deletion authority, the ability to view notes, export access, and any HRBP role remain undecided.

## Route-level policy to implement after M0 decisions

| Route family | Minimum proposed check |
|---|---|
| `GET /api/jobs` | Return only jobs the authenticated principal may read. |
| `GET /api/jobs/{id}` and `/events` | Check tenant and job membership before loading child records. |
| `POST /api/jobs` | Require an approved job-creator role and tenant membership. |
| `POST /api/jobs/{id}/approvals` | Require the matching approver permission; bind the approval to the authenticated subject. |
| `POST /api/jobs/{id}/candidates`, synthetic/demo loaders | Require assigned-job processing permission; keep demo/synthetic routes unavailable to production tenants unless expressly approved. |
| `POST /api/candidates/{id}/reviews` | Resolve candidate to job, check membership and reviewer permission, bind the review to the authenticated subject. |
| `DELETE /api/candidates/{id}` | Require the owner-approved deletion permission and policy; audit the authenticated subject without retaining deleted candidate identifiers beyond approved policy. |
| `/api/metrics` and diagnostics | Restrict to the approved operations boundary; do not expose candidate data. |

## Decisions required before implementation

- Identity provider, tenant/org claim, stable subject claim, group claim, token/session transport, logout, and key rotation.
- Intended user groups and job-membership source, including whether membership comes from the ATS, IdP groups, or an approved local administration workflow.
- Final role-to-action mapping, who can assign roles, whether approvals require two distinct authenticated people, and candidate deletion authority.
- Cross-tenant response behavior, audit access, data export, service accounts, emergency access, and treatment of legacy local rows.
- Hosting boundary, reverse proxy/gateway trust, session cookie and CSRF design, health/metrics exposure, and identity-service outage behavior.

## Required verification before any shadow use

Add tests using synthetic tenants/jobs and signed test identities for: unauthenticated access; valid assigned access; wrong-role denial; cross-job and cross-tenant reads, writes, events, reviews, and deletes; forged body roles/names; expired, wrong-issuer, wrong-audience, and invalid-signature credentials; distinct-subject approvals; session/CSRF failures; and identity-provider outage. Verify both status codes and absence of protected data in response bodies and logs. Run the tests against the selected staging topology before M3 approval.

M3 remains open until the M0 owners select these decisions, the implementation and negative access tests pass, and security/privacy owners approve the deployed design. No authorization behavior should be inferred from this draft.
