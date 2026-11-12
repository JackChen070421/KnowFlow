"""A transparent Beta-Bernoulli baseline for full-credit performance."""

import math
from dataclasses import asdict, dataclass

from scipy.stats import beta


@dataclass(frozen=True)
class DiagnosisConfig:
    prior_alpha: float = 1.0
    prior_beta: float = 1.0
    min_evidence: int = 3
    weak_threshold: float = 0.4
    mastered_threshold: float = 0.75
    confirmation_probability: float = 0.9
    credible_mass: float = 0.9
    high_confidence_width: float = 0.35
    medium_confidence_width: float = 0.6

    def __post_init__(self):
        if any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in asdict(self).values()
        ):
            raise ValueError("diagnosis configuration must contain finite numbers")
        if self.prior_alpha <= 0 or self.prior_beta <= 0:
            raise ValueError("Beta priors must be positive")
        if not isinstance(self.min_evidence, int) or self.min_evidence < 1:
            raise ValueError("min_evidence must be a positive integer")
        if not 0 < self.weak_threshold < self.mastered_threshold < 1:
            raise ValueError("require 0 < weak_threshold < mastered_threshold < 1")
        if not 0.5 < self.confirmation_probability < 1 or not 0 < self.credible_mass < 1:
            raise ValueError("invalid posterior probabilities")
        if not 0 < self.high_confidence_width < self.medium_confidence_width < 1:
            raise ValueError("invalid confidence interval width thresholds")


def estimate_mastery(correct: int, observed: int, config: DiagnosisConfig) -> dict:
    if not 0 <= correct <= observed:
        raise ValueError("require 0 <= correct <= observed")
    if observed == 0:
        return {
            "mastery": None,
            "confidence": "low",
            "status": "insufficient_evidence",
            "credible_interval": None,
            "weak_probability": None,
            "mastered_probability": None,
            "status_reason": "没有有效评分，不能估计掌握情况。",
        }
    a, b = correct + config.prior_alpha, observed - correct + config.prior_beta
    mean = a / (a + b)
    tail = (1 - config.credible_mass) / 2
    low, high = (float(x) for x in beta.ppf([tail, 1 - tail], a, b))
    weak = float(beta.cdf(config.weak_threshold, a, b))
    mastered = float(beta.sf(config.mastered_threshold, a, b))
    width = high - low
    confidence = (
        "high"
        if width <= config.high_confidence_width
        else "medium"
        if width <= config.medium_confidence_width
        else "low"
    )
    if observed < config.min_evidence:
        status, confidence = "insufficient_evidence", "low"
        reason = f"仅有{observed}项有效评分，少于最低观测数{config.min_evidence}。"
    elif weak >= config.confirmation_probability:
        status = "confirmed_weak"
        reason = "低于薄弱阈值的后验概率达到预设确认门槛；仅适用于当前测验范围。"
    elif mastered >= config.confirmation_probability:
        status = "confirmed_mastered"
        reason = "高于掌握阈值的后验概率达到预设确认门槛；仅适用于当前测验范围。"
    elif mean < config.weak_threshold:
        status, reason = "likely_weak", "表现偏弱，但后验概率尚未达到确认门槛。"
    elif mean >= config.mastered_threshold:
        status, reason = "likely_mastered", "表现较好，但后验概率尚未达到确认门槛。"
    else:
        status, reason = "mixed_performance", "有效记录呈现中间或混合表现，不能简单归为掌握或薄弱。"
    return {
        "mastery": round(mean, 6),
        "confidence": confidence,
        "status": status,
        "credible_interval": [round(low, 6), round(high, 6)],
        "weak_probability": round(weak, 6),
        "mastered_probability": round(mastered, 6),
        "status_reason": reason,
    }
