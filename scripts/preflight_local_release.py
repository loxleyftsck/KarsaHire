"""Verify the pinned local environment and synthetic-only release checks.

This is a pre-release check for the local prototype, not a production deploy
gate. Current check paths do not make external requests, and the child
environment omits application secrets; this script does not enforce host-level
network isolation. It prints only aggregate metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from synthetic_dataset_fingerprint import pinned_dataset_snapshot_sha256

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_DATASET_ID = "synthetic-cv-32"
SYNTHETIC_SAMPLE_COUNT = 32  # Mirrors server.SYNTHETIC_DATASET_SIZE without importing app config.
EXPECTED_SYNTHETIC_FIXTURE_PROFILE = {
    "samples_with_expected_labels": 32,
    "missing_given_names": 0,
    "duplicate_given_name_groups": 0,
    "samples_with_phone_labels": 32,
    "missing_phone_labels": 0,
    "phone_format_masks": 1,
}
SAFE_CHILD_ENV = (
    "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA",
)


def child_environment() -> dict[str, str]:
    """Do not propagate application secrets or arbitrary host configuration."""
    return {key: os.environ[key] for key in SAFE_CHILD_ENV if os.environ.get(key)}


def pinned_versions(requirements_path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)", line)
        if not match:
            raise ValueError("requirements.txt must contain only exact package pins.")
        name, expected = match.groups()
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise ValueError(f"Required package is not installed: {name}.") from error
        if installed != expected:
            raise ValueError(f"Installed version for {name} does not match requirements.txt.")
        versions[name] = installed
    if not versions:
        raise ValueError("requirements.txt does not contain any pinned packages.")
    return versions


def run_checked(
    command: list[str],
    timeout: int,
    *,
    step: str,
) -> subprocess.CompletedProcess[bytes]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=child_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"Local release-preflight step '{step}' could not complete.") from error
    if result.returncode != 0:
        raise ValueError(
            f"Local release-preflight step '{step}' failed (exit {result.returncode})."
        )
    return result


def expected_synthetic_manifest_sha256() -> str:
    manifest_path = ROOT / "data" / SYNTHETIC_DATASET_ID / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("The local synthetic dataset manifest could not be read.") from error
    if not isinstance(manifest, list) or len(manifest) != SYNTHETIC_SAMPLE_COUNT:
        raise ValueError("The local synthetic dataset manifest must contain exactly 32 samples.")
    sample_ids = [
        item.get("sample_id") if isinstance(item, dict) else None
        for item in manifest
    ]
    if any(not isinstance(sample_id, str) or not re.fullmatch(r"r[0-9]{5}", sample_id)
           for sample_id in sample_ids):
        raise ValueError("The local synthetic dataset manifest contains an invalid sample ID.")
    if len(set(sample_ids)) != SYNTHETIC_SAMPLE_COUNT:
        raise ValueError("The local synthetic dataset manifest contains duplicate sample IDs.")
    return hashlib.sha256(manifest_bytes).hexdigest()


def summarize_m2_report(
    raw_report: bytes,
    *,
    expected_requirements_sha256: str,
    expected_dependency_versions: dict[str, str],
    expected_python_version: str,
    expected_dataset_manifest_sha256: str,
    expected_dataset_snapshot_sha256: str,
) -> dict[str, object]:
    try:
        report = json.loads(raw_report.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("The aggregate M2 report was not valid JSON.") from error

    try:
        pipeline_version = report["pipeline_version"]
        dataset = report["dataset"]
        report_dataset_manifest_sha256 = report["dataset_manifest_sha256"]
        report_dataset_snapshot_sha256 = report["dataset_snapshot_sha256"]
        report_requirements_sha256 = report["requirements_sha256"]
        report_dependency_versions = report["dependency_versions"]
        report_python_version = report["python_version"]
        evaluations = report["evaluations"]
        fixture_profile = report["synthetic_fixture_profile"]
        format_round_trip = evaluations["format_round_trip"]
        text_label_overlap = evaluations["text_label_overlap"]
        ocr_preflight = evaluations["ocr_preflight"]
        format_samples_processed = format_round_trip["samples_processed"]
        format_matches = {
            name: format_round_trip[name]["text_match_count"]
            for name in ("txt", "docx", "text_pdf")
        }
        samples_processed = text_label_overlap["samples_processed"]
        ocr_requests_sent = ocr_preflight["ocr_requests_sent"]
        ocr_pipeline_version = ocr_preflight["pipeline_version"]
    except (KeyError, TypeError) as error:
        raise ValueError("The aggregate M2 report was missing required summary fields.") from error

    counts = [*format_matches.values(), samples_processed, format_samples_processed, ocr_requests_sent]
    if (
        not isinstance(pipeline_version, str)
        or not pipeline_version
        or not isinstance(report_requirements_sha256, str)
        or not isinstance(dataset, str)
        or not isinstance(report_dataset_manifest_sha256, str)
        or not isinstance(report_dataset_snapshot_sha256, str)
        or not re.fullmatch(r"[a-f0-9]{64}", report_dataset_snapshot_sha256)
        or not isinstance(report_dependency_versions, dict)
        or not isinstance(report_python_version, str)
        or not isinstance(fixture_profile, dict)
        or set(fixture_profile) != set(EXPECTED_SYNTHETIC_FIXTURE_PROFILE)
        or any(type(value) is not int for value in fixture_profile.values())
        or fixture_profile != EXPECTED_SYNTHETIC_FIXTURE_PROFILE
        or not isinstance(ocr_pipeline_version, str)
        or any(type(count) is not int or count < 0 for count in counts)
    ):
        raise ValueError("The aggregate M2 report contained invalid summary values.")
    if report_requirements_sha256 != expected_requirements_sha256:
        raise ValueError("The aggregate M2 report used a different requirements.txt revision.")
    if dataset != SYNTHETIC_DATASET_ID or report_dataset_manifest_sha256 != expected_dataset_manifest_sha256:
        raise ValueError("The aggregate M2 report used a different synthetic dataset manifest.")
    if report_dataset_snapshot_sha256 != expected_dataset_snapshot_sha256:
        raise ValueError("The aggregate M2 report used different synthetic dataset files.")
    if report_dependency_versions != expected_dependency_versions:
        raise ValueError("The aggregate M2 report used different installed dependency versions.")
    if report_python_version != expected_python_version:
        raise ValueError("The aggregate M2 report used a different Python runtime.")
    if ocr_pipeline_version != pipeline_version:
        raise ValueError("The aggregate M2 evaluations used different pipeline versions.")
    if format_samples_processed == 0 or samples_processed == 0:
        raise ValueError("The aggregate M2 report processed no synthetic samples.")
    if format_samples_processed != SYNTHETIC_SAMPLE_COUNT:
        raise ValueError("Local preflight requires all 32 bundled synthetic samples.")
    if format_samples_processed != samples_processed:
        raise ValueError("The aggregate M2 evaluations did not process the same sample count.")
    if any(count != format_samples_processed for count in format_matches.values()):
        raise ValueError("Local preflight requires complete text round-trip matches for every format.")
    if ocr_requests_sent != 0:
        raise ValueError("Local preflight must not send OCR requests.")

    return {
        "pipeline_version": pipeline_version,
        "format_text_matches": format_matches,
        "samples_processed": samples_processed,
        "dataset_snapshot_sha256": report_dataset_snapshot_sha256,
        "synthetic_fixture_profile": fixture_profile,
        "ocr_requests_sent": ocr_requests_sent,
    }


def build_summary() -> dict:
    expected_venv = (ROOT / ".venv").resolve()
    if sys.prefix == sys.base_prefix or Path(sys.prefix).resolve() != expected_venv:
        raise ValueError("Run this command with the repository's .venv Python interpreter.")

    requirements_path = ROOT / "requirements.txt"
    versions = pinned_versions(requirements_path)
    requirements_hash = hashlib.sha256(requirements_path.read_bytes()).hexdigest()
    dataset_manifest_hash = expected_synthetic_manifest_sha256()
    dataset_snapshot_hash = pinned_dataset_snapshot_sha256(ROOT / "data" / SYNTHETIC_DATASET_ID)
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    run_checked([sys.executable, "-m", "pip", "check"], timeout=30, step="pip check")
    run_checked(
        [sys.executable, str(ROOT / "scripts" / "smoke_test_local.py")],
        timeout=180,
        step="synthetic smoke suite",
    )
    report_result = run_checked(
        [sys.executable, str(ROOT / "scripts" / "build_m2_reproducibility_report.py")],
        timeout=90,
        step="aggregate M2 report",
    )
    m2 = summarize_m2_report(
        report_result.stdout,
        expected_requirements_sha256=requirements_hash,
        expected_dependency_versions=versions,
        expected_python_version=python_version,
        expected_dataset_manifest_sha256=dataset_manifest_hash,
        expected_dataset_snapshot_sha256=dataset_snapshot_hash,
    )

    return {
        "status": "local_preflight_passed",
        "production_ready": False,
        "network_mode": "external_requests_not_made_by_preflight; smoke_checks_use_loopback",
        "host_network_isolation_enforced": False,
        "python_version": python_version,
        "venv": str(expected_venv),
        "dependency_versions": versions,
        "requirements_sha256": requirements_hash,
        "m2_dataset_manifest_sha256": dataset_manifest_hash,
        "m2_dataset_snapshot_sha256": dataset_snapshot_hash,
        "m2_synthetic_fixture_profile": m2["synthetic_fixture_profile"],
        "pipeline_version": m2["pipeline_version"],
        "m2_format_text_matches": m2["format_text_matches"],
        "m2_samples_processed": m2["samples_processed"],
        "m2_ocr_preflight_requests_sent": m2["ocr_requests_sent"],
        "limitations": [
            "This checks only the local synthetic prototype and does not deploy or certify production readiness.",
            "M0 scope/approvals, SSO/RBAC, authorized adjudicated data, staging, managed services, and operational owners remain required.",
        ],
    }


def write_report_exclusive(output_path: Path, report: bytes) -> Path:
    """Publish a completed aggregate report atomically without replacing a prior run."""
    output = output_path.expanduser().resolve()
    if output.exists():
        raise FileExistsError("Report tujuan sudah ada; pilih nama file baru.")
    if not output.parent.is_dir():
        raise ValueError("Folder report harus sudah ada.")

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as report_file:
            report_file.write(report)
            report_file.flush()
            os.fsync(report_file.fileno())
        # Same-directory hard-link publication is atomic and refuses replacement.
        os.link(temporary, output)
        return output
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-output",
        type=Path,
        help="Optionally save this successful aggregate report to a new JSON file.",
    )
    args = parser.parse_args()
    try:
        report = (json.dumps(build_summary(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if args.report_output is not None:
            output = write_report_exclusive(args.report_output, report)
            print(f"Aggregate report saved to {output}", file=sys.stderr)
        sys.stdout.buffer.write(report)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Local release preflight failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
