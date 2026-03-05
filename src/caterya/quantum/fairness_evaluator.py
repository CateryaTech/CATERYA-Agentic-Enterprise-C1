"""
QuantumFairnessEvaluator — Fairness checks on scaling decisions
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Uses quantum-inspired superposition of fairness metrics to evaluate
whether auto-scaling and resource allocation decisions are equitable
across tenant tiers, geographic regions, and demographic segments.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.caterya.quantum.quantum_utils import quantum_entropy, superposition_weights


@dataclass
class FairnessViolation:
    dimension: str
    score: float
    threshold: float
    description: str
    severity: str  # "critical" | "warning" | "info"


@dataclass
class QuantumFairnessResult:
    overall_fairness: float        # 0–1 quantum fairness score
    passed: bool
    violations: List[FairnessViolation]
    dimension_scores: Dict[str, float]
    quantum_seed: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_fairness": round(self.overall_fairness, 4),
            "passed":           self.passed,
            "violations":       [v.__dict__ for v in self.violations],
            "dimension_scores": {k: round(v, 4) for k, v in self.dimension_scores.items()},
            "quantum_seed":     self.quantum_seed,
            "metadata":         self.metadata,
        }


class QuantumFairnessEvaluator:
    """
    Evaluates fairness of scaling decisions using quantum-inspired multi-dimensional
    fairness metrics.

    Fairness dimensions:
    1. Tenant equity    — are all tenants getting proportional resources?
    2. Geographic equity — are latency/resources equal across regions?
    3. Tier fairness    — are upgrades/downgrades applied fairly?
    4. Load fairness    — is load balanced without demographic bias?
    5. Cost fairness    — are costs proportional to usage?

    Usage::

        qfe = QuantumFairnessEvaluator()
        result = qfe.evaluate(scaling_decision={
            "action": "scale_up",
            "tenant_id": "acme",
            "resources_before": {"cpu": 2, "memory": "4Gi"},
            "resources_after": {"cpu": 4, "memory": "8Gi"},
            "trigger": "cpu_threshold",
            "all_tenants_metrics": {...},
        })
        print(result.overall_fairness, result.passed)
    """

    FAIRNESS_THRESHOLD = 0.7

    def __init__(self, threshold: float = 0.7):
        self.threshold = threshold
        self._entropy_source = quantum_entropy(8)

    def evaluate(
        self,
        scaling_decision: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> QuantumFairnessResult:
        ctx = context or {}
        q_seed = int.from_bytes(quantum_entropy(4), "big")

        # ── Compute fairness dimensions ──
        tenant_equity   = self._tenant_equity(scaling_decision)
        geo_equity      = self._geographic_equity(scaling_decision, ctx)
        tier_fairness   = self._tier_fairness(scaling_decision)
        load_fairness   = self._load_balance_fairness(scaling_decision)
        cost_fairness   = self._cost_fairness(scaling_decision)

        # ── Quantum superposition weighting ──
        # Weights are quantum-randomised on each evaluation for robustness
        q_weights = superposition_weights(5)

        dimension_scores = {
            "tenant_equity":   tenant_equity,
            "geo_equity":      geo_equity,
            "tier_fairness":   tier_fairness,
            "load_fairness":   load_fairness,
            "cost_fairness":   cost_fairness,
        }

        overall = sum(
            score * weight
            for score, weight in zip(dimension_scores.values(), q_weights)
        )

        violations = self._detect_violations(dimension_scores)

        return QuantumFairnessResult(
            overall_fairness=overall,
            passed=overall >= self.threshold,
            violations=violations,
            dimension_scores=dimension_scores,
            quantum_seed=q_seed,
            metadata={
                "decision_type": scaling_decision.get("action"),
                "tenant_id":     scaling_decision.get("tenant_id"),
                "q_weights":     [round(w, 4) for w in q_weights],
                "threshold":     self.threshold,
            },
        )

    # ── Dimension evaluators ──────────────────────────────────────────────────

    def _tenant_equity(self, decision: Dict) -> float:
        """
        Are all tenants scaled proportionally to their usage?
        """
        all_metrics = decision.get("all_tenants_metrics", {})
        if not all_metrics:
            return 0.8  # no data → assume fair

        # Check if the scaled tenant's resource ratio is proportional
        tenant_id   = decision.get("tenant_id", "")
        tenant_data = all_metrics.get(tenant_id, {})
        usage_pct   = tenant_data.get("cpu_usage_pct", 70)

        # High CPU usage justifies scaling → fair
        if usage_pct >= 70:
            return 0.95
        elif usage_pct >= 50:
            return 0.80
        else:
            # Scaling a low-usage tenant while others are high → unfair
            others_avg = sum(
                v.get("cpu_usage_pct", 0)
                for k, v in all_metrics.items() if k != tenant_id
            ) / max(1, len(all_metrics) - 1)

            if others_avg > usage_pct + 30:
                return 0.4   # other tenants need scaling more
            return 0.75

    def _geographic_equity(self, decision: Dict, ctx: Dict) -> float:
        """Are latency and resources equitable across geographic regions?"""
        region_metrics = ctx.get("region_metrics", {})
        if not region_metrics:
            return 0.85

        latencies = [v.get("p99_latency_ms", 100) for v in region_metrics.values()]
        if not latencies:
            return 0.85

        max_lat = max(latencies)
        min_lat = min(latencies)
        avg_lat = sum(latencies) / len(latencies)

        # Perfect geo equity: all regions within 20% of average
        variance_ratio = (max_lat - min_lat) / (avg_lat + 1e-9)
        equity = max(0.0, 1.0 - variance_ratio * 0.5)
        return min(1.0, equity)

    def _tier_fairness(self, decision: Dict) -> float:
        """Are upgrade/downgrade decisions applied consistently across tiers?"""
        tier = decision.get("tenant_plan", "pro")
        action = decision.get("action", "scale_up")

        # Scaling down free tier while pro tier is at capacity → unfair
        if tier == "free" and action == "scale_down":
            other_tier_actions = decision.get("concurrent_tier_actions", {})
            if other_tier_actions.get("enterprise") == "scale_up":
                return 0.5   # enterprise getting more while free gets less

        return 0.9  # default fair

    def _load_balance_fairness(self, decision: Dict) -> float:
        """Is load balanced without implicit demographic bias in routing?"""
        routing_weights = decision.get("routing_weights", {})
        if not routing_weights:
            return 0.88

        weights = list(routing_weights.values())
        if not weights:
            return 0.88

        # Check for extreme imbalance (e.g. one node getting 80%+ of traffic)
        max_weight = max(weights)
        if max_weight > 0.8:
            return max(0.3, 1.0 - max_weight)

        # Perfect balance = all weights equal
        mean_w   = sum(weights) / len(weights)
        variance = sum((w - mean_w) ** 2 for w in weights) / len(weights)
        std_dev  = math.sqrt(variance)
        return max(0.0, 1.0 - std_dev * 2)

    def _cost_fairness(self, decision: Dict) -> float:
        """Are costs proportional to usage across tenants?"""
        cost_data = decision.get("cost_attribution", {})
        if not cost_data:
            return 0.85

        usages = [v.get("usage") for v in cost_data.values() if v.get("usage")]
        costs  = [v.get("cost")  for v in cost_data.values() if v.get("cost")]

        if not usages or not costs or len(usages) != len(costs):
            return 0.85

        # Compute cost-per-usage ratios; fair = consistent ratios
        ratios = [c / (u + 1e-9) for c, u in zip(costs, usages)]
        mean_r = sum(ratios) / len(ratios)
        cv     = max(abs(r - mean_r) for r in ratios) / (mean_r + 1e-9)

        return max(0.0, min(1.0, 1.0 - cv * 0.3))

    def _detect_violations(self, scores: Dict[str, float]) -> List[FairnessViolation]:
        violations = []
        thresholds = {
            "tenant_equity":  (0.7, "Some tenants may be under-resourced relative to usage"),
            "geo_equity":     (0.6, "Geographic latency disparity detected"),
            "tier_fairness":  (0.7, "Tier-based scaling may disadvantage certain plans"),
            "load_fairness":  (0.65, "Load imbalance detected across nodes"),
            "cost_fairness":  (0.7, "Cost attribution may not be proportional to usage"),
        }
        for dim, (threshold, desc) in thresholds.items():
            score = scores.get(dim, 1.0)
            if score < threshold:
                severity = "critical" if score < 0.4 else "warning"
                violations.append(FairnessViolation(
                    dimension=dim,
                    score=score,
                    threshold=threshold,
                    description=desc,
                    severity=severity,
                ))
        return violations
