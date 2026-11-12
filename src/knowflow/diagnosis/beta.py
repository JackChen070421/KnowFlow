"""Regularized incomplete beta and its inverse, in pure Python.

The diagnosis layer needs three quantities from a Beta posterior: the credible
interval end points, ``P(p < weak_threshold)`` and ``P(p > mastered_threshold)``.
Pulling SciPy in for that alone would put a scientific stack on the critical path
of every run (and on CI), so the two routines are implemented here with the
continued-fraction expansion from *Numerical Recipes* §6.4.  Accuracy is far
beyond what a six-decimal report needs; ``tests/diagnosis/test_beta.py`` pins it
against known values.
"""

from __future__ import annotations

import math

_EPS = 3e-14
_TINY = 1e-300
_MAX_ITER = 300


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""

    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _TINY:
        d = _TINY
    d = 1.0 / d
    h = d
    for m in range(1, _MAX_ITER + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1.0 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1.0 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized lower incomplete beta ``I_x(a, b)`` = CDF of ``Beta(a, b)``."""

    if a <= 0 or b <= 0:
        raise ValueError("beta parameters must be positive")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_bt = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    bt = math.exp(log_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def betappf(q: float, a: float, b: float) -> float:
    """Quantile function of ``Beta(a, b)`` by bisection on :func:`betainc`.

    Bisection is slower than Newton but cannot diverge for tiny ``a``/``b``,
    which is exactly the regime of an uninformative prior plus one observation.
    """

    if not 0.0 < q < 1.0:
        raise ValueError("q must be in (0, 1)")
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if betainc(a, b, mid) < q:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-15:
            break
    return (lo + hi) / 2.0
