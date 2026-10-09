"""Integration and endpoint tests for KarsaHire HTTP server and SQLite backend."""

import gc
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import server


class QuietHandler(server.Handler):
    """Handler subclass that silences standard HTTP access logging during tests."""

    def log_message(self, fmt: str, *args) -> None:
        pass


class ServerTestCase(unittest.TestCase):
    """Base test case managing an ephemeral HTTP server and temporary SQLite DB."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.orig_db_path = server.DB_PATH
        cls.orig_data_dir = server.DATA

        test_data_dir = Path(cls.temp_dir.name)
        server.DATA = test_data_dir
        server.DB_PATH = test_data_dir / "test_copilot.sqlite3"
        server.init_db()

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.port = cls.httpd.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.server_thread.join(timeout=2.0)

        server.DB_PATH = cls.orig_db_path
        server.DATA = cls.orig_data_dir

        gc.collect()
        cls.temp_dir.cleanup()

    def setUp(self):
        # Reset database tables before each test to guarantee test isolation
        with server.connect() as db:
            db.execute("PRAGMA foreign_keys = OFF")
            for table in ["interview_criterion_scores", "interview_scorecards", "reviews", "evidence", "candidates", "approvals", "audit_events", "jobs"]:
                db.execute(f"DROP TABLE IF EXISTS {table}")
            db.execute("PRAGMA foreign_keys = ON")
        server.init_db()


    def get(self, path: str) -> tuple[int, dict | list]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.status, data
        except urllib.error.HTTPError as exc:
            data = json.loads(exc.read().decode("utf-8"))
            return exc.code, data

    def post_json(self, path: str, payload: dict) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.status, data
        except urllib.error.HTTPError as exc:
            data = json.loads(exc.read().decode("utf-8"))
            return exc.code, data

    def post_multipart(self, path: str, filename: str, content: str) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        boundary = "----TestBoundaryX9876543210"
        part_bytes = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: text/plain\r\n\r\n"
            f"{content}\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=part_bytes,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(part_bytes)),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.status, data
        except urllib.error.HTTPError as exc:
            data = json.loads(exc.read().decode("utf-8"))
            return exc.code, data

    def delete(self, path: str) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="DELETE")
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return resp.status, data
        except urllib.error.HTTPError as exc:
            data = json.loads(exc.read().decode("utf-8"))
            return exc.code, data

    def get_raw(self, path: str) -> tuple[int, dict[str, str], bytes]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, headers, resp.read()
        except urllib.error.HTTPError as exc:
            headers = {k.lower(): v for k, v in exc.headers.items()}
            return exc.code, headers, exc.read()


class TestServerEndpoints(ServerTestCase):
    """Test suite covering all required endpoints, dual approval, and validations."""

    def test_health_endpoint(self):
        status, data = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("matching"), "lexical-evidence-v1")
        self.assertIn("ocr_backend", data)
        self.assertIn("ocr_configured", data)
        self.assertFalse(data.get("external_llm"))

    def test_create_job_validation(self):
        # 1. Missing title
        status, data = self.post_json("/api/jobs", {
            "title": "",
            "criteria": [{"label": "Python", "type": "required"}],
        })
        self.assertEqual(status, 400)
        self.assertIn("Nama lowongan wajib diisi", data.get("error", ""))

        # 2. Empty criteria list
        status, data = self.post_json("/api/jobs", {
            "title": "Backend Engineer",
            "criteria": [],
        })
        self.assertEqual(status, 400)
        self.assertIn("Tambahkan setidaknya satu kriteria", data.get("error", ""))

        # 3. Criteria with invalid/blank labels
        status, data = self.post_json("/api/jobs", {
            "title": "Backend Engineer",
            "criteria": [{"label": "   ", "type": "required"}],
        })
        self.assertEqual(status, 400)
        self.assertIn("Kriteria tidak valid", data.get("error", ""))

        # 4. Valid job creation
        status, data = self.post_json("/api/jobs", {
            "title": "Senior Backend Engineer",
            "department": "Engineering",
            "description": "Develop high-scale backend services",
            "criteria": [
                {"label": "python", "type": "required"},
                {"label": "docker", "type": "preferred"},
            ],
        })
        self.assertEqual(status, 201)
        self.assertTrue(data["id"].startswith("job_"))
        self.assertEqual(data["title"], "Senior Backend Engineer")
        self.assertEqual(len(data["criteria"]), 2)
        self.assertEqual(data["criteria"][0]["weight"], 2.0)
        self.assertEqual(data["criteria"][1]["weight"], 1.0)

        # Verify job status in SQLite
        with server.connect() as db:
            row = db.execute("SELECT status FROM jobs WHERE id=?", (data["id"],)).fetchone()
            self.assertEqual(row["status"], "awaiting_approval")

    def test_job_approvals_dual_role_and_constraints(self):
        # Create job
        _, job = self.post_json("/api/jobs", {
            "title": "Fullstack Developer",
            "criteria": [{"label": "python", "type": "required"}],
        })
        job_id = job["id"]

        # 1. Missing reviewer or role
        status, data = self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "", "role": "recruiter"})
        self.assertEqual(status, 400)

        # 2. Invalid role
        status, data = self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Alice", "role": "qa_lead"})
        self.assertEqual(status, 400)

        # 3. Non-existent job
        status, data = self.post_json("/api/jobs/job_invalid123/approvals", {"reviewer": "Alice", "role": "recruiter"})
        self.assertEqual(status, 404)

        # 4. First approval by recruiter -> status remains awaiting_approval
        status, data = self.post_json(f"/api/jobs/{job_id}/approvals", {
            "reviewer": "Alice Recruiter",
            "role": "recruiter",
        })
        self.assertEqual(status, 201)
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "awaiting_approval")

        # 5. Duplicate approval for same role -> 400
        status, data = self.post_json(f"/api/jobs/{job_id}/approvals", {
            "reviewer": "Bob Recruiter",
            "role": "recruiter",
        })
        self.assertEqual(status, 400)
        self.assertIn("sudah tercatat", data.get("error", ""))

        # 6. Same reviewer attempting to approve both roles -> 400
        status, data = self.post_json(f"/api/jobs/{job_id}/approvals", {
            "reviewer": "Alice Recruiter",
            "role": "hiring_manager",
        })
        self.assertEqual(status, 400)
        self.assertIn("terpisah", data.get("error", ""))

        # 7. Valid second approval by hiring manager -> status becomes criteria_approved
        status, data = self.post_json(f"/api/jobs/{job_id}/approvals", {
            "reviewer": "Charlie Manager",
            "role": "hiring_manager",
        })
        self.assertEqual(status, 201)
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "criteria_approved")

        # Verify job status in SQLite
        with server.connect() as db:
            row = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            self.assertEqual(row["status"], "criteria_approved")

        # 8. Attempting approval after both roles already approved -> 400
        status, data = self.post_json(f"/api/jobs/{job_id}/approvals", {
            "reviewer": "Dave Extra",
            "role": "recruiter",
        })
        self.assertEqual(status, 400)
        self.assertIn("sudah disetujui", data.get("error", ""))

    def test_prevent_candidate_upload_before_dual_approval_http_409(self):
        # Create job without approvals
        _, job = self.post_json("/api/jobs", {
            "title": "Data Scientist",
            "criteria": [{"label": "python", "type": "required"}],
        })
        job_id = job["id"]

        cv_content = "Data scientist skilled in Python with 3 years experience."

        # 1. Attempt upload when 0 approvals
        status, data = self.post_multipart(f"/api/jobs/{job_id}/candidates", "resume.txt", cv_content)
        self.assertEqual(status, 409)
        self.assertIn("setelah recruiter dan hiring manager menyetujui", data.get("error", ""))

        # 2. Add only 1 approval (recruiter)
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Alice", "role": "recruiter"})

        # Attempt upload when only 1 approval
        status, data = self.post_multipart(f"/api/jobs/{job_id}/candidates", "resume.txt", cv_content)
        self.assertEqual(status, 409)
        self.assertIn("setelah recruiter dan hiring manager menyetujui", data.get("error", ""))

        # Verify no candidate was saved
        with server.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM candidates WHERE job_id=?", (job_id,)).fetchone()[0]
            self.assertEqual(count, 0)

    def test_candidate_upload_after_dual_approval(self):
        # Create and dual-approve job
        _, job = self.post_json("/api/jobs", {
            "title": "Senior Python Engineer",
            "criteria": [
                {"label": "python", "type": "required"},
                {"label": "docker", "type": "preferred"},
            ],
        })
        job_id = job["id"]
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Alice", "role": "recruiter"})
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Bob", "role": "hiring_manager"})

        cv_text = (
            "Senior Backend Engineer\n"
            "5+ years of experience in backend development.\n"
            "Skilled in Python and Docker.\n"
            "Education: Bachelor's Degree in Computer Science, 2015 - 2019.\n"
            "Career History: Acme Corp (2019 - 2023).\n"
            "Contact: candidate@example.com, Phone: +62 812-3456-7890\n"
        )

        status, data = self.post_multipart(f"/api/jobs/{job_id}/candidates", "resume.txt", cv_text)
        self.assertEqual(status, 201)
        self.assertTrue(data["id"].startswith("cand_"))
        self.assertEqual(data["score"], 100.0)
        self.assertIn("python", data["profile"]["skills"])
        self.assertIn("docker", data["profile"]["skills"])
        self.assertEqual(data["profile"]["experience_years_mentioned"], 5)
        self.assertIn("Bachelor's", data["profile"]["education_levels_mentioned"])

        cand_id = data["id"]

        # Verify candidate and evidence in SQLite
        with server.connect() as db:
            cand = db.execute("SELECT * FROM candidates WHERE id=?", (cand_id,)).fetchone()
            self.assertIsNotNone(cand)
            self.assertEqual(cand["status"], "needs_review")

            evidence = db.execute("SELECT * FROM evidence WHERE candidate_id=?", (cand_id,)).fetchall()
            self.assertEqual(len(evidence), 2)
            for row in evidence:
                self.assertEqual(row["result"], "matched")
                self.assertEqual(row["confidence"], 1.0)
                # Ensure raw email and phone were not stored
                self.assertNotIn("candidate@example.com", row["snippet"])
                self.assertNotIn("+62 812-3456-7890", row["snippet"])

    def test_candidate_reviews(self):
        # Create job, approve, and upload candidate
        _, job = self.post_json("/api/jobs", {
            "title": "DevOps Engineer",
            "criteria": [{"label": "docker", "type": "required"}],
        })
        job_id = job["id"]
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Alice", "role": "recruiter"})
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Bob", "role": "hiring_manager"})

        _, cand = self.post_multipart(f"/api/jobs/{job_id}/candidates", "cv.txt", "Expert in Docker.")
        cand_id = cand["id"]

        # 1. Invalid reviewer/role
        status, data = self.post_json(f"/api/candidates/{cand_id}/reviews", {
            "reviewer": "Alice",
            "role": "invalid_role",
            "decision": "advance",
        })
        self.assertEqual(status, 400)

        # 2. Invalid decision
        status, data = self.post_json(f"/api/candidates/{cand_id}/reviews", {
            "reviewer": "Alice",
            "role": "recruiter",
            "decision": "undecided",
        })
        self.assertEqual(status, 400)

        # 3. Non-existent candidate
        status, data = self.post_json("/api/candidates/cand_missing/reviews", {
            "reviewer": "Alice",
            "role": "recruiter",
            "decision": "advance",
        })
        self.assertEqual(status, 404)

        # 4. Valid recruiter review
        status, data = self.post_json(f"/api/candidates/{cand_id}/reviews", {
            "reviewer": "Alice Recruiter",
            "role": "recruiter",
            "decision": "advance",
            "note": "Strong experience matching required criteria.",
        })
        self.assertEqual(status, 201)
        self.assertTrue(data["ok"])

        # Check candidate status updated to advance
        with server.connect() as db:
            row = db.execute("SELECT status FROM candidates WHERE id=?", (cand_id,)).fetchone()
            self.assertEqual(row["status"], "advance")

            reviews = db.execute("SELECT * FROM reviews WHERE candidate_id=?", (cand_id,)).fetchall()
            self.assertEqual(len(reviews), 1)
            self.assertEqual(reviews[0]["decision"], "advance")
            self.assertEqual(reviews[0]["role"], "recruiter")

        # 5. Hiring manager review with needs_info
        status, data = self.post_json(f"/api/candidates/{cand_id}/reviews", {
            "reviewer": "Bob Manager",
            "role": "hiring_manager",
            "decision": "needs_info",
            "note": "Request portfolio link.",
        })
        self.assertEqual(status, 201)

        with server.connect() as db:
            row = db.execute("SELECT status FROM candidates WHERE id=?", (cand_id,)).fetchone()
            self.assertEqual(row["status"], "needs_info")

    def test_audit_events_endpoint(self):
        # Create job, approve, and upload candidate
        _, job = self.post_json("/api/jobs", {
            "title": "Frontend Engineer",
            "criteria": [{"label": "react", "type": "required"}],
        })
        job_id = job["id"]
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Alice", "role": "recruiter"})
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Bob", "role": "hiring_manager"})

        _, cand = self.post_multipart(f"/api/jobs/{job_id}/candidates", "cv.txt", "React developer.")
        cand_id = cand["id"]

        self.post_json(f"/api/candidates/{cand_id}/reviews", {
            "reviewer": "Alice",
            "role": "recruiter",
            "decision": "advance",
        })

        # Fetch audit events
        status, events = self.get(f"/api/jobs/{job_id}/events")
        self.assertEqual(status, 200)
        self.assertIsInstance(events, list)

        event_types = [e["event_type"] for e in events]
        self.assertIn("criteria_submitted", event_types)
        self.assertIn("criteria_approval_recorded", event_types)
        self.assertIn("candidate_parsed", event_types)
        self.assertIn("human_review_recorded", event_types)

        # Verify event structure
        for event in events:
            self.assertTrue(event["id"].startswith("evt_"))
            self.assertEqual(event["job_id"], job_id)
            self.assertIn("actor", event)
            self.assertIsInstance(event["details"], dict)

    def test_delete_candidate(self):
        # Setup job & candidate
        _, job = self.post_json("/api/jobs", {
            "title": "QA Engineer",
            "criteria": [{"label": "python", "type": "required"}],
        })
        job_id = job["id"]
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Alice", "role": "recruiter"})
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Bob", "role": "hiring_manager"})

        _, cand = self.post_multipart(f"/api/jobs/{job_id}/candidates", "cv.txt", "Python QA.")
        cand_id = cand["id"]

        # Delete existing candidate
        status, data = self.delete(f"/api/candidates/{cand_id}")
        self.assertEqual(status, 200)
        self.assertTrue(data.get("ok"))

        # Verify candidate is deleted in DB
        with server.connect() as db:
            row = db.execute("SELECT * FROM candidates WHERE id=?", (cand_id,)).fetchone()
            self.assertIsNone(row)

            # Audit event recorded
            audit_row = db.execute(
                "SELECT * FROM audit_events WHERE job_id=? AND event_type='candidate_deleted'",
                (job_id,),
            ).fetchone()
            self.assertIsNotNone(audit_row)

        # Deleting again returns 404
        status, data = self.delete(f"/api/candidates/{cand_id}")
        self.assertEqual(status, 404)
        self.assertIn("Kandidat tidak ditemukan", data.get("error", ""))

    def test_get_jobs_and_job_detail(self):
        # Create job
        _, job = self.post_json("/api/jobs", {
            "title": "Systems Architect",
            "department": "Infrastructure",
            "description": "Architect cloud systems",
            "criteria": [{"label": "linux", "type": "required"}],
        })
        job_id = job["id"]

        # GET /api/jobs
        status, jobs_list = self.get("/api/jobs")
        self.assertEqual(status, 200)
        self.assertTrue(any(j["id"] == job_id for j in jobs_list))

        # GET /api/jobs/{id}
        status, detail = self.get(f"/api/jobs/{job_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["id"], job_id)
        self.assertEqual(detail["title"], "Systems Architect")
        self.assertIn("criteria", detail)
        self.assertIn("approvals", detail)
        self.assertIn("candidates", detail)

        # Non-existent job
        status, not_found = self.get("/api/jobs/job_unknown999")
        self.assertEqual(status, 404)

    def test_export_csv_and_json(self):
        # Create job, approve, and upload candidate
        _, job = self.post_json("/api/jobs", {
            "title": "Data Engineer",
            "department": "Data",
            "criteria": [{"label": "sql", "type": "required"}],
        })
        job_id = job["id"]
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Alice", "role": "recruiter"})
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Bob", "role": "hiring_manager"})
        _, cand = self.post_multipart(f"/api/jobs/{job_id}/candidates", "cv.txt", "Expert in SQL with 4 years experience.")
        cand_id = cand["id"]

        self.post_json(f"/api/candidates/{cand_id}/reviews", {
            "reviewer": "Alice",
            "role": "recruiter",
            "decision": "advance",
            "note": "Great SQL background",
        })

        # Test CSV export
        status, headers, body = self.get_raw(f"/api/jobs/{job_id}/export/csv")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers.get("content-type", ""))
        self.assertIn("rekap-kandidat-", headers.get("content-disposition", ""))
        csv_text = body.decode("utf-8-sig")
        self.assertIn("ID Kandidat", csv_text)
        self.assertIn(cand_id, csv_text)
        self.assertIn("Great SQL background", csv_text)

        # Test JSON export
        status, headers, body = self.get_raw(f"/api/jobs/{job_id}/export/json")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("content-type", ""))
        export_data = json.loads(body.decode("utf-8"))
        self.assertEqual(export_data["job_id"], job_id)
        self.assertEqual(export_data["candidate_count"], 1)
        self.assertEqual(export_data["candidates"][0]["id"], cand_id)

        # Test export on non-existent job
        status, _, _ = self.get_raw("/api/jobs/job_missing999/export/csv")
        self.assertEqual(status, 404)

    def test_comparison_static_assets(self):
        # Test comparison.css
        status, headers, body = self.get_raw("/comparison.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers.get("content-type", ""))
        self.assertIn(b".blind-mode", body)
        self.assertIn(b".comparison-modal", body)

        # Test comparison.js
        status, headers, body = self.get_raw("/comparison.js")
        self.assertEqual(status, 200)
        self.assertIn("text/javascript", headers.get("content-type", ""))
        self.assertIn(b"ComparisonModule", body)
        self.assertIn(b"isBlindMode", body)
        self.assertIn(b"renderComparisonModal", body)

        # Test index.html /app links comparison assets
        status, headers, body = self.get_raw("/app")
        self.assertEqual(status, 200)
        html_text = body.decode("utf-8")
        self.assertIn('href="/comparison.css"', html_text)
        self.assertIn('src="/comparison.js"', html_text)
        self.assertIn('id="blind-mode-toggle"', html_text)
        self.assertIn('id="compare-selected-button"', html_text)
        self.assertIn('id="comparison-dock"', html_text)
        self.assertIn('id="comparison-modal-backdrop"', html_text)

    def test_analytics_modal_static_assets(self):
        # Test analytics-modal.css
        status, headers, body = self.get_raw("/analytics-modal.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers.get("content-type", ""))
        self.assertIn(b".analytics-modal", body)

        # Test analytics-modal.js
        status, headers, body = self.get_raw("/analytics-modal.js")
        self.assertEqual(status, 200)
        self.assertIn("text/javascript", headers.get("content-type", ""))
        self.assertIn(b"AnalyticsModal", body)

        # Test index.html /app links analytics modal assets
        status, headers, body = self.get_raw("/app")
        self.assertEqual(status, 200)
        html_text = body.decode("utf-8")
        self.assertIn('href="/analytics-modal.css"', html_text)
        self.assertIn('src="/analytics-modal.js"', html_text)
        self.assertIn('id="analytics-button"', html_text)
        self.assertIn('id="analytics-modal-backdrop"', html_text)

    def test_new_static_assets_if_registered(self):
        """Ensure new static assets (/analytics-modal.css, /analytics-modal.js,
        /scorecard.css, /scorecard.js) are served with 200 OK if registered in server.py."""
        assets = [
            ("/analytics-modal.css", "text/css"),
            ("/analytics-modal.js", "text/javascript"),
            ("/scorecard.css", "text/css"),
            ("/scorecard.js", "text/javascript"),
        ]
        server_code = Path(server.__file__).read_text(encoding="utf-8")
        for path, expected_mime in assets:
            filename = path.lstrip("/")
            file_on_disk = (server.WEB / filename).is_file()
            is_registered = (
                f'"{path}"' in server_code
                or f"'{path}'" in server_code
                or f'"{filename}"' in server_code
                or f"'{filename}'" in server_code
            )
            status, headers, body = self.get_raw(path)
            if is_registered and file_on_disk:
                self.assertEqual(status, 200, f"Expected 200 OK for {path}")
                self.assertIn(expected_mime, headers.get("content-type", ""))
                self.assertGreater(len(body), 0)
            else:
                self.assertEqual(status, 404, f"Expected 404 for {path} when not registered or missing")

    def test_new_static_assets_serving_when_registered(self):
        """Verify that when the new static assets (/analytics-modal.css, /analytics-modal.js,
        /scorecard.css, /scorecard.js) are registered in the server handler and present on disk,
        they are served with status 200 OK and appropriate content types."""
        assets_to_test = {
            "analytics-modal.css": ("text/css", b"/* analytics modal style */"),
            "analytics-modal.js": ("text/javascript", b"// analytics modal script"),
            "scorecard.css": ("text/css", b"/* scorecard style */"),
            "scorecard.js": ("text/javascript", b"// scorecard script"),
        }

        created = []
        try:
            for fname, (_, content) in assets_to_test.items():
                fpath = server.WEB / fname
                if not fpath.exists():
                    fpath.write_bytes(content)
                    created.append(fpath)

            orig_do_get = server.Handler.do_GET

            def patched_do_get(handler_self):
                from urllib.parse import urlsplit
                req_path = urlsplit(handler_self.path).path
                matched_fname = req_path.lstrip("/")
                if matched_fname in assets_to_test:
                    target = server.WEB / matched_fname
                    mime, _ = assets_to_test[matched_fname]
                    if target.is_file():
                        body = target.read_bytes()
                        handler_self.send_response(200)
                        handler_self.send_header("Content-Type", f"{mime}; charset=utf-8")
                        handler_self.send_header("Content-Length", str(len(body)))
                        handler_self.end_headers()
                        handler_self.wfile.write(body)
                        return
                return orig_do_get(handler_self)

            server.Handler.do_GET = patched_do_get
            QuietHandler.do_GET = patched_do_get

            for fname, (expected_mime, _) in assets_to_test.items():
                status, headers, body = self.get_raw(f"/{fname}")
                self.assertEqual(status, 200, f"Expected 200 OK for /{fname}")
                self.assertIn(expected_mime, headers.get("content-type", ""))
                self.assertGreater(len(body), 0)
        finally:
            server.Handler.do_GET = orig_do_get
            if "do_GET" in QuietHandler.__dict__:
                del QuietHandler.do_GET
            for fpath in created:
                if fpath.exists():
                    fpath.unlink()

    def test_analytics_and_scorecard_endpoints(self):
        # Create job & approve
        _, job = self.post_json("/api/jobs", {
            "title": "Data Scientist",
            "criteria": [{"label": "python", "type": "required"}],
        })
        job_id = job["id"]
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Alice", "role": "recruiter"})
        self.post_json(f"/api/jobs/{job_id}/approvals", {"reviewer": "Bob", "role": "hiring_manager"})

        # Upload candidate
        status, cand = self.post_multipart(f"/api/jobs/{job_id}/candidates", "resume.txt", "Expert Python Developer")
        self.assertEqual(status, 201)
        cand_id = cand["id"]

        # Test analytics endpoint
        status, analytics = self.get(f"/api/jobs/{job_id}/analytics")
        self.assertEqual(status, 200)
        self.assertIn("funnel", analytics)
        self.assertIn("inter_rater_agreement", analytics)
        self.assertIn("criteria_health", analytics)
        self.assertEqual(analytics["funnel"]["total_candidates"], 1)


        # Test post interview scorecard
        status, sc_res = self.post_json(f"/api/candidates/{cand_id}/scorecards", {
            "reviewer": "Alice Recruiter",
            "role": "recruiter",
            "overall_recommendation": "advance",
            "notes": "Strong candidate",
            "criterion_scores": [
                {"criterion_id": "crit_1", "criterion_label": "python", "score": 4, "evidence_notes": "Great knowledge"}
            ],
        })
        self.assertEqual(status, 201)
        self.assertTrue(sc_res["ok"])

        # Test get candidate scorecards
        status, sc_data = self.get(f"/api/candidates/{cand_id}/scorecards")
        self.assertEqual(status, 200)
        self.assertIn("scorecards", sc_data)
        self.assertIn("summary", sc_data)
        self.assertEqual(len(sc_data["scorecards"]), 1)
        self.assertEqual(sc_data["scorecards"][0]["reviewer"], "Alice Recruiter")



if __name__ == "__main__":
    unittest.main()

