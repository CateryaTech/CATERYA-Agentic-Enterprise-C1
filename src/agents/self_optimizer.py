"""
Self-Optimizer Agent — Auto-tunes based on COS feedback
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

The SelfOptimizerAgent monitors COS scores across all agents and:
1. Identifies which pillar is lowest for each agent
2. Generates targeted prompt improvements
3. Adjusts pillar weights for better balance
4. Recommends LLM model changes when scores degrade
5. Creates optimisation reports for operators
"""

from __future__ import annotations

import json
import logging
import statistics
from typing import Any, Dict, List, Optional, Tuple

from src.agents.base import BaseCateryaAgent

logger = logging.getLogger(__name__)


class SelfOptimizerAgent(BaseCateryaAgent):
    """
    Autonomous agent that analyses COS history and generates optimisation actions.

    Usage::

        optimizer = SelfOptimizerAgent(tenant_id="acme")
        result = optimizer.optimize(
            cos_history=[result1.to_dict(), result2.to_dict()],
            agent_name="security_auditor",
        )
        print(result["recommendations"])
        print(result["new_weights"])
    """

    AGENT_NAME = "self_optimizer"
    AGENT_ROLE = "Autonomous COS-based performance optimisation"

    def get_system_prompt(self) -> str:
        return """You are an AI performance optimisation expert.
Analyse COS (Composite Overall Score) evaluation results and produce
specific, actionable improvements.

For each failing pillar, provide:
1. Root cause analysis (why is it failing?)
2. Specific prompt modifications (exact text changes)
3. Expected improvement in score (quantified estimate)
4. Implementation priority (1-5)

Output format: JSON with keys: analysis, recommendations, new_weights, priority_actions
"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        cos_history  = state.get("cos_history",  [])
        agent_target = state.get("agent_target", "all")

        analysis = self._analyse_cos_history(cos_history, agent_target)
        recs      = self._generate_recommendations(analysis)
        weights   = self._optimise_weights(analysis)

        state["optimizer_output"] = json.dumps({
            "analysis":        analysis,
            "recommendations": recs,
            "new_weights":     weights,
        }, indent=2)
        return state

    def explain(self, state: Dict[str, Any]) -> str:
        analysis = state.get("optimizer_analysis", {})
        worst    = analysis.get("worst_pillar", "unknown")
        avg_cos  = analysis.get("average_cos", 0.0)
        return (
            f"I analysed the COS history and identified '{worst}' as the consistently "
            f"lowest pillar (average COS: {avg_cos:.4f}). "
            f"Recommendations target root causes with specific prompt modifications. "
            f"Weight adjustments balance pillars for higher overall COS. "
            f"All changes are reversible and tracked in ProvenanceChain."
        )

    def optimize(
        self,
        cos_history: List[Dict[str, Any]],
        agent_name: str = "all",
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Main optimisation entry point."""
        state = {
            "cos_history":    cos_history,
            "agent_target":   agent_name,
            "tenant_id":      tenant_id or self.tenant_id,
            "messages":       [{"role": "user", "content": f"Optimise {agent_name}"}],
            "trace_id":       "optimizer",
            "timestamp":      "now",
        }
        state = self.safe_execute(state)
        analysis = self._analyse_cos_history(cos_history, agent_name)

        return {
            "agent_name":      agent_name,
            "analysis":        analysis,
            "recommendations": self._generate_recommendations(analysis),
            "new_weights":     self._optimise_weights(analysis),
            "cos_delta":       self._estimate_improvement(analysis),
        }

    # ── Internal ────────────────────────────────────────────────────────────

    def _analyse_cos_history(
        self, history: List[Dict], agent_name: str
    ) -> Dict[str, Any]:
        if not history:
            return {"average_cos": 0.0, "worst_pillar": "unknown", "trend": "no_data"}

        cos_scores = [h.get("cos", 0.0) for h in history]
        avg_cos    = statistics.mean(cos_scores)
        trend      = "improving" if len(cos_scores) >= 2 and cos_scores[-1] > cos_scores[0] else \
                     "degrading" if len(cos_scores) >= 2 and cos_scores[-1] < cos_scores[0] else "stable"

        # Aggregate pillar scores
        pillar_avgs: Dict[str, List[float]] = {}
        for h in history:
            for p in h.get("pillars", []):
                name  = p.get("name", "unknown")
                score = p.get("score", 0.0)
                pillar_avgs.setdefault(name, []).append(score)

        pillar_means = {
            name: statistics.mean(scores)
            for name, scores in pillar_avgs.items()
        }
        worst_pillar = min(pillar_means, key=pillar_means.get) if pillar_means else "unknown"

        return {
            "agent_name":    agent_name,
            "sample_size":   len(history),
            "average_cos":   round(avg_cos, 4),
            "min_cos":       round(min(cos_scores), 4),
            "max_cos":       round(max(cos_scores), 4),
            "trend":         trend,
            "pillar_means":  {k: round(v, 4) for k, v in pillar_means.items()},
            "worst_pillar":  worst_pillar,
            "pass_rate":     round(sum(1 for c in cos_scores if c >= 0.7) / len(cos_scores), 4),
        }

    def _generate_recommendations(self, analysis: Dict) -> List[Dict[str, Any]]:
        worst = analysis.get("worst_pillar", "unknown")
        recs  = []

        prompt_fixes = {
            "bias_fairness": {
                "fix": "Add explicit instruction: 'Consider both men and women, all ethnicities, and age groups equally. Use balanced examples.'",
                "priority": 1, "expected_gain": 0.08,
            },
            "transparency": {
                "fix": "Add: 'Always cite your reasoning step by step. Use phrases like: According to..., Based on..., I believe because...'",
                "priority": 1, "expected_gain": 0.10,
            },
            "safety": {
                "fix": "Add: 'Add a disclaimer when discussing potentially sensitive topics: This is not professional advice.'",
                "priority": 2, "expected_gain": 0.06,
            },
            "accountability": {
                "fix": "Ensure all agent calls include trace_id, agent_id, timestamp in context dict.",
                "priority": 1, "expected_gain": 0.12,
            },
            "privacy": {
                "fix": "Enable CATERYAGuardrail redact_pii=True on all agent nodes.",
                "priority": 1, "expected_gain": 0.10,
            },
            "robustness": {
                "fix": "Structure output with headers (##), numbered lists, and use 'therefore/because' connectors.",
                "priority": 2, "expected_gain": 0.07,
            },
            "interpretability": {
                "fix": "Add to system prompt: 'Explain your reasoning with Feynman-level clarity. Use: because, therefore, for example, step 1/2/3.'",
                "priority": 1, "expected_gain": 0.09,
            },
        }

        if worst in prompt_fixes:
            recs.append({"pillar": worst, **prompt_fixes[worst]})

        # General improvements if COS < 0.8
        if analysis.get("average_cos", 1.0) < 0.8:
            recs.append({
                "pillar":        "general",
                "fix":           "Consider upgrading to llama3:70b or groq/llama3-70b for higher quality outputs.",
                "priority":      3,
                "expected_gain": 0.05,
            })

        return sorted(recs, key=lambda r: r["priority"])

    def _optimise_weights(self, analysis: Dict) -> Dict[str, float]:
        """Adjust pillar weights to emphasise weakest areas."""
        from src.caterya.core.evaluator import DEFAULT_WEIGHTS
        base = dict(DEFAULT_WEIGHTS)
        pillar_means = analysis.get("pillar_means", {})

        if not pillar_means:
            return base

        # Increase weight for worst pillar, decrease for best
        worst  = min(pillar_means, key=pillar_means.get)
        best   = max(pillar_means, key=pillar_means.get)

        if worst in base and best in base and worst != best:
            transfer = 0.03
            base[worst] = min(0.40, base[worst] + transfer)
            base[best]  = max(0.10, base[best]  - transfer)

        # Normalise
        total = sum(base.values())
        return {k: round(v / total, 4) for k, v in base.items()}

    def _estimate_improvement(self, analysis: Dict) -> float:
        """Estimate expected COS improvement after applying recommendations."""
        current = analysis.get("average_cos", 0.0)
        worst_score = min(analysis.get("pillar_means", {}).values() or [current])
        potential = min(0.15, (0.9 - current) * 0.5)
        return round(potential, 4)
