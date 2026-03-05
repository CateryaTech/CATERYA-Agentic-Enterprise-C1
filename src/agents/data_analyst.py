"""
Data Analyst Agent
Author  : Ary HH <cateryatech@proton.me>
"""
from __future__ import annotations
from typing import Any, Dict
from src.agents.base import BaseCateryaAgent


class DataAnalystAgent(BaseCateryaAgent):
    AGENT_NAME = "data_analyst"
    AGENT_ROLE = "Data schema, pipeline, and analytics design"

    def get_system_prompt(self) -> str:
        return """You are a Senior Data Analyst and Data Engineer.
Design data models, ETL pipelines, and analytics schemas for SaaS products.

Output:
## Data Entities & Schema (with field types, constraints, indexes)
## Data Relationships (ERD description)
## Analytics Events (for product analytics)
## Data Pipeline Architecture
## Privacy & GDPR Considerations
## Performance Considerations (partitioning, caching strategy)

Use PostgreSQL-compatible syntax. Flag all PII fields explicitly.
Apply privacy-by-design principles. Be transparent about trade-offs.
"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        reqs = state.get("requirements_output", self._extract_query(state))
        prompt = f"""Design the data architecture for this SaaS:

REQUIREMENTS:
{reqs[:2000]}

Produce: entity schemas, relationships, analytics events, pipeline design,
GDPR data mapping, and caching strategy."""

        output = self._llm_invoke(prompt, state)
        state["data_analysis_output"] = output
        state["messages"] = state.get("messages", []) + [
            {"role": "assistant", "content": output, "agent": self.AGENT_NAME}
        ]
        return state

    def explain(self, state: Dict[str, Any]) -> str:
        return (
            "I designed the data architecture by first identifying core entities "
            "from the requirements, then normalising to 3NF while pragmatically "
            "denormalising hot paths. PII fields are flagged for GDPR compliance. "
            "Analytics events follow the segment.io spec for ecosystem compatibility. "
            "Trade-offs between normalisation and query performance are documented."
        )
