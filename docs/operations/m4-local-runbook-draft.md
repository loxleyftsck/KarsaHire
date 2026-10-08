# M4 local operations runbook — draft

**Status: prototype draft.** This is not an approved production runbook and does not authorize real applicant data. The app has no authenticated users, managed database, alert destination, or tested production cutover.

## Before an operational trial

Record the service owner, environment, database location, backup owner, backup retention, recovery-time and recovery-point targets, alert recipient, OCR service owner, secret-rotation procedure, and incident contact. Obtain M0 privacy/security approval and M3 identity/access controls before handling applicant data.

## Start and check the local service

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Optional: keep the local database outside the repository.
$env:RECRUITMENT_COPILOT_DB_PATH = "C:\KarsaHireLocal\copilot.sqlite3"
.\.venv\Scripts\python.exe .\server.py
```

The `.venv` directory is local to this checkout and ignored by Git. Recreate it from `requirements.txt` for a fresh checkout; do not copy a virtual environment between machines or Python versions.

In later commands, invoke `.\.venv\Scripts\python.exe` instead of `python` unless that environment is active in the current PowerShell session.

The database defaults to `data/copilot.sqlite3`. The optional override must be an absolute path; its parent folder is created when the database opens. If the app uses an override, run the backup tool in a shell with the same variable set or pass `--source` explicitly. Keep the file in a protected local folder and do not share one SQLite file across independent server processes.

The prototype binds only to `127.0.0.1`. In a second PowerShell window, check the probes:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/health/live
Invoke-RestMethod http://127.0.0.1:8765/api/health/ready
Invoke-RestMethod http://127.0.0.1:8765/api/metrics
```

Liveness only confirms that the process answers. Readiness returns HTTP 503 when SQLite cannot be queried, its schema version is unsupported, or the process is draining. Metrics are in-memory and process-local; they reset on restart. `upload_busy_rejections_total` counts upload parser backpressure. Request logs are JSON on stdout and omit client IP, raw URL, candidate ID, query string, and headers. Each request receives a server-generated ID in both `X-Request-ID` and the matching log entry; include that ID when reporting a local error. The ID is for correlation only and is not an authentication token.

Stop the local server with `Ctrl+C`. On `SIGINT` or `SIGTERM`, readiness switches to HTTP 503 while liveness stays HTTP 200. For the default five-second drain window, normal reads and mutations receive HTTP 503 while health probes remain available; then the listener stops accepting requests and waits for active handlers to finish. Set `RECRUITMENT_COPILOT_SHUTDOWN_GRACE_SECONDS` to an integer from 0 to 120 before startup to change the window. Synthetic smoke calls the same signal callback registered by `main()` using `SIGTERM`; it verifies the drain state and that an active synthetic request finishes before close. A Windows-only smoke test also starts `server.main()` in an isolated child console and sends an actual Ctrl+C console event; it checks SIGINT callback execution, clean process exit, and SQLite integrity/schema plus the synthetic lowongan after stop. The separate-process cutover check uses a sentinel to exercise the same drain callback. These local tests do not prove deployment-level connection draining or proxy/network behavior. Current source limits request headers to five seconds idle, 15 seconds total, and 64 KiB aggregate. Synthetic QC passed on 2 October 2026 using handler stubs and a loopback client with an accelerated total deadline; the live test confirms slow incremental headers are closed within the total deadline. Body reads are bounded to 60 seconds total and five seconds idle.

**Developer stop retest (5 October 2026):** a PTY-backed `write_stdin` control-character attempt closed the listener but did not capture `SIGINT diterima`; the process remained in that tool session past 20 seconds and was stopped by its owner. That input path did not establish delivery of a Windows console Ctrl+C event, so it is not evidence of a service shutdown defect. The follow-up isolated Windows test used `GenerateConsoleCtrlEvent(CTRL_C_EVENT)`, captured the SIGINT drain callback, exited with code 0, and preserved an integrity-valid schema-v1 synthetic database with one lowongan. The blank-page browser itself loaded successfully; browser-backed terminal input was not an OS-signal test.

If readiness fails, stop new use and preserve the database file. Do not delete it or change `PRAGMA user_version` manually. Review the application output and schema migration before restarting. The prototype has no alerting or automated recovery.

## Local release preflight

Before handing off a local build, use the repository virtual environment:

```powershell
$ReportPath = Join-Path .\data\evaluation ("local-release-preflight-{0}.json" -f (Get-Date -Format "yyyy-MM-dd-HHmmss"))
.\.venv\Scripts\python.exe .\scripts\preflight_local_release.py --report-output $ReportPath
```

