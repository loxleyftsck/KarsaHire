# KarsaHire — Explainable AI Recruitment Copilot

KarsaHire is a local portfolio prototype for collaborative hiring teams. It helps recruiters and hiring managers agree on criteria, parse CVs, review evidence-backed matches, and keep a human-owned audit trail. See [the architecture plan](KarsaHire-Architecture-Plan.md) for the broader RAG, ranking, explainability, and governance design.

## Run locally

Requires Python 3.10+. From PowerShell, install dependencies and start the app:

```powershell
python -m pip install -r requirements.txt
python .\server.py
```

Open <http://127.0.0.1:8765>. Select **Coba dengan data sintetis** for a sample requisition and fictional CV, or create a requisition then upload PDF, DOCX, TXT, PNG, or JPG. Text-based documents are parsed locally. PNG/JPG and scanned PDF pages are sent to the configured internal OCR API.

The server defaults to port 8765. Set `RECRUITMENT_COPILOT_PORT` before launching if that port is already occupied; each local instance uses the same `data/copilot.sqlite3` database.

The repository includes a 32-record synthetic test corpus in `data/synthetic-cv-32`, sourced from [sukhrobnurali/resume-parsing-vision](https://huggingface.co/datasets/sukhrobnurali/resume-parsing-vision) (CC BY 4.0). Attribute the dataset to its source when redistributing it. The source dataset card states that the CVs are synthetic and contain no real personal data. To load them, create/select a requisition, record both approvals, then click **Muat CV uji (0/32)**. The loader imports local text references, calculates evidence scores locally, and does not call OCR. Re-importing the same dataset into the same requisition skips candidates already loaded. The source PDFs remain available for manual OCR testing.

The local SQLite database and any OCR credentials are excluded from Git. A fresh checkout starts with an empty local database; run the app to create it.

## Database

KarsaHire uses SQLite at `data/copilot.sqlite3`. On startup, the server applies the canonical schema in [`database/schema.sql`](database/schema.sql), creating missing tables and indexes without replacing existing records. The database file is local-only and excluded from Git.

| Table | Purpose |
|---|---|
| `jobs` | Requisitions, descriptions, criteria, and approval status |
| `approvals` | Recruiter and hiring-manager approvals for each requisition |
| `candidates` | Parsed profile summary, ranking score, and review status |
| `evidence` | Per-criterion match result, confidence, and CV snippet |
| `reviews` | Human reviewer decision and note |
| `audit_events` | Append-style record of workflow actions |

## Enable the internal OCR API

Before starting the server, provide the API key through `RECRUITMENT_COPILOT_OCR_API_KEY` and the OpenAI-compatible base URL through `RECRUITMENT_COPILOT_OCR_API_URL` in the current process environment or an approved secret manager. Do not put credentials or internal service URLs in source files, command history, or the SQLite database. The model defaults to `ocr-lighton` and can be changed with `RECRUITMENT_COPILOT_OCR_MODEL`.

The app sends each uploaded image or embedded scan page as an OpenAI-compatible `messages[].content` array containing text and a base64 `image_url`; it does not send `enable_thinking`. It enforces up to 6 OCR requests per rolling minute and 5 simultaneous calls per local server process. A scanned PDF with more than six image pages is rejected before requests are sent. The rate guard is local to this server process; it cannot count OCR calls made by other clients using the same key.

The OCR endpoint was checked with one synthetic image. No real candidate CV was sent during that check. OCR page images leave the local process and go to the internal API; the source file and full extracted CV text are not stored locally, but derived profile fields and matching evidence snippets are.

## Current behavior

- Stores requisitions, extracted skill/education/experience hints, evidence snippets, reviewer decisions, and audit events in local SQLite under `data/`.
- Does not store the uploaded file or the full extracted CV text. Common contact fields are removed from evidence before persistence; this is a prototype safeguard, not a guarantee of complete de-identification.
- Gives each candidate an opaque ID. The score is a transparent lexical baseline: exact phrase evidence scores fully, partial token evidence scores partly, and missing text is “unknown”. It is not an LLM ranking model and should not make hiring decisions.
- The requisition Q&A panel performs retrieval-only search over the saved description and approved criteria. It does not generate answers with an LLM; retrieved lines are shown as sources.
- Decisions (`advance`, `needs information`, `not selected`) are recorded only through an explicit human reviewer action.
- Approver names and roles are recorded separately, but are not authenticated; dual approval demonstrates the workflow and does not replace company SSO or authorization controls.
- Binds to `127.0.0.1`; this app has no authentication or production hardening and must not be exposed to a network.

## API outline

- `POST /api/jobs` — save a requisition and proposed criteria.
- `POST /api/jobs/{id}/approvals` — record separate recruiter and hiring-manager approvals; the app blocks CV processing until both roles sign off.
- `GET /api/jobs`, `GET /api/jobs/{id}` — list requisitions or view candidate evidence.
- `POST /api/jobs/{id}/candidates` — parse a multipart TXT, PDF, DOCX, PNG, or JPG file.
- `POST /api/jobs/{id}/load-synthetic-data` — idempotently load the local 32-CV synthetic test set after criteria approval.
- `POST /api/jobs/{id}/ask` — retrieve relevant requisition text for an internal question.
- `POST /api/candidates/{id}/reviews` — record a human review.
- `DELETE /api/candidates/{id}` — delete a candidate and their evidence/reviews.
- `GET /api/jobs/{id}/events` — view the requisition audit trail.

Use synthetic or specifically authorized test data only. Before using real applicant data, replace the prototype safeguards with the approved company privacy, access-control, retention, audit, OCR, and fairness controls described in the architecture plan.
