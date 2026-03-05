"""
Market Analyst Agent
Author  : Ary HH <cateryatech@proton.me>
"""
from __future__ import annotations
from typing import Any, Dict
from src.agents.base import BaseCateryaAgent


class MarketAnalystAgent(BaseCateryaAgent):
    AGENT_NAME = "market_analyst"
    AGENT_ROLE = "Competitive market analysis and positioning"

    def get_system_prompt(self) -> str:
        return """You are a Senior Market Analyst specialising in SaaS and technology markets.
Provide balanced, evidence-based market analysis.

Always structure output as:
## Market Overview
## Target Segments (with sizing estimates)
## Competitive Landscape (fair comparison of all players)
## Differentiation Opportunities
## Go-to-Market Strategy
## Risk Factors
## Revenue Model Recommendations

Critical: Represent all market participants fairly. Do not favour any demographic group.
Acknowledge data limitations and uncertainty ranges for all estimates.
"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        reqs = state.get("requirements_output", self._extract_query(state))
        prompt = f"""Conduct a market analysis for this SaaS product:

REQUIREMENTS SUMMARY:
{reqs[:2000]}

Provide TAM/SAM/SOM estimates, competitive analysis (min 5 competitors),
differentiation strategy, and pricing model recommendations.
Base all estimates on publicly available market data patterns."""

        output = self._llm_invoke(prompt, state)
        state["market_analysis_output"] = output
        state["messages"] = state.get("messages", []) + [
            {"role": "assistant", "content": output, "agent": self.AGENT_NAME}
        ]
        return state

    def explain(self, state: Dict[str, Any]) -> str:
        return (
            "I conducted market analysis by examining the competitive landscape, "
            "estimating market size using bottom-up analysis, and identifying "
            "differentiation opportunities based on the stated requirements. "
            "All competitive comparisons were made fairly without bias toward "
            "any particular company or demographic. Estimates are ranges, not absolutes."
        )
