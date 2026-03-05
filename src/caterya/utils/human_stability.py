"""
Human Constant Stability (HCS) — Humans-in-the-Loop Integration
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

The Human Constant Stability module ensures that:
1. Critical agent decisions are reviewed by humans before execution
2. Human feedback is collected and fed back into COS evaluation
3. Disagreement between human and AI is tracked as a stability signal
4. The system degrades gracefully when humans are unavailable

HCS Formula:
  HCS = w1 * agreement_rate + w2 * response_latency_score + w3 * coverage_rate
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Actions requiring human review (configurable per tenant)
HIGH_RISK_ACTIONS = {
    "security_audit_finding_critical",
    "compliance_violation_critical",
    "cos_below_threshold",
    "guardrail_override_requested",
    "data_deletion_requested",
    "billing_dispute",
}


@dataclass
class HumanReviewRequest:
    request_id:   str
    tenant_id:    str
    agent_name:   str
    action:       str
    output:       str
    explanation:  str
    cos_score:    float
    urgency:      str   # "low" | "medium" | "high" | "critical"
    created_at:   float = field(default_factory=time.time)
    resolved:     bool  = False
    human_verdict: Optional[str] = None   # "approve" | "reject" | "modify"
    human_notes:   Optional[str] = None
    resolved_at:   Optional[float] = None


@dataclass
class HCSMetrics:
    agreement_rate:       float   # % cases where human agreed with AI
    response_latency_s:   float   # avg time for human to respond
    coverage_rate:        float   # % of flagged items actually reviewed
    total_reviews:        int
    pending_reviews:      int

    def hcs_score(self) -> float:
        """Composite Human Constant Stability score."""
        latency_score = max(0.0, 1.0 - self.response_latency_s / 3600)   # degrades after 1h
        return (
            0.40 * self.agreement_rate +
            0.30 * latency_score +
            0.30 * self.coverage_rate
        )


class HumanConstantStability:
    """
    Manages human-in-the-loop review queue for high-stakes agent decisions.

    Integrates with Streamlit dashboard for review UI and email/Slack notifications.

    Usage::

        hcs = HumanConstantStability(tenant_id="acme")

        # Flag a decision for human review
        req = hcs.flag(
            agent_name="security_auditor",
            action="security_audit_finding_critical",
            output="Critical SQL injection found.",
            explanation="OWASP A03 violation detected in endpoint /api/users.",
            cos_score=0.62,
        )

        # In dashboard: human approves/rejects
        hcs.resolve(req.request_id, verdict="approve", notes="Confirmed, fixing now.")

        # Get stability metrics
        metrics = hcs.get_metrics()
        print(metrics.hcs_score())
    """

    def __init__(
        self,
        tenant_id: str,
        auto_approve_threshold: float = 0.9,    # auto-approve if COS >= this
        auto_reject_threshold: float = 0.3,      # auto-reject if COS <= this
        timeout_secs: int = 3600,                # auto-resolve after 1h
        notification_fn: Optional[Callable] = None,
    ):
        self.tenant_id              = tenant_id
        self.auto_approve_threshold = auto_approve_threshold
        self.auto_reject_threshold  = auto_reject_threshold
        self.timeout_secs           = timeout_secs
        self.notification_fn        = notification_fn
        self._queue: Dict[str, HumanReviewRequest] = {}
        self._resolved: List[HumanReviewRequest]   = []

    def flag(
        self,
        agent_name: str,
        action: str,
        output: str,
        explanation: str,
        cos_score: float,
        urgency: str = "medium",
    ) -> HumanReviewRequest:
        """Flag a decision for human review."""

        # Auto-approve high-confidence decisions
        if cos_score >= self.auto_approve_threshold and action not in HIGH_RISK_ACTIONS:
            req = HumanReviewRequest(
                request_id=str(uuid.uuid4()), tenant_id=self.tenant_id,
                agent_name=agent_name, action=action, output=output,
                explanation=explanation, cos_score=cos_score, urgency=urgency,
                resolved=True, human_verdict="auto_approved",
                resolved_at=time.time(),
            )
            self._resolved.append(req)
            logger.debug("Auto-approved | agent=%s cos=%.4f", agent_name, cos_score)
            return req

        # Auto-reject very low confidence
        if cos_score <= self.auto_reject_threshold:
            req = HumanReviewRequest(
                request_id=str(uuid.uuid4()), tenant_id=self.tenant_id,
                agent_name=agent_name, action=action, output=output,
                explanation=explanation, cos_score=cos_score, urgency="critical",
                resolved=True, human_verdict="auto_rejected",
                resolved_at=time.time(),
            )
            self._resolved.append(req)
            logger.warning("Auto-rejected | agent=%s cos=%.4f", agent_name, cos_score)
            return req

        # Queue for human review
        req = HumanReviewRequest(
            request_id=str(uuid.uuid4()), tenant_id=self.tenant_id,
            agent_name=agent_name, action=action, output=output[:1000],
            explanation=explanation[:500], cos_score=cos_score, urgency=urgency,
        )
        self._queue[req.request_id] = req

        if self.notification_fn:
            self.notification_fn(req)

        logger.info("Human review queued | id=%s agent=%s urgency=%s",
                    req.request_id, agent_name, urgency)
        return req

    def resolve(
        self,
        request_id: str,
        verdict: str,   # "approve" | "reject" | "modify"
        notes: Optional[str] = None,
        modified_output: Optional[str] = None,
    ) -> Optional[HumanReviewRequest]:
        req = self._queue.pop(request_id, None)
        if not req:
            return None
        req.resolved      = True
        req.human_verdict = verdict
        req.human_notes   = notes
        req.resolved_at   = time.time()
        if modified_output:
            req.output = modified_output
        self._resolved.append(req)
        logger.info("Review resolved | id=%s verdict=%s", request_id, verdict)
        return req

    def get_pending(self, urgency: Optional[str] = None) -> List[HumanReviewRequest]:
        reqs = list(self._queue.values())
        if urgency:
            reqs = [r for r in reqs if r.urgency == urgency]
        return sorted(reqs, key=lambda r: r.created_at)

    def get_metrics(self) -> HCSMetrics:
        if not self._resolved:
            return HCSMetrics(1.0, 0.0, 1.0, 0, len(self._queue))

        total_resolved     = len(self._resolved)
        human_reviewed     = [r for r in self._resolved if r.human_verdict not in ("auto_approved", "auto_rejected")]
        approved           = [r for r in human_reviewed if r.human_verdict == "approve"]
        agreement_rate     = len(approved) / max(1, len(human_reviewed))
        latencies          = [r.resolved_at - r.created_at for r in human_reviewed if r.resolved_at]
        avg_latency        = sum(latencies) / len(latencies) if latencies else 0.0
        flagged            = total_resolved + len(self._queue)
        coverage_rate      = total_resolved / flagged if flagged > 0 else 1.0

        return HCSMetrics(
            agreement_rate=agreement_rate,
            response_latency_s=avg_latency,
            coverage_rate=coverage_rate,
            total_reviews=total_resolved,
            pending_reviews=len(self._queue),
        )

    def to_dict(self) -> Dict[str, Any]:
        metrics = self.get_metrics()
        return {
            "hcs_score":    round(metrics.hcs_score(), 4),
            "metrics":      metrics.__dict__,
            "pending_count": len(self._queue),
            "resolved_count": len(self._resolved),
        }
