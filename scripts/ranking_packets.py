"""Prepare independently blinded M2 ranking packets and merge reviewer ranks."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import re
import secrets
import sys
from collections import defaultdict
from pathlib import Path

import evaluate_rankings as evaluator


ROOT = Path(__file__).resolve().parents[1]
PACKET_FIELDS = (
    "run_id", "requisition_id", "candidate_id", "criteria_version", "job_family",
    "cv_language", "source_format", "reviewer_role", "reviewer_rank",
)
CONTEXT_FIELDS = PACKET_FIELDS[1:7]
ADJUDICATION_FIELDS = (
    "run_id",
    *CONTEXT_FIELDS,
    "recruiter_rank",
    "hiring_manager_rank",
    "adjudicated_rank",
)
BINDING_FORMAT = "karsahire-ranking-master-binding-v3"
PREPARATION_BINDING_FORMAT = "karsahire-ranking-preparation-binding-v1"
RUN_ID_PATTERN = re.compile(r"[a-f0-9]{32}")
REVIEWERS = {"recruiter": "recruiter_rank", "hiring_manager": "hiring_manager_rank"}


def restricted_path(path: Path) -> Path:
    return evaluator.require_external_evaluation_path(
        path, ROOT, "Ranking masters, reviewer packets, and merged files"
    )


def read_csv_bytes(path: Path) -> bytes:
    path = restricted_path(path)
    try:
        return path.read_bytes()
    except OSError as error:
        raise ValueError("A ranking CSV could not be read.") from error


def parse_csv(raw: bytes, fields: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if tuple(reader.fieldnames or ()) != fields:
            raise ValueError("CSV header does not match the required ranking format.")
        rows = list(reader)
    except (UnicodeError, csv.Error) as error:
        raise ValueError("A ranking CSV could not be read.") from error
    if not rows or any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("Ranking CSV is empty or contains missing/extra columns.")
    return rows


def read_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    return parse_csv(read_csv_bytes(path), fields)


def read_master(path: Path) -> tuple[list[dict[str, str]], str]:
    raw = read_csv_bytes(path)
    rows = parse_csv(raw, evaluator.FIELDS)
    return rows, hashlib.sha256(raw).hexdigest()


def validate_master(rows: list[dict[str, str]], *, must_be_unreviewed: bool) -> dict[tuple[str, str], dict[str, str]]:
    records = {}
    by_requisition: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row_number, row in enumerate(rows, start=2):
        for field in evaluator.FIELDS:
            row[field] = (row.get(field) or "").strip()
        for field in ("requisition_id", "candidate_id"):
            if not evaluator.ID_PATTERNS[field].fullmatch(row[field]):
                raise ValueError(f"Anonymous {field} is invalid on row {row_number}.")
        if not evaluator.CRITERIA_VERSION_PATTERN.fullmatch(row["criteria_version"]):
            raise ValueError(f"criteria_version is invalid on row {row_number}.")
        if not evaluator.VERSION_PATTERN.fullmatch(row["pipeline_version"]):
            raise ValueError(f"pipeline_version is invalid on row {row_number}.")
        if not evaluator.JOB_FAMILY_PATTERN.fullmatch(row["job_family"]):
            raise ValueError(f"job_family is invalid on row {row_number}.")
        if not evaluator.LANGUAGE_PATTERN.fullmatch(row["cv_language"]):
            raise ValueError(f"cv_language is invalid on row {row_number}.")
        if row["source_format"] not in evaluator.SOURCE_FORMATS:
            raise ValueError(f"source_format is invalid on row {row_number}.")
        for field in ("recruiter_rank", "hiring_manager_rank", "adjudicated_rank"):
            if must_be_unreviewed and row[field]:
                raise ValueError("Prepare packets from a pristine master with blank reviewer/adjudication ranks.")
        row["model_rank"] = str(evaluator.rank_value(row["model_rank"], "model_rank", row_number))
        key = (row["requisition_id"], row["candidate_id"])
        if key in records:
            raise ValueError(f"Duplicate requisition/candidate row at line {row_number}.")
        records[key] = row
        by_requisition[row["requisition_id"]].append(row)

    for requisition_rows in by_requisition.values():
        count = len(requisition_rows)
        ranks = sorted(int(row["model_rank"]) for row in requisition_rows)
        if count < 2 or ranks != list(range(1, count + 1)):
            raise ValueError("Every requisition needs at least two candidates and a complete frozen model order.")
        if len({row["job_family"] for row in requisition_rows}) != 1:
            raise ValueError("Each requisition must use one job_family.")
        if len({row["criteria_version"] for row in requisition_rows}) != 1:
            raise ValueError("A requisition cannot mix criteria versions.")
    if len({row["criteria_version"] for row in records.values()}) != 1:
        raise ValueError("A ranking run must use one criteria_version.")
    if len({row["pipeline_version"] for row in records.values()}) != 1:
        raise ValueError("A ranking run must use one pipeline_version.")
    return records


def freeze_master(master_path: Path, preparation_binding_path: Path) -> str:
    """Create an operator-only immutable lock before distributing reviewer packets."""
    rows, master_sha256 = read_master(master_path)
    validate_master(rows, must_be_unreviewed=True)
    return write_preparation_binding(preparation_binding_path, master_sha256)


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    output = restricted_path(path)
    created = False
    try:
        with output.open("x", encoding="utf-8", newline="") as file:
            created = True
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
    except FileExistsError as error:
        raise ValueError("Output file already exists; choose a new path to preserve the original packet.") from error
    except Exception as error:
        if created:
            output.unlink(missing_ok=True)
        if isinstance(error, (OSError, csv.Error, ValueError)):
            raise ValueError("Ranking output could not be written.") from error
        raise


def reviewer_ranks_digest(reviewer_ranks: dict[str, dict[tuple[str, str], int]]) -> str:
    canonical = {
        reviewer: [
            [requisition_id, candidate_id, rank]
            for (requisition_id, candidate_id), rank in sorted(ranks.items())
        ]
        for reviewer, ranks in sorted(reviewer_ranks.items())
    }
    payload = json.dumps(canonical, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_binding(
    path: Path, master_sha256: str, reviewer_ranks_sha256: str, run_id: str
) -> None:
    output = restricted_path(path)
    created = False
    try:
        with output.open("x", encoding="utf-8", newline="") as file:
            created = True
            json.dump({
                "format": BINDING_FORMAT,
                "master_sha256": master_sha256,
                "reviewer_ranks_sha256": reviewer_ranks_sha256,
                "run_id": run_id,
            }, file, indent=2)
            file.write("\n")
    except FileExistsError as error:
        raise ValueError("The operator binding file already exists; choose a new path.") from error
    except Exception as error:
        if created:
            output.unlink(missing_ok=True)
        if isinstance(error, (OSError, ValueError)):
            raise ValueError("The operator binding file could not be written.") from error
        raise


def write_preparation_binding(path: Path, master_sha256: str) -> str:
    output = restricted_path(path)
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
        raise ValueError("The preparation binding already exists; use a new file for each frozen ranking run.") from error
    except Exception as error:
        if created:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(error, (OSError, ValueError)):
            raise ValueError("The preparation binding could not be written.") from error
        raise
    return run_id


def read_binding_json(path: Path, expected_format: str, expected_keys: set[str]) -> dict[str, str]:
    binding_path = restricted_path(path)
    try:
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("The private operator binding file could not be read.") from error
    if (
        not isinstance(binding, dict)
        or set(binding) != expected_keys
        or binding.get("format") != expected_format
        or not isinstance(binding.get("master_sha256"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", binding["master_sha256"])
        or not isinstance(binding.get("run_id"), str)
        or not RUN_ID_PATTERN.fullmatch(binding["run_id"])
    ):
        raise ValueError("The private ranking binding file is invalid.")
    return binding


def validate_preparation_binding(path: Path, master_sha256: str) -> str:
    binding = read_binding_json(
        path,
        PREPARATION_BINDING_FORMAT,
        {"format", "master_sha256", "run_id"},
    )
    if binding["master_sha256"] != master_sha256:
        raise ValueError("The ranking master changed after its order was frozen for reviewer packets.")
    return binding["run_id"]


def validate_binding(path: Path, master_sha256: str) -> tuple[str, str]:
    binding = read_binding_json(
        path,
        BINDING_FORMAT,
        {"format", "master_sha256", "reviewer_ranks_sha256", "run_id"},
    )
    if (
        not isinstance(binding.get("reviewer_ranks_sha256"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", binding["reviewer_ranks_sha256"])
    ):
        raise ValueError("The private operator binding file is invalid.")
    if binding["master_sha256"] != master_sha256:
        raise ValueError("The frozen ranking master changed after reviewer packets were prepared.")
    return binding["reviewer_ranks_sha256"], binding["run_id"]


def prepare(
    master_path: Path,
    reviewer: str,
    output_path: Path,
    preparation_binding_path: Path,
) -> None:
    if reviewer not in REVIEWERS:
        raise ValueError("Select recruiter or hiring_manager as the reviewer role.")
    rows, master_sha256 = read_master(master_path)
    records = validate_master(rows, must_be_unreviewed=True)
    run_id = validate_preparation_binding(preparation_binding_path, master_sha256)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in records.values():
        grouped[row["requisition_id"]].append(row)
    shuffled = random.SystemRandom()
    packet_rows = []
    for requisition_id in sorted(grouped):
        candidates = list(grouped[requisition_id])
        shuffled.shuffle(candidates)
        for row in candidates:
            packet_rows.append({
                "run_id": run_id,
                **{field: row[field] for field in CONTEXT_FIELDS},
                "reviewer_role": reviewer,
                "reviewer_rank": "",
            })
    write_csv(output_path, PACKET_FIELDS, packet_rows)


def competition_rank(value: str, field: str, row_number: int) -> int:
    return evaluator.rank_value(value, field, row_number)


def validate_packet(
    packet_path: Path,
    expected_reviewer: str,
    master_records: dict[tuple[str, str], dict[str, str]],
    expected_run_id: str,
) -> dict[tuple[str, str], int]:
    rows = read_csv(packet_path, PACKET_FIELDS)
    ranks = {}
    by_requisition: dict[str, list[tuple[tuple[str, str], int]]] = defaultdict(list)
    for row_number, row in enumerate(rows, start=2):
        row = {field: (row.get(field) or "").strip() for field in PACKET_FIELDS}
        if row["run_id"] != expected_run_id:
            raise ValueError(f"Ranking packet run ID mismatch on row {row_number}.")
        if row["reviewer_role"] != expected_reviewer:
            raise ValueError(f"Reviewer role mismatch on row {row_number}.")
        key = (row["requisition_id"], row["candidate_id"])
        if key not in master_records or key in ranks:
            raise ValueError("A reviewer packet has an unknown or duplicate requisition/candidate row.")
        master = master_records[key]
        if any(row[field] != master[field] for field in CONTEXT_FIELDS):
            raise ValueError("A reviewer packet's requisition/candidate context changed after preparation.")
        rank = competition_rank(row["reviewer_rank"], "reviewer_rank", row_number)
        ranks[key] = rank
        by_requisition[key[0]].append((key, rank))
    if set(ranks) != set(master_records):
        raise ValueError("A reviewer packet must contain the complete frozen candidate roster.")
    for group in by_requisition.values():
        if not evaluator.competition_ranks_valid([rank for _, rank in group]):
            raise ValueError("Tied reviewer ranks must use competition-rank positions (for example, 1, 1, 3).")
    return ranks


def merge(
    master_path: Path,
    recruiter_path: Path,
    hiring_manager_path: Path,
    preparation_binding_path: Path,
    output_path: Path,
    binding_path: Path,
) -> None:
    """Create a blind adjudication sheet and private master binding."""
    output = restricted_path(output_path)
    binding = restricted_path(binding_path)
    if output == binding:
        raise ValueError("The blind adjudication sheet and private binding must use separate files.")
    preparation_binding = restricted_path(preparation_binding_path)
    if preparation_binding in {output, binding}:
        raise ValueError("Preparation and final operator bindings must use separate files from the blind sheet.")
    if output.exists() or binding.exists():
        raise ValueError("Choose new paths; existing ranking files are never overwritten.")
    rows, frozen_master_sha256 = read_master(master_path)
    records = validate_master(rows, must_be_unreviewed=True)
    run_id = validate_preparation_binding(preparation_binding, frozen_master_sha256)
    reviewer_ranks = {
        "recruiter_rank": validate_packet(recruiter_path, "recruiter", records, run_id),
        "hiring_manager_rank": validate_packet(hiring_manager_path, "hiring_manager", records, run_id),
    }
    adjudication_rows = []
    for row in rows:
        row = {field: (row.get(field) or "").strip() for field in evaluator.FIELDS}
        key = (row["requisition_id"], row["candidate_id"])
        adjudication_rows.append({
            "run_id": run_id,
            **{field: row[field] for field in CONTEXT_FIELDS},
            "recruiter_rank": str(reviewer_ranks["recruiter_rank"][key]),
            "hiring_manager_rank": str(reviewer_ranks["hiring_manager_rank"][key]),
            "adjudicated_rank": "",
        })
    random.SystemRandom().shuffle(adjudication_rows)
    write_binding(
        binding,
        frozen_master_sha256,
        reviewer_ranks_digest(reviewer_ranks),
        run_id,
    )
    try:
        write_csv(output, ADJUDICATION_FIELDS, adjudication_rows)
    except Exception:
        binding.unlink(missing_ok=True)
        raise


def validate_adjudication(
    adjudication_path: Path,
    master_records: dict[tuple[str, str], dict[str, str]],
    expected_run_id: str,
) -> dict[tuple[str, str], dict[str, int]]:
    """Validate a completed blind sheet against the frozen master roster."""
    rows = read_csv(adjudication_path, ADJUDICATION_FIELDS)
    ranks: dict[tuple[str, str], dict[str, int]] = {}
    by_requisition: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: {field: [] for field in ("recruiter_rank", "hiring_manager_rank", "adjudicated_rank")}
    )
    for row_number, source in enumerate(rows, start=2):
        row = {field: (source.get(field) or "").strip() for field in ADJUDICATION_FIELDS}
        if row["run_id"] != expected_run_id:
            raise ValueError(f"The adjudication sheet run ID does not match the frozen ranking run on row {row_number}.")
        key = (row["requisition_id"], row["candidate_id"])
        if key not in master_records or key in ranks:
            raise ValueError("The adjudication sheet has an unknown or duplicate requisition/candidate row.")
        master = master_records[key]
        if any(row[field] != master[field] for field in CONTEXT_FIELDS):
            raise ValueError("The adjudication sheet context changed after packet preparation.")
        candidate_ranks = {
            field: evaluator.rank_value(row[field], field, row_number)
            for field in ("recruiter_rank", "hiring_manager_rank", "adjudicated_rank")
        }
        ranks[key] = candidate_ranks
        for field, rank in candidate_ranks.items():
            by_requisition[key[0]][field].append(rank)

    if set(ranks) != set(master_records):
        raise ValueError("The adjudication sheet must contain the complete frozen candidate roster.")
    for group in by_requisition.values():
        for field, field_ranks in group.items():
            if not evaluator.competition_ranks_valid(field_ranks):
                raise ValueError(f"{field} must use complete competition ranks with ties sharing positions.")
    return ranks


def apply_adjudication(
    master_path: Path,
    adjudication_path: Path,
    binding_path: Path,
    output_path: Path,
) -> None:
    """Join locked, model-blind adjudication ranks to a pristine frozen master."""
    rows, frozen_master_sha256 = read_master(master_path)
    records = validate_master(rows, must_be_unreviewed=True)
    expected_reviewer_ranks_digest, run_id = validate_binding(binding_path, frozen_master_sha256)
    adjudication_ranks = validate_adjudication(adjudication_path, records, run_id)
    locked_reviewer_ranks = {
        reviewer_field: {
            key: candidate_ranks[reviewer_field]
            for key, candidate_ranks in adjudication_ranks.items()
        }
        for reviewer_field in ("recruiter_rank", "hiring_manager_rank")
    }
    if reviewer_ranks_digest(locked_reviewer_ranks) != expected_reviewer_ranks_digest:
        raise ValueError("Reviewer ranks changed after the independent packets were locked.")
    evaluation_rows = []
    for source in rows:
        row = {field: (source.get(field) or "").strip() for field in evaluator.FIELDS}
        key = (row["requisition_id"], row["candidate_id"])
        for field, value in adjudication_ranks[key].items():
            row[field] = str(value)
        evaluation_rows.append(row)
    write_csv(output_path, evaluator.FIELDS, evaluation_rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze_parser = subparsers.add_parser(
        "freeze-master", help="Lock the pristine ranking master before distributing packets"
    )
    freeze_parser.add_argument("master", type=Path)
    freeze_parser.add_argument("--output", type=Path, required=True)
    prepare_parser = subparsers.add_parser("prepare", help="Create one blinded reviewer packet")
    prepare_parser.add_argument("master", type=Path)
    prepare_parser.add_argument("--reviewer", choices=sorted(REVIEWERS), required=True)
    prepare_parser.add_argument("--preparation-binding", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    merge_parser = subparsers.add_parser(
        "merge", help="Create a model-blind adjudication sheet from both reviewer packets"
    )
    merge_parser.add_argument("master", type=Path)
    merge_parser.add_argument("recruiter_packet", type=Path)
    merge_parser.add_argument("hiring_manager_packet", type=Path)
    merge_parser.add_argument("--preparation-binding", type=Path, required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    merge_parser.add_argument(
        "--binding-output", type=Path, required=True,
        help="Private operator file binding this blind sheet to the exact frozen master; never send it to the adjudicator",
    )
    apply_parser = subparsers.add_parser(
        "apply-adjudication", help="Join locked adjudication ranks to a pristine master"
    )
    apply_parser.add_argument("master", type=Path)
    apply_parser.add_argument("adjudication", type=Path)
    apply_parser.add_argument(
        "--binding", type=Path, required=True,
        help="Private operator binding created by merge; keep it away from the adjudicator",
    )
    apply_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "freeze-master":
            run_id = freeze_master(args.master, args.output)
            print(json.dumps({"status": "frozen", "run_id": run_id}, ensure_ascii=True))
        elif args.command == "prepare":
            prepare(args.master, args.reviewer, args.output, args.preparation_binding)
        elif args.command == "merge":
            merge(
                args.master,
                args.recruiter_packet,
                args.hiring_manager_packet,
                args.preparation_binding,
                args.output,
                args.binding_output,
            )
        else:
            apply_adjudication(args.master, args.adjudication, args.binding, args.output)
        return 0
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        print(f"Ranking packet operation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
