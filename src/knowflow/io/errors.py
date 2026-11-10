"""Error types for the data-processing layer."""

from __future__ import annotations


class AdaptError(RuntimeError):
    """Raised when official data cannot be mapped without guessing.

    The message always names the table/line/field so the failure can be
    reproduced from the command line.
    """
