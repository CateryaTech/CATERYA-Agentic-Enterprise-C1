"""
Builder Architect Agent
Author  : Ary HH <cateryatech@proton.me>
"""
from __future__ import annotations
from typing import Any, Dict
from src.agents.base import BaseCateryaAgent


class BuilderArchitectAgent(BaseCateryaAgent):
    AGENT_NAME = "architect"
    AGENT_ROLE = "System architecture and tech stack design"

    def get_system_prompt(self) -> str:
        return """You are a Principal Software Architect with 15+ years experience in SaaS.
Design scalable, maintainable, secure system architectures.

Output:
## System Architecture Overview (C4 Model: Context, Container, Component)
## Technology Stack (with justification for each choice)
## API Design (REST/GraphQL endpoints, versioning strategy)
## Infrastructure Design (cloud-native, multi-region considerations)
## Security Architecture (auth flows, encryption, network segmentation)
## Scalability Strategy (horizontal scaling, caching, CDN)
## Development Workflow (branching, CI/CD approach)
## Cost Estimation (rough infra cost ranges)

Be technology-agnostic in evaluation. Justify every choice with trade-offs.
Consider teams of different sizes and skill levels.
"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        reqs    = state.get("requirements_output",    "")[:1500]
        market  = state.get("market_analysis_output", "")[:500]
        data    = state.get("data_analysis_output",   "")[:500]

        prompt = f"""Design the complete system architecture for this SaaS:

REQUIREMENTS SUMMARY:
{reqs}

MARKET CONTEXT: {market[:300]}
DATA DESIGN SUMMARY: {data[:300]}

Produce full architecture with C4 diagrams (text), tech stack with trade-offs,
API design, infrastructure, security architecture, and cost estimation."""

        output = self._llm_invoke(prompt, state)
        state["architecture_output"] = output
        state["tech_stack"] = self._extract_tech_stack(output)
        state["messages"] = state.get("messages", []) + [
            {"role": "assistant", "content": output, "agent": self.AGENT_NAME}
        ]
        return state

    def explain(self, state: Dict[str, Any]) -> str:
        stack = state.get("tech_stack", {})
        return (
            f"I designed the system architecture by first understanding the scale requirements, "
            f"then selecting a technology stack ({stack}) based on team familiarity, "
            f"ecosystem maturity, and operational simplicity. "
            f"The architecture follows cloud-native principles with explicit trade-off documentation. "
            f"Security is built-in at each layer, not bolted on. "
            f"I considered both startup (low cost) and enterprise (high scale) scenarios."
        )

    @staticmethod
    def _extract_tech_stack(output: str) -> Dict[str, str]:
        """Heuristic extraction of tech mentions from architecture output."""
        tech = {}
        keywords = {
            "frontend": ["react", "next.js", "vue", "angular", "svelte"],
            "backend":  ["fastapi", "django", "express", "nestjs", "rails"],
            "database": ["postgresql", "mysql", "mongodb", "redis", "cassandra"],
            "infra":    ["kubernetes", "docker", "aws", "gcp", "azure"],
        }
        lower = output.lower()
        for category, terms in keywords.items():
            for term in terms:
                if term in lower:
                    tech[category] = term
                    break
        return tech
