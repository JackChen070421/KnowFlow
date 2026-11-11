"""Layer 2 (data): official package → canonical tables + quality report.

Import surface for scripts and the CLI; all rules live in ``mapping.py``
(IDs), ``adapters.py`` (fields), ``quality.py`` (cleaning/report) and
``pipeline.py`` (I/O + validation).
"""

from __future__ import annotations

from .errors import AdaptError
from .pipeline import (
    CANONICAL_VERSION,
    build_bundle,
    load_official,
    run_adapt,
    validate_bundle,
    verify_written,
    write_bundle,
)

__all__ = [
    "AdaptError",
    "CANONICAL_VERSION",
    "build_bundle",
    "load_official",
    "run_adapt",
    "validate_bundle",
    "verify_written",
    "write_bundle",
]
