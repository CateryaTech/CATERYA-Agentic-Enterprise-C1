"""
CATERYA Guardrail — Per-Agent Ethical Filter
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Toxicity / harmful-content patterns ──────────────────────────────────────
_HARM_PATTERNS = [
    r"\b(kill|murder|harm|hurt|attack|destroy)\s+(yourself|himself|herself|themselves|people)\b",
    r"\b(how\s+to\s+(make|build|create|synthesize|manufacture))\s+(a\s+)?(bomb|weapon|poison|explosive|malware|virus)\b",
    r"\b(make|build|create)\s+(a\s+)?(bomb|explosive|weapon)\b",
    r"\b(step[- ]by[- ]step).{0,30}(bomb|explosive|weapon|poison)\b",
    r"\b(instructions?|tutorial|guide).{0,30}(bomb|explosive|weapon|harm)\b",
    r"\b(synthesize|make|produce|manufacture)\s+(meth(amphetamine)?|heroin|fentanyl|cocaine)\b",
    r"\binstructions?\s+to\s+(synthesize|make|produce|manufacture)\s",
    r"\b(child\s+(abuse|exploitation|porn))\b",
    r"\b(self[- ]harm|suicide\s+method)\b",
    r"\b(synthesize|manufacture)\s+(meth|heroin|fentanyl|explosives)\b",
]

_BIAS_SLURS = [
    r"\b(nigger|faggot|chink|spic|kike|tranny)\b",
]

_PII_PATTERNS = [
    r"\b\d{3}-\d{2}-\d{4}\b",          # SSN
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",   # email
    r"\b(?:\d[ -]?){13,16}\b",          # credit card
]

_COMPILED_HARM  = [re.compile(p, re.I) for p in _HARM_PATTERNS]
_COMPILED_BIAS  = [re.compile(p, re.I) for p in _BIAS_SLURS]
_COMPILED_PII   = [re.compile(p, re.I) for p in _PII_PATTERNS]


@dataclass
class GuardrailResult:
    allowed: bool
    reasons: List[str] = field(default_factory=list)
    sanitized_output: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": self.reasons,
            "sanitized_output": self.sanitized_output,
            "metadata": self.metadata,
        }


class CATERYAGuardrail:
    """
    Wraps any agent node in a LangGraph workflow.
    Checks both INPUT (pre-guard) and OUTPUT (post-guard).

    Usage::

        guardrail = CATERYAGuardrail(agent_name="research_agent")

        # LangGraph node wrapper
        @guardrail.wrap
        def research_node(state):
            ...
            return state
    """

    def __init__(
        self,
        agent_name: str = "agent",
        block_on_harm: bool = True,
        block_on_bias: bool = True,
        redact_pii: bool = True,
        custom_rules: Optional[List[Callable[[str], Optional[str]]]] = None,
        tenant_id: Optional[str] = None,
    ):
        self.agent_name = agent_name
        self.block_on_harm = block_on_harm
        self.block_on_bias = block_on_bias
        self.redact_pii = redact_pii
        self.custom_rules = custom_rules or []
        self.tenant_id = tenant_id
        self._violations: List[Dict[str, Any]] = []

    # ── public ─────────────────────────────────

    def check(self, text: str, context: Optional[Dict[str, Any]] = None) -> GuardrailResult:
        ctx = context or {}
        reasons: List[str] = []
        sanitized = text

        # ── harmful content ──
        if self.block_on_harm:
            for pat in _COMPILED_HARM:
                if pat.search(sanitized):
                    reasons.append(f"harmful_content:{pat.pattern[:40]}")

        # ── bias slurs ──
        if self.block_on_bias:
            for pat in _COMPILED_BIAS:
                if pat.search(sanitized):
                    reasons.append(f"bias_slur:{pat.pattern[:40]}")

        # ── PII redaction (non-blocking) ──
        if self.redact_pii:
            for pat in _COMPILED_PII:
                sanitized = pat.sub("[REDACTED]", sanitized)

        # ── custom rules ──
        for rule in self.custom_rules:
            result = rule(sanitized)
            if result:
                reasons.append(result)

        allowed = len(reasons) == 0

        if not allowed:
            self._violations.append({
                "agent": self.agent_name,
                "tenant_id": ctx.get("tenant_id", self.tenant_id),
                "reasons": reasons,
                "text_snippet": text[:200],
            })
            logger.warning(
                "Guardrail BLOCKED | agent=%s reasons=%s",
                self.agent_name, reasons,
            )

        return GuardrailResult(
            allowed=allowed,
            reasons=reasons,
            sanitized_output=sanitized if allowed else None,
            metadata={"agent": self.agent_name, "tenant_id": ctx.get("tenant_id")},
        )

    def wrap(self, node_fn: Callable) -> Callable:
        """Decorator for LangGraph node functions."""

        def wrapped(state: Dict[str, Any]) -> Dict[str, Any]:
            # ── pre-guard: check incoming messages ──
            messages = state.get("messages", [])
            last_human = next(
                (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
                "",
            )
            pre = self.check(last_human, context={"phase": "input", **state})
            if not pre.allowed:
                state["guardrail_blocked"] = True
                state["guardrail_reasons"] = pre.reasons
                state["messages"] = messages + [{
                    "role": "assistant",
                    "content": (
                        "I'm unable to process this request as it violates ethical guidelines. "
                        f"Reasons: {', '.join(pre.reasons)}"
                    ),
                }]
                return state

            # ── run actual node ──
            state = node_fn(state)

            # ── post-guard: check output ──
            out_messages = state.get("messages", [])
            last_assistant = next(
                (m.get("content", "") for m in reversed(out_messages) if m.get("role") == "assistant"),
                "",
            )
            post = self.check(last_assistant, context={"phase": "output", **state})
            if not post.allowed:
                # Replace with safe refusal
                state["messages"] = out_messages[:-1] + [{
                    "role": "assistant",
                    "content": "The generated response was filtered due to policy violations.",
                }]
                state["guardrail_blocked"] = True
            elif post.sanitized_output and post.sanitized_output != last_assistant:
                # Apply PII redaction
                state["messages"] = out_messages[:-1] + [{
                    "role": "assistant",
                    "content": post.sanitized_output,
                }]

            return state

        wrapped.__name__ = node_fn.__name__
        return wrapped

    def violations(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if tenant_id:
            return [v for v in self._violations if v.get("tenant_id") == tenant_id]
        return list(self._violations)
