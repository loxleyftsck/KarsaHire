"""Create an atomic, integrity-checked SQLite online backup of KarsaHire."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def create_backup(
    source_path: Path,
    output_path: Path,
    *,
    maximum_schema_version: int | None = None,
) -> dict[str, str | int]:
    """Snapshot a live database consistently; never overwrite an existing backup."""
    source = source_path.expanduser().resolve(strict=True)
    output = output_path.expanduser().resolve()
    if not source.is_file():
        raise ValueError("Source backup harus berupa file database.")
    if source == output:
        raise ValueError("File backup tidak boleh sama dengan database sumber.")
    repository = ROOT.resolve()
    if output == repository or repository in output.parents:
        raise ValueError(
            "Tujuan backup harus berada di luar repository agar snapshot tidak masuk ke Git."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("File tujuan sudah ada; pilih nama backup baru.")

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    source_db = target_db = None
    try:
        source_uri = source.as_uri() + "?mode=ro"
        source_db = sqlite3.connect(source_uri, uri=True, timeout=10)
        target_db = sqlite3.connect(temporary, timeout=10)
        source_db.backup(target_db, pages=256, sleep=0.05)
        check = target_db.execute("PRAGMA integrity_check").fetchone()
        if check != ("ok",):
            raise sqlite3.DatabaseError("Backup gagal melewati PRAGMA integrity_check.")
        schema_version = int(target_db.execute("PRAGMA user_version").fetchone()[0])
        if maximum_schema_version is not None and schema_version > maximum_schema_version:
            raise ValueError(
                f"Database snapshot v{schema_version} lebih baru daripada aplikasi ini "
                f"(mendukung sampai v{maximum_schema_version})."
            )
        target_db.close()
        target_db = None
        source_db.close()
        source_db = None

        # Restrict the snapshot to its owner where POSIX permissions are available.
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        file_fd = os.open(temporary, os.O_RDWR)
        try:
            os.fsync(file_fd)
        finally:
            os.close(file_fd)

        # Hard-link publication is atomic and fails if another backup already exists.
        os.link(temporary, output)
        temporary.unlink()
        return {
            "output": str(output),
            "size_bytes": output.stat().st_size,
            "schema_version": schema_version,
            "integrity_check": "ok",
        }
    finally:
        if target_db is not None:
            target_db.close()
        if source_db is not None:
            source_db.close()
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=server.DB_PATH,
        help="SQLite source file (defaults to the local KarsaHire database)",
    )
    parser.add_argument("--output", type=Path, required=True, help="New backup path; existing files are never overwritten")
    args = parser.parse_args()
    try:
        print(json.dumps(create_backup(args.source, args.output), ensure_ascii=False, indent=2))
        return 0
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"Backup gagal: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
