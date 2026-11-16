"""Direction 1: disputed-score review.

Rules only raise review clues; humans decide in an append-only local ledger; the
official scores are never modified. See ``schemas/CONTRACT.md`` §10.
"""

from .pipeline import (
    POLICY_VALUES,
    REPORT_FILE,
    build_context,
    context_from_run_manifest,
    decide,
    latest_report,
    load_report,
    scan_dataset,
)
from .rules import EXCLUDED_FLAG_CODES, FLAG_CODES, RULE_VERSION
from .validation import validate_report

__all__ = [
    "EXCLUDED_FLAG_CODES",
    "FLAG_CODES",
    "POLICY_VALUES",
    "REPORT_FILE",
    "RULE_VERSION",
    "build_context",
    "context_from_run_manifest",
    "decide",
    "latest_report",
    "load_report",
    "scan_dataset",
    "validate_report",
]
