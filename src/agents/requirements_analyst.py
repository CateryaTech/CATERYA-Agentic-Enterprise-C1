"""
Requirements Analyst Agent
Author  : Ary HH <cateryatech@proton.me>
"""
from __future__ import annotations
from typing import Any, Dict
from src.agents.base import BaseCateryaAgent


class RequirementsAnalystAgent(BaseCateryaAgent):
    AGENT_NAME = "requirements_analyst"
    AGENT_ROLE = "Analyse and structure SaaS requirements"

    def get_system_prompt(self) -> str:
        return """You are a Senior Requirements Analyst specialising in SaaS products.
Your job: extract, structure, and prioritise software requirements from user input.

Output format (always):
## Functional Requirements
- FR-001: ...
- FR-002: ...

## Non-Functional Requirements
- NFR-001: Performance: ...
- NFR-002: Security: ...

## User Stories
- As a [role], I want [feature] so that [benefit]

## Acceptance Criteria
- [Testable criteria for each requirement]

## Out of Scope
- [What is explicitly excluded]

Be specific, testable, and unambiguous. Acknowledge uncertainty where present.
Consider diverse user demographics and accessibility requirements (WCAG 2.1 AA).
"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        query = self._extract_query(state)
        prompt = f"""Analyse the following SaaS idea and produce structured requirements:

PROJECT: {query}

Additional context:
- Target market: {state.get('target_market', 'global')}
- Scale: {state.get('scale', 'startup to enterprise')}
- Compliance: {state.get('compliance', 'GDPR, SOC2')}

Produce complete, prioritised requirements."""

        output = self._llm_invoke(prompt, state)
        state["requirements_output"] = output
        state["messages"] = state.get("messages", []) + [
            {"role": "assistant", "content": output, "agent": self.AGENT_NAME}
        ]
        return state

    def explain(self, state: Dict[str, Any]) -> str:
        output = state.get("requirements_output", "")
        query  = self._extract_query(state)
        return (
            f"I analysed the project '{query[:100]}' and identified requirements "
            f"by decomposing the user's goals into functional and non-functional categories. "
            f"Based on best practices for SaaS architecture, I prioritised requirements "
            f"by business value and technical feasibility. "
            f"The output contains {output.count('FR-') + output.count('NFR-')} "
            f"structured requirements with acceptance criteria."
        )
