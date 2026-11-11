"""Layer 4 boundary: cleaning and diagnosis-side judgments.

Only pure, deterministic functions that turn evidence fields into buckets live
here. Anything that needs a model, a threshold or contextual judgment belongs to
``diagnosis/`` and is **not** implemented yet.
"""