The command requires this checkout’s `.venv`, verifies every exact package pin and `pip check`, runs the synthetic smoke suite, and rebuilds the aggregate M2 report. It validates the report schema and Python/dependency/manifest fingerprints, requires the full synthetic corpus snapshot to match its pinned digest, checks the fixture's aggregate identity-pattern profile, requires 32 bundled samples with valid unique manifest IDs and matching text round-trips, and fails if the report records any OCR requests or inconsistent pipeline versions. The snapshot hashes sorted relative file paths and file bytes, rejects symbolic links and paths outside the repository, and is checked before and after report generation. Failure messages name the preflight step without printing child-process output. Update the pin and expected profile only after reviewing the fixture's source and provenance. Current check paths do not make external requests; smoke traffic uses loopback, and application secrets are removed from child-process environments. The script does not enforce host-level network isolation or install a firewall. `local_preflight_passed` is not production approval; the report deliberately keeps `production_ready` false until M0, M3, staging, and operations gates are satisfied.

On success, `--report-output` atomically saves the aggregate JSON report and refuses to replace an existing file. Keep the report with the matching build/review record; it contains environment paths and aggregate synthetic metadata. On a missing pin, mismatched local fixture, failed smoke check, or timed-out prerequisite, the CLI prints a short error to stderr and returns a nonzero exit code.

## Snapshot and restore to a new file

Create a new snapshot while the server is running:

```powershell
$BackupFolder = Read-Host "Approved protected backup folder"
$SnapshotPath = Join-Path $BackupFolder "karsahire-snapshot.sqlite3"
.\.venv\Scripts\python.exe .\scripts\backup_database.py --output $SnapshotPath
```

The tool uses SQLite's online backup API, opens the source read-only, checks integrity, and refuses to overwrite an existing output file. Backup destinations inside the repository are rejected before a directory is created. Store snapshots outside the repository in an approved, access-controlled and encrypted location. A later deletion from the active database does not remove data from snapshots already created. Agree on backup expiry/purge and how deletions are reconciled after restore before any authorized applicant data is used.

The synthetic smoke suite exercises the online snapshot while a writer holds a partial, uncommitted transaction. The snapshot excludes that transaction, passes integrity check, and a later snapshot after commit contains the full transaction. This verifies SQLite snapshot consistency for the local helper; it does not establish production recovery-point/recovery-time targets, scheduled backup delivery, storage durability, or restore cutover readiness.

Restore a snapshot to a new path for inspection:

```powershell
$SnapshotPath = Read-Host "Snapshot file path"
$RestorePath = Read-Host "New restore file path"
.\.venv\Scripts\python.exe .\scripts\restore_database.py --source $SnapshotPath --target $RestorePath
```

The restore tool checks integrity and schema compatibility and refuses to overwrite an existing target. Restore destinations inside the repository are rejected before a directory is created. The command warns that a snapshot can reintroduce candidate data deleted after that snapshot was taken; do not use a restored database for operational data until an approved reconciliation procedure exists. For a local restore-path switch, restore into a new file, stop the app with `Ctrl+C`, set `RECRUITMENT_COPILOT_DB_PATH` to the new file, restart, and check `/api/health/ready`. To roll back locally, stop the app and restore the previous path value. Keep both files until an approved retention policy says otherwise. The synthetic smoke suite starts separate loopback service processes using each database path from the environment, verifies readiness and a source lowongan after cutover, and confirms a synthetic stage-only lowongan disappears after rollback. A local sentinel calls the registered drain callback so each child exits cleanly; this does not verify Windows Ctrl+C event delivery, exercise a human operator's command sequence, or establish staging recovery approval.

## Upload and OCR incidents

- HTTP 503 with `Retry-After: 2` means local upload capacity is full. Wait before retrying; do not run parallel retries.
- PDF parsing runs in a child worker capped at 256 MiB and 30 seconds. The worker receives no OCR credentials, endpoint, or proxy configuration; OCR requests are made by the parent only after the PDF worker returns bounded normalized images. If the service reports that a memory limit could not be applied, PDF parsing fails closed; on Windows, check whether the host permits assigning a child process to a Job Object. For timeout/resource-limit errors, avoid repeated retries of the same file; use a smaller synthetic fixture to diagnose and do not raise limits until measured in staging. TXT, DOCX, and direct image OCR still run in the server process.
- An OCR configuration error means image-only/scanned CV processing is unavailable. Do not copy a credential into source, command history, or logs. No OCR endpoint is configured in the reviewed environment.
- Python's default OCR opener honors environment proxy settings and Windows system proxy settings. The endpoint allowlist does not approve that route or any TLS inspection. Do not enable OCR until security/privacy owners approve the egress path and provider handling; the reviewed environment has no OCR endpoint configured. See the [Python `urllib.request` documentation](https://docs.python.org/3.12/library/urllib.request.html#urllib.request.ProxyHandler).
- If unauthorized or unexpected applicant data is processed, stop the service with `Ctrl+C`, restrict access to the SQLite database and snapshots, and notify the privacy/security owner through the organization's incident process. The organization must supply the approved contact and evidence-preservation rules before production.

## Release and incident controls still required

Before production, add an approved deployment target, TLS and reverse proxy, SSO/RBAC, managed database, encrypted/scheduled backup storage, restore cutover and rollback steps, external log/metric collection, alert thresholds and recipients, OCR secret management/rotation, incident contacts, and an on-call owner. Test these with the service owners in staging before opening any pilot.
