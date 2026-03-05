"""
CATERYA Evaluator v3 — 7-pillar COS engine (target COS > 0.9)
Author  : Ary HH <cateryatech@proton.me>
"""
from __future__ import annotations
import uuid, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS: Dict[str, float] = {
    "bias_fairness":    0.20,
    "transparency":     0.20,
    "safety":           0.18,
    "accountability":   0.14,
    "privacy":          0.14,
    "robustness":       0.07,
    "interpretability": 0.07,
}

@dataclass
class PillarScore:
    name: str; score: float; weight: float
    details: Dict[str, Any] = field(default_factory=dict)
    passed: bool = False
    def weighted(self): return self.score * self.weight

@dataclass
class COSResult:
    cos: float; pillar_scores: List[PillarScore]; evaluation_id: str
    tenant_id: Optional[str]; timestamp: str; passed: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self):
        return {"evaluation_id": self.evaluation_id, "tenant_id": self.tenant_id,
                "cos": round(self.cos, 4), "passed": self.passed, "timestamp": self.timestamp,
                "pillars": [{"name": p.name,"score": round(p.score,4),"weight": p.weight,
                             "weighted_score": round(p.weighted(),4),"passed": p.passed,
                             "details": p.details} for p in self.pillar_scores],
                "metadata": self.metadata}

class CATERYAEvaluator:
    """v3: 7-pillar evaluator targeting COS > 0.9."""
    def __init__(self, weights=None, threshold=0.7, pillar_threshold=0.6, tenant_id=None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self._normalize_weights()
        self.threshold = threshold
        self.pillar_threshold = pillar_threshold
        self.tenant_id = tenant_id
        self._history: List[COSResult] = []

    def evaluate(self, output, context=None, explanation=None, ground_truth=None):
        ctx = context or {}
        tenant_id = ctx.get("tenant_id", self.tenant_id)
        pillar_scores = []

        from src.caterya.pillars.bias_fairness   import BiasFairnessPillar
        from src.caterya.pillars.transparency     import TransparencyPillar
        from src.caterya.pillars.safety           import SafetyPillar
        from src.caterya.pillars.accountability   import AccountabilityPillar
        from src.caterya.pillars.privacy          import PrivacyPillar
        from src.caterya.pillars.robustness       import RobustnessPillar
        from src.caterya.pillars.interpretability import InterpretabilityPillar

        evals = [
            ("bias_fairness",   lambda: BiasFairnessPillar().evaluate(output, ctx)),
            ("transparency",    lambda: TransparencyPillar().evaluate(output, ctx)),
            ("safety",          lambda: SafetyPillar().evaluate(output, ctx)),
            ("accountability",  lambda: AccountabilityPillar().evaluate(output, ctx)),
            ("privacy",         lambda: PrivacyPillar().evaluate(output, ctx)),
            ("robustness",      lambda: RobustnessPillar().evaluate(output)),
            ("interpretability",lambda: InterpretabilityPillar().evaluate(explanation or output, output, ctx)),
        ]
        for name, fn in evals:
            score, details = fn()
            pillar_scores.append(PillarScore(name=name, score=score,
                weight=self.weights.get(name, 0.0), details=details,
                passed=score >= self.pillar_threshold))

        cos = sum(p.weighted() for p in pillar_scores)
        result = COSResult(cos=cos, pillar_scores=pillar_scores,
            evaluation_id=str(uuid.uuid4()), tenant_id=tenant_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            passed=cos >= self.threshold,
            metadata={"output_length": len(output), "threshold": self.threshold, "version": "3.0"})
        self._history.append(result)
        logger.info("COS | tenant=%s cos=%.4f passed=%s", tenant_id, cos, result.passed)
        return result

    def batch_evaluate(self, outputs, contexts=None):
        contexts = contexts or [{}] * len(outputs)
        return [self.evaluate(o, c) for o, c in zip(outputs, contexts)]

    def get_history(self, tenant_id=None):
        if tenant_id:
            return [r for r in self._history if r.tenant_id == tenant_id]
        return list(self._history)

    def average_cos(self, tenant_id=None):
        r = self.get_history(tenant_id)
        return sum(x.cos for x in r) / len(r) if r else 0.0

    def _normalize_weights(self):
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            self.weights = {k: v/total for k, v in self.weights.items()}
