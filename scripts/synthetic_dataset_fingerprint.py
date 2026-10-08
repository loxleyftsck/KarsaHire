"""Fingerprint every file in the bundled synthetic evaluation corpus."""

from __future__ import annotations

import hashlib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = REPOSITORY_ROOT / "data" / "synthetic-cv-32"
PINNED_SYNTHETIC_DATASET_SHA256 = "ccdcc7def2da8fedf37ecc58080b96391cbcaa38b542a117dc58f1d225c502d3"


def dataset_snapshot_sha256(dataset_root: Path) -> str:
    """Hash sorted relative paths and file bytes, rejecting links and escapes."""
    if (
        dataset_root.absolute() != DATASET_ROOT
        or (REPOSITORY_ROOT / "data").is_symlink()
        or dataset_root.is_symlink()
    ):
        raise ValueError("Only the bundled synthetic dataset directory can be fingerprinted.")
    root = dataset_root.resolve(strict=True)
    if not root.is_dir() or root != DATASET_ROOT:
        raise ValueError("Synthetic dataset path must remain at its bundled repository location.")

    files = sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())
    digest = hashlib.sha256(b"karsahire-synthetic-dataset-snapshot-v1\0")
    file_count = 0
    for path in files:
        if path.is_symlink():
            raise ValueError("Synthetic dataset snapshots must not contain symbolic links.")
        if not path.is_file():
            continue
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError("A synthetic dataset file resolves outside its dataset directory.")
        relative_path = path.relative_to(root).as_posix().encode("utf-8")
        contents = path.read_bytes()
        digest.update(len(relative_path).to_bytes(4, "big"))
        digest.update(relative_path)
        digest.update(len(contents).to_bytes(8, "big"))
        digest.update(contents)
        file_count += 1

    if not file_count:
        raise ValueError("Synthetic dataset directory contains no files.")
    return digest.hexdigest()


def pinned_dataset_snapshot_sha256(dataset_root: Path) -> str:
    """Require the bundled corpus to match its reviewed repository snapshot."""
    observed = dataset_snapshot_sha256(dataset_root)
    if observed != PINNED_SYNTHETIC_DATASET_SHA256:
        raise ValueError(
            "Bundled synthetic dataset differs from its pinned snapshot; review provenance before updating the pin."
        )
    return observed
