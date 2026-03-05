"""
CATERYA Base Agent — with Guardrail, Interpretability, COS Evaluation
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech
"""

from __future__ import annotations

import time
import uuid
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.caterya.core.guardrail import CATERYAGuardrail
from src.caterya.core.evaluator import CATERYAEvaluator

logger = logging.getLogger(__name__)


class AgentResult:
    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        output: Any,
        explanation: str,
        cos_result: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        duration_ms: float = 0.0,
    ):
        self.agent_id   = agent_id
        self.agent_name = agent_name
        self.output     = output
        self.explanation = explanation
        self.cos_result = cos_result
        self.metadata   = metadata or {}
        self.duration_ms = duration_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id":    self.agent_id,
            "agent_name":  self.agent_name,
            "output":      str(self.output)[:2000],
            "explanation": self.explanation,
            "cos_result":  self.cos_result,
            "metadata":    self.metadata,
            "duration_ms": round(self.duration_ms, 2),
        }


class BaseCateryaAgent(ABC):
    """
    Abstract base class for all CATERYA pipeline agents.

    Every concrete agent must implement:
      - run(state) → dict         : main agent logic
      - explain(state) → str      : interpretability explanation of reasoning
      - get_system_prompt() → str : LLM system prompt

    Each agent is wrapped with CATERYAGuardrail and evaluated with CATERYAEvaluator.
    """

    AGENT_NAME: str = "base_agent"
    AGENT_ROLE: str = "Generic agent"

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        llm_provider: str = "ollama",
        llm_model: str = "llama3",
        cos_threshold: float = 0.7,
    ):
        self.agent_uid   = str(uuid.uuid4())
        self.tenant_id   = tenant_id
        self.llm_provider = llm_provider
        self.llm_model   = llm_model
        self.cos_threshold = cos_threshold

        self.guardrail   = CATERYAGuardrail(
            agent_name=self.AGENT_NAME,
            tenant_id=tenant_id,
            redact_pii=True,
        )
        self.evaluator   = CATERYAEvaluator(
            threshold=cos_threshold,
            tenant_id=tenant_id,
        )
        self._history: List[AgentResult] = []

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute agent logic, return updated state."""

    @abstractmethod
    def explain(self, state: Dict[str, Any]) -> str:
        """
        Interpretability: explain WHY the agent produced its output.
        Used for COS evaluation on interpretability dimension.
        """

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the LLM system prompt for this agent."""

    # ── Guarded execution ─────────────────────────────────────────────────────

    def safe_execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Run with pre/post guardrail + COS evaluation on explanation."""
        t0 = time.perf_counter()

        # ── Pre-guard: check incoming query ──
        query = self._extract_query(state)
        pre = self.guardrail.check(query, context=state)
        if not pre.allowed:
            state["guardrail_blocked"] = True
            state["guardrail_reasons"] = pre.reasons
            state[f"{self.AGENT_NAME}_output"] = (
                f"[BLOCKED] {self.AGENT_NAME} guardrail: {', '.join(pre.reasons)}"
            )
            return state

        # ── Execute ──
        try:
            state = self.run(state)
        except Exception as exc:
            logger.exception("Agent %s crashed: %s", self.AGENT_NAME, exc)
            state[f"{self.AGENT_NAME}_output"] = f"[ERROR] {self.AGENT_NAME}: {exc}"
            return state

        # ── Post-guard: check output ──
        output = state.get(f"{self.AGENT_NAME}_output", "")
        post = self.guardrail.check(str(output), context=state)
        if not post.allowed:
            state[f"{self.AGENT_NAME}_output"] = (
                "[FILTERED] Output blocked by ethical guardrail."
            )
        elif post.sanitized_output:
            state[f"{self.AGENT_NAME}_output"] = post.sanitized_output

        # ── Evaluate interpretability explanation ──
        explanation = self.explain(state)
        cos = self.evaluator.evaluate(
            output=explanation,
            context={
                "tenant_id": self.tenant_id,
                "agent_id":  self.AGENT_NAME,
                "trace_id":  state.get("trace_id", ""),
                "timestamp": state.get("timestamp", ""),
            },
        )

        duration = (time.perf_counter() - t0) * 1000

        result = AgentResult(
            agent_id=self.agent_uid,
            agent_name=self.AGENT_NAME,
            output=output,
            explanation=explanation,
            cos_result=cos.to_dict(),
            metadata={"tenant_id": self.tenant_id, "trace_id": state.get("trace_id")},
            duration_ms=duration,
        )
        self._history.append(result)

        # Store COS in state
        state.setdefault("agent_cos_scores", {})[self.AGENT_NAME] = cos.to_dict()

        logger.info(
            "Agent %s | cos=%.4f | passed=%s | %.0fms",
            self.AGENT_NAME, cos.cos, cos.passed, duration,
        )
        return state

    # ── LLM helper ───────────────────────────────────────────────────────────

    def _llm_invoke(self, prompt: str, state: Dict[str, Any]) -> str:
        """Invoke the configured LLM with system prompt + user prompt."""
        from workflows.llm_router import LLMRouter
        llm = LLMRouter.get(
            state.get("llm_provider", self.llm_provider),
            state.get("llm_model", self.llm_model),
        )
        system = self.get_system_prompt()
        full_prompt = f"SYSTEM: {system}\n\nUSER: {prompt}"
        try:
            response = llm.invoke(full_prompt)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.error("LLM error in %s: %s", self.AGENT_NAME, exc)
            return f"[LLM_ERROR] {exc}"

    @staticmethod
    def _extract_query(state: Dict[str, Any]) -> str:
        msgs = state.get("messages", [])
        if msgs:
            return msgs[0].get("content", "")
        return state.get("user_query", "")

    def get_history(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._history]
