"""
SaaS Builder Workflow — Full Pipeline via LangGraph
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Pipeline:
  Requirements Analyst
       ↓
  Market Analyst + Data Analyst  (parallel)
       ↓
  Builder Architect
       ↓
  Frontend Builder + Backend Builder  (parallel)
       ↓
  Developer Tester
       ↓
  DevOps Integrator
       ↓
  Performance Optimizer + Security Auditor  (parallel)
       ↓
  COS Evaluation + ProvenanceChain
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import StateGraph, END

from src.caterya.core.evaluator import CATERYAEvaluator
from src.caterya.core.guardrail import CATERYAGuardrail
from src.caterya.blockchain.provenance_chain import ProvenanceChain
from src.agents.requirements_analyst  import RequirementsAnalystAgent
from src.agents.market_analyst         import MarketAnalystAgent
from src.agents.data_analyst           import DataAnalystAgent
from src.agents.builder_architect      import BuilderArchitectAgent
from src.agents.frontend_builder       import FrontendBuilderAgent
from src.agents.backend_builder        import BackendBuilderAgent
from src.agents.specialist_agents      import (
    DeveloperTesterAgent, DevOpsIntegratorAgent,
    PerformanceOptimizerAgent, SecurityAuditorAgent,
)

logger = logging.getLogger(__name__)


# ── State definition ──────────────────────────────────────────────────────────

class SaaSBuildState(TypedDict):
    # Identity
    session_id:           str
    tenant_id:            str
    user_id:              Optional[str]
    trace_id:             str
    timestamp:            str
    # Input
    messages:             List[Dict[str, str]]
    user_query:           str
    target_market:        str
    scale:                str
    backend_framework:    str
    llm_provider:         str
    llm_model:            str
    # Agent outputs
    requirements_output:   Optional[str]
    market_analysis_output: Optional[str]
    data_analysis_output:  Optional[str]
    architecture_output:   Optional[str]
    tech_stack:            Dict[str, str]
    frontend_output:       Optional[str]
    frontend_validation:   List[Dict]
    backend_output:        Optional[str]
    backend_security_issues: List[str]
    test_output:           Optional[str]
    test_coverage_est:     int
    devops_output:         Optional[str]
    performance_output:    Optional[str]
    security_output:       Optional[str]
    security_findings:     Dict[str, int]
    # Evaluation
    cos_result:            Optional[Dict]
    agent_cos_scores:      Dict[str, Dict]
    # Robustness
    stability_index:       float
    # Guardrail
    guardrail_blocked:     bool
    guardrail_reasons:     List[str]
    # Provenance
    provenance_chain:      List[Dict]
    # Pipeline status
    pipeline_stage:        str
    pipeline_complete:     bool


def make_saas_state(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    llm_provider: str = "ollama",
    llm_model: str = "llama3",
    target_market: str = "global",
    scale: str = "startup to enterprise",
    backend_framework: str = "fastapi",
) -> SaaSBuildState:
    return SaaSBuildState(
        session_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        trace_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        messages=[{"role": "user", "content": query}],
        user_query=query,
        target_market=target_market,
        scale=scale,
        backend_framework=backend_framework,
        llm_provider=llm_provider,
        llm_model=llm_model,
        requirements_output=None,
        market_analysis_output=None,
        data_analysis_output=None,
        architecture_output=None,
        tech_stack={},
        frontend_output=None,
        frontend_validation=[],
        backend_output=None,
        backend_security_issues=[],
        test_output=None,
        test_coverage_est=0,
        devops_output=None,
        performance_output=None,
        security_output=None,
        security_findings={},
        cos_result=None,
        agent_cos_scores={},
        stability_index=0.0,
        guardrail_blocked=False,
        guardrail_reasons=[],
        provenance_chain=[],
        pipeline_stage="init",
        pipeline_complete=False,
    )


# ── Workflow class ────────────────────────────────────────────────────────────

class SaaSBuilderWorkflow:
    """
    Full SaaS development pipeline via LangGraph.

    Usage::

        wf = SaaSBuilderWorkflow(tenant_id="acme")
        result = wf.run(
            query="Build a project management SaaS like Linear",
            llm_provider="ollama",
            llm_model="llama3",
        )
    """

    def __init__(
        self,
        tenant_id: str,
        cos_threshold: float = 0.7,
        llm_provider: str = "ollama",
        llm_model: str = "llama3",
        redis_client: Optional[Any] = None,
    ):
        self.tenant_id    = tenant_id
        self.cos_threshold = cos_threshold
        self.llm_provider = llm_provider
        self.llm_model    = llm_model
        self.redis        = redis_client

        # ── Initialise all agents ──
        self.agents = {
            "requirements": RequirementsAnalystAgent(tenant_id, llm_provider, llm_model),
            "market":       MarketAnalystAgent(tenant_id, llm_provider, llm_model),
            "data":         DataAnalystAgent(tenant_id, llm_provider, llm_model),
            "architect":    BuilderArchitectAgent(tenant_id, llm_provider, llm_model),
            "frontend":     FrontendBuilderAgent(tenant_id, llm_provider, llm_model),
            "backend":      BackendBuilderAgent(tenant_id, llm_provider, llm_model),
            "tester":       DeveloperTesterAgent(tenant_id, llm_provider, llm_model),
            "devops":       DevOpsIntegratorAgent(tenant_id, llm_provider, llm_model),
            "performance":  PerformanceOptimizerAgent(tenant_id, llm_provider, llm_model),
            "security":     SecurityAuditorAgent(tenant_id, llm_provider, llm_model),
        }

        self.evaluator  = CATERYAEvaluator(threshold=cos_threshold, tenant_id=tenant_id)
        self.provenance = ProvenanceChain(tenant_id=tenant_id)
        self._graph     = self._build_graph()

    # ── Graph construction ────────────────────────────────────────────────────

    def _build_graph(self):
        g = StateGraph(SaaSBuildState)

        # ── Nodes ──
        g.add_node("requirements",  self._node("requirements"))
        g.add_node("market",        self._node("market"))
        g.add_node("data",          self._node("data"))
        g.add_node("architect",     self._node("architect"))
        g.add_node("frontend",      self._node("frontend"))
        g.add_node("backend",       self._node("backend"))
        g.add_node("tester",        self._node("tester"))
        g.add_node("devops",        self._node("devops"))
        g.add_node("performance",   self._node("performance"))
        g.add_node("security",      self._node("security"))
        g.add_node("evaluate",      self._evaluate_node)

        # ── Edges ──
        g.set_entry_point("requirements")

        def route(state):
            return "blocked" if state.get("guardrail_blocked") else "continue"

        # Sequential pipeline with guardrail checks
        for src, dst in [
            ("requirements", "market"),
            ("market",       "data"),
            ("data",         "architect"),
            ("architect",    "frontend"),
            ("frontend",     "backend"),
            ("backend",      "tester"),
            ("tester",       "devops"),
            ("devops",       "performance"),
            ("performance",  "security"),
            ("security",     "evaluate"),
        ]:
            g.add_conditional_edges(src, route, {"blocked": END, "continue": dst})

        g.add_edge("evaluate", END)
        return g.compile()

    def _node(self, agent_key: str):
        agent = self.agents[agent_key]

        def node_fn(state: SaaSBuildState) -> SaaSBuildState:
            state["pipeline_stage"] = agent_key
            logger.info("Pipeline stage: %s | tenant=%s", agent_key, self.tenant_id)

            state = agent.safe_execute(state)

            # Record to provenance chain
            output_key = f"{agent.AGENT_NAME}_output"
            self.provenance.record(
                agent_id=agent.AGENT_NAME,
                action=agent_key,
                input_data=self._extract_query(state),
                output_data=state.get(output_key, "")[:500],
                metadata={"tenant_id": self.tenant_id, "stage": agent_key},
            )
            return state

        node_fn.__name__ = agent_key
        return node_fn

    def _evaluate_node(self, state: SaaSBuildState) -> SaaSBuildState:
        """Final COS evaluation across all agent explanations."""
        # Build composite explanation for evaluation
        composite = " ".join(filter(None, [
            state.get("requirements_output",   "")[:200],
            state.get("architecture_output",   "")[:200],
            state.get("backend_output",        "")[:200],
            state.get("security_output",       "")[:200],
        ]))

        cos = self.evaluator.evaluate(
            output=composite,
            context={
                "tenant_id": self.tenant_id,
                "agent_id":  "pipeline",
                "trace_id":  state["trace_id"],
                "timestamp": state["timestamp"],
            },
        )

        # Robustness: evaluate stability on security output (most critical)
        from src.caterya.pillars.robustness import RobustnessPillar
        stab_score, _ = RobustnessPillar().evaluate(
            state.get("security_output", composite)
        )

        state["cos_result"]       = cos.to_dict()
        state["stability_index"]  = stab_score
        state["provenance_chain"] = self.provenance.get_chain()
        state["pipeline_complete"] = True
        state["pipeline_stage"]   = "complete"

        if self.redis:
            self._persist(state)

        logger.info(
            "Pipeline complete | tenant=%s cos=%.4f stability=%.4f passed=%s",
            self.tenant_id, cos.cos, stab_score, cos.passed,
        )
        return state

    # ── Public API ────────────────────────────────────────────────────────────

    def run(
        self,
        query: str,
        user_id: Optional[str] = None,
        target_market: str = "global",
        scale: str = "startup",
        backend_framework: str = "fastapi",
    ) -> Dict[str, Any]:
        state = make_saas_state(
            query=query,
            tenant_id=self.tenant_id,
            user_id=user_id,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            target_market=target_market,
            scale=scale,
            backend_framework=backend_framework,
        )
        return self._graph.invoke(state)

    def run_streaming(self, query: str, **kwargs):
        """Yield (stage, state) tuples for streaming UI."""
        state = make_saas_state(query=query, tenant_id=self.tenant_id, **kwargs)
        for event in self._graph.stream(state):
            for stage, s in event.items():
                yield stage, s

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_query(state: Dict) -> str:
        msgs = state.get("messages", [])
        return msgs[0].get("content", "") if msgs else ""

    def _persist(self, state: SaaSBuildState) -> None:
        try:
            key = f"saas_build:{self.tenant_id}:{state['session_id']}"
            safe = {k: v for k, v in state.items()
                    if isinstance(v, (str, int, float, bool, list, dict, type(None)))}
            self.redis.setex(key, 86400 * 7, json.dumps(safe, default=str))
        except Exception as exc:
            logger.warning("Persist error: %s", exc)
