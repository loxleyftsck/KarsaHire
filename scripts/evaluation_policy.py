"""Shared M2 reporting and work-file boundary policies."""

import hashlib
from pathlib import Path

# M0 privacy governance must approve or replace this before results are shared.
REPORTING_POLICY_VERSION = "provisional-v1"
REPORTING_POLICY_STATUS = "provisional"
MIN_REPORTING_CANDIDATES = 5


def evaluator_fingerprints(source_path: Path) -> dict[str, str]:
    """Fingerprint the evaluator together with the policy that governs its output."""
    source = source_path.read_bytes().replace(b"\r\n", b"\n")
    policy = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    return {
        "evaluator_sha256": hashlib.sha256(source + b"\0" + policy).hexdigest(),
        "reporting_policy_sha256": hashlib.sha256(policy).hexdigest(),
    }


def require_external_evaluation_path(
    path: Path, repository_root: Path, purpose: str
) -> Path:
    """Resolve a work-file path and reject it if it points into the repository."""
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(repository_root.resolve())
    except ValueError:
        return resolved
    raise ValueError(f"{purpose} must be kept outside the repository.")
