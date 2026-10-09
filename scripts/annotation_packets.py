"""Prepare and merge blinded M2 reviewer packets without exposing model evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import random
import re
import secrets
import sys

import evaluate_adjudications as evaluator


ROOT = Path(__file__).resolve().parents[1]
CONTEXT_FIELDS = (
    "requisition_id", "candidate_id", "criteria_version", "criterion_id",
    "pipeline_version", "job_family", "cv_language", "source_format",
)
PACKET_FIELDS = ("run_id", *CONTEXT_FIELDS, "reviewer_role", "reviewer_label", "reference_label")
PACKET_ROLES = ("recruiter", "hiring_manager")
PREPARATION_BINDING_FORMAT = "karsahire-annotation-preparation-binding-v1"
RUN_ID_PATTERN = re.compile(r"[a-f0-9]{32}")
REVIEW_FIELDS = (
    "recruiter_reference_label", "hiring_manager_reference_label",
    "adjudicated_reference_label", "recruiter_label", "hiring_manager_label",
    "adjudicated_label",
)


def require_outside_repository(path: Path) -> Path:
    return evaluator.require_external_evaluation_path(
        path, ROOT, "Annotation CSVs and packet files"
    )


def parse_rows(raw: bytes, fields: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        if tuple(reader.fieldnames or ()) != fields:
            raise ValueError("CSV header does not match the required annotation packet format.")
        rows = list(reader)
    except (UnicodeError, csv.Error) as error:
        raise ValueError("An annotation CSV could not be read.") from error
    if not rows:
        raise ValueError("Annotation CSV has no rows.")
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("An annotation CSV contains missing or extra columns.")
    return rows


def read_rows(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    path = require_outside_repository(path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError("An annotation CSV could not be read.") from error
    return parse_rows(raw, fields)


def validate_context(rows: list[dict[str, str]], *, master: bool) -> list[tuple[str, str, str, str]]:
    keys = []
    criteria_versions: set[str] = set()
    pipeline_versions: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        for field in CONTEXT_FIELDS:
            if not (row.get(field) or "").strip():
                raise ValueError(f"Required annotation context is missing on row {row_number}.")
        for field in ("requisition_id", "candidate_id", "criterion_id"):
            if not evaluator.ANONYMOUS_ID_PATTERNS[field].fullmatch(row[field].strip()):
                raise ValueError(f"Anonymous IDs are invalid on row {row_number}.")
        if not evaluator.CRITERIA_VERSION.fullmatch(row["criteria_version"].strip()):
            raise ValueError(f"Criteria version is invalid on row {row_number}.")
        if not evaluator.PIPELINE_VERSION.fullmatch(row["pipeline_version"].strip()):
            raise ValueError(f"Pipeline version is invalid on row {row_number}.")
        if not evaluator.JOB_FAMILY.fullmatch(row["job_family"].strip()):
            raise ValueError(f"Job family is invalid on row {row_number}.")
        if not evaluator.CV_LANGUAGE.fullmatch(row["cv_language"].strip()):
            raise ValueError(f"CV language is invalid on row {row_number}.")
        if row["source_format"].strip() not in evaluator.SOURCE_FORMATS:
            raise ValueError(f"Source format is invalid on row {row_number}.")
        key = tuple(row[field].strip() for field in CONTEXT_FIELDS[:4])
        keys.append(key)
        criteria_versions.add(row["criteria_version"].strip())
        pipeline_versions.add(row["pipeline_version"].strip())
        if master:
            if row["model_result"].strip() not in evaluator.MODEL_LABELS:
                raise ValueError(f"Model result is invalid on row {row_number}.")
            evidence_ref = row["model_evidence_ref"].strip()
            if evidence_ref and not evaluator.ANONYMOUS_ID_PATTERNS["model_evidence_ref"].fullmatch(evidence_ref):
                raise ValueError(f"Evidence reference is invalid on row {row_number}.")
            page = row["model_evidence_page"].strip()
            if page and (not page.isdigit() or int(page) < 1 or not evidence_ref):
                raise ValueError(f"Evidence page is invalid on row {row_number}.")
            for field in REVIEW_FIELDS:
                if row[field].strip():
                    raise ValueError("Reviewer packets can only be prepared from a pristine, unlabeled master CSV.")
        else:
            role = row["reviewer_role"].strip()
            if role not in PACKET_ROLES:
                raise ValueError(f"Reviewer role is invalid on row {row_number}.")
            if row["reviewer_label"].strip() and row["reviewer_label"].strip() not in evaluator.LABELS:
                raise ValueError(f"Reviewer label is invalid on row {row_number}.")
            if row["reference_label"].strip() and row["reference_label"].strip() not in evaluator.REFERENCE_LABELS:
                raise ValueError(f"Reference label is invalid on row {row_number}.")
    if len(criteria_versions) != 1 or len(pipeline_versions) != 1:
        raise ValueError("A packet run must use one criteria and one pipeline version.")
    if len(keys) != len(set(keys)):
        raise ValueError("Annotation rows must have unique requisition/candidate/criterion keys.")
    return keys


def read_master(path: Path) -> tuple[list[dict[str, str]], str]:
    master_path = require_outside_repository(path)
    try:
        raw = master_path.read_bytes()
    except OSError as error:
        raise ValueError("The annotation master could not be read.") from error
    rows = parse_rows(raw, evaluator.FIELDS)
    validate_context(rows, master=True)
    return rows, hashlib.sha256(raw).hexdigest()


def write_preparation_binding(path: Path, master_sha256: str) -> str:
    output = require_outside_repository(path)
    run_id = secrets.token_hex(16)
    created = False
    try:
        with output.open("x", encoding="utf-8", newline="") as file:
            created = True
            json.dump({
                "format": PREPARATION_BINDING_FORMAT,
                "master_sha256": master_sha256,
                "run_id": run_id,
            }, file, indent=2)
            file.write("\n")
    except FileExistsError as error:
        raise ValueError("The annotation preparation binding already exists; use a new file for each run.") from error
    except Exception as error:
        if created:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(error, (OSError, ValueError)):
            raise ValueError("The annotation preparation binding could not be written.") from error
        raise
    return run_id


def validate_preparation_binding(path: Path, master_sha256: str) -> str:
    binding_path = require_outside_repository(path)
    try:
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("The private annotation preparation binding could not be read.") from error
    if (
        not isinstance(binding, dict)
        or set(binding) != {"format", "master_sha256", "run_id"}
        or binding.get("format") != PREPARATION_BINDING_FORMAT
        or not isinstance(binding.get("master_sha256"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", binding["master_sha256"])
        or not isinstance(binding.get("run_id"), str)
        or not RUN_ID_PATTERN.fullmatch(binding["run_id"])
    ):
        raise ValueError("The private annotation preparation binding is invalid.")
    if binding["master_sha256"] != master_sha256:
        raise ValueError("The annotation master changed after it was frozen for reviewer packets.")
    return binding["run_id"]


def freeze_master(master_path: Path, preparation_binding_path: Path) -> str:
    _, master_sha256 = read_master(master_path)
    return write_preparation_binding(preparation_binding_path, master_sha256)


def prepare_packet(
    master_path: Path,
    packet_path: Path,
    reviewer_role: str,
    preparation_binding_path: Path,
) -> int:
    if reviewer_role not in PACKET_ROLES:
        raise ValueError("Select recruiter or hiring_manager as the reviewer role.")
    rows, master_sha256 = read_master(master_path)
    run_id = validate_preparation_binding(preparation_binding_path, master_sha256)
    target = require_outside_repository(packet_path)
    if not target.parent.is_dir():
        raise ValueError("Create the access-controlled packet folder before preparing a packet.")
    if target.exists():
        raise ValueError("The output packet already exists; choose a new file path.")
    random.SystemRandom().shuffle(rows)
    created = False
    try:
        with target.open("x", encoding="utf-8", newline="") as file:
            created = True
            writer = csv.DictWriter(file, fieldnames=PACKET_FIELDS)
            writer.writeheader()
            for row in rows:
                packet = {"run_id": run_id}
                packet.update({field: row[field] for field in CONTEXT_FIELDS})
                packet.update({
                    "reviewer_role": reviewer_role,
                    "reviewer_label": "",
                    "reference_label": "",
                })
                writer.writerow(packet)
    except (OSError, UnicodeError, csv.Error) as error:
        if created:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        raise ValueError("The reviewer packet could not be written.") from error
    return len(rows)


def packet_map(
    path: Path,
    expected_role: str,
    expected_run_id: str,
) -> dict[tuple[str, str, str, str], dict[str, str]]:
    rows = read_rows(path, PACKET_FIELDS)
    keys = validate_context(rows, master=False)
    if any(row["reviewer_role"].strip() != expected_role for row in rows):
        raise ValueError("Reviewer packet role does not match the requested merge role.")
    if any(row["run_id"].strip() != expected_run_id for row in rows):
        raise ValueError("Reviewer packet run ID does not match the frozen annotation master.")
    return {key: row for key, row in zip(keys, rows)}


def merge_packets(
    master_path: Path,
    recruiter_path: Path,
    hiring_manager_path: Path,
    output_path: Path,
    preparation_binding_path: Path,
) -> int:
    master_resolved = require_outside_repository(master_path)
    recruiter_resolved = require_outside_repository(recruiter_path)
    manager_resolved = require_outside_repository(hiring_manager_path)
    if recruiter_resolved == manager_resolved:
        raise ValueError("Provide one separate packet for each reviewer role.")
    master_rows, master_sha256 = read_master(master_resolved)
    master_keys = validate_context(master_rows, master=True)
    run_id = validate_preparation_binding(preparation_binding_path, master_sha256)
    recruiter = packet_map(recruiter_resolved, "recruiter", run_id)
    hiring_manager = packet_map(manager_resolved, "hiring_manager", run_id)
    expected_keys = set(master_keys)
    if set(recruiter) != expected_keys or set(hiring_manager) != expected_keys:
        raise ValueError("Each reviewer packet must contain exactly the master rows.")
    for row, key in zip(master_rows, master_keys):
        for packet in (recruiter[key], hiring_manager[key]):
            if any(packet[field].strip() != row[field].strip() for field in CONTEXT_FIELDS):
                raise ValueError("Reviewer packet context does not match the master CSV.")
    output = require_outside_repository(output_path)
    if not output.parent.is_dir():
        raise ValueError("Create the access-controlled output folder before merging packets.")
    if output.exists():
        raise ValueError("The merged annotation CSV already exists; choose a new file path.")
    created = False
    try:
        with output.open("x", encoding="utf-8", newline="") as file:
            created = True
            writer = csv.DictWriter(file, fieldnames=evaluator.FIELDS)
            writer.writeheader()
            for row, key in zip(master_rows, master_keys):
                recruiter_row = recruiter[key]
                manager_row = hiring_manager[key]
                merged = dict(row)
                merged["recruiter_label"] = recruiter_row["reviewer_label"].strip()
                merged["recruiter_reference_label"] = recruiter_row["reference_label"].strip()
                merged["hiring_manager_label"] = manager_row["reviewer_label"].strip()
                merged["hiring_manager_reference_label"] = manager_row["reference_label"].strip()
                writer.writerow(merged)
    except (OSError, UnicodeError, csv.Error) as error:
        if created:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass
        raise ValueError("The merged annotation CSV could not be written.") from error
    return len(master_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze-master", help="Lock the pristine master before distributing packets.")
    freeze.add_argument("master_csv", type=Path)
    freeze.add_argument("--output", type=Path, required=True)
    prepare = commands.add_parser("prepare", help="Create one blind packet for one reviewer.")
    prepare.add_argument("master_csv", type=Path)
    prepare.add_argument("--reviewer", choices=PACKET_ROLES, required=True)
    prepare.add_argument("--preparation-binding", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    merge = commands.add_parser("merge", help="Merge the two completed reviewer packets.")
    merge.add_argument("master_csv", type=Path)
    merge.add_argument("recruiter_packet", type=Path)
    merge.add_argument("hiring_manager_packet", type=Path)
    merge.add_argument("--preparation-binding", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "freeze-master":
            run_id = freeze_master(args.master_csv, args.output)
            print(json.dumps({"status": "master_frozen", "run_id": run_id}, ensure_ascii=False))
            return 0
        elif args.command == "prepare":
            count = prepare_packet(
                args.master_csv, args.output, args.reviewer, args.preparation_binding
            )
            status = "reviewer_packet_prepared"
        else:
            count = merge_packets(
                args.master_csv, args.recruiter_packet, args.hiring_manager_packet,
                args.output, args.preparation_binding,
            )
            status = "reviewer_packets_merged"
        print(json.dumps({"status": status, "rows_processed": count}, ensure_ascii=False))
        return 0
    except (OSError, ValueError) as error:
        print(f"Annotation packet operation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
