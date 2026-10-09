"""Restore a SQLite snapshot into a new, integrity-checked database file."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
from backup_database import create_backup  # noqa: E402


def restore_snapshot(snapshot_path: Path, destination_path: Path) -> dict[str, str | int]:
    """Restore to a new path without replacing a live or existing database."""
    return create_backup(
        snapshot_path,
        destination_path,
        maximum_schema_version=server.SCHEMA_VERSION,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Verified SQLite snapshot")
    parser.add_argument("--target", type=Path, required=True, help="New restore path; existing files are never overwritten")
    args = parser.parse_args()
    try:
        print(
            "PERHATIAN: snapshot dapat memulihkan data kandidat yang dihapus setelah snapshot dibuat. "
            "Jangan gunakan hasil restore pada data operasional sebelum prosedur rekonsiliasi disepakati.",
            file=sys.stderr,
        )
        result = restore_snapshot(args.source, args.target)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"Restore gagal: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
