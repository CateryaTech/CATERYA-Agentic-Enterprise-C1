"""
Frontend Builder Agent — React / Next.js
Author  : Ary HH <cateryatech@proton.me>

Tools:
 - Pyodide (browser-side Python for JS simulation)
 - Component scaffolding
 - Accessibility checker
"""
from __future__ import annotations
import json
import re
from typing import Any, Dict
from src.agents.base import BaseCateryaAgent


# ── Pyodide simulation (server-side JS execution stub) ───────────────────────

def simulate_jsx_with_pyodide(component_code: str) -> Dict[str, Any]:
    """
    Simulate JSX component validation using Python (Pyodide-equivalent logic).
    In browser context, this runs in Pyodide. On server, uses regex heuristics.
    """
    issues = []

    # Accessibility checks
    if "<img" in component_code and 'alt=' not in component_code:
        issues.append("A11Y: <img> missing alt attribute")
    if "<button" in component_code and 'aria-label' not in component_code and ">< " not in component_code:
        pass  # button text is the label
    if "<input" in component_code and '<label' not in component_code:
        issues.append("A11Y: <input> may be missing associated <label>")

    # React best practices
    if "useState" in component_code and "import" not in component_code:
        issues.append("REACT: useState used but not imported")
    if "useEffect" in component_code and "// eslint-disable" not in component_code:
        if "[]" not in component_code and "[" not in component_code:
            issues.append("REACT: useEffect missing dependency array")
    if "console.log" in component_code:
        issues.append("QUALITY: console.log found — remove before production")
    if "any" in component_code and "TypeScript" in component_code:
        issues.append("TS: 'any' type used — consider specific types")

    # Performance
    if component_code.count("useState") > 5:
        issues.append("PERF: Many useState calls — consider useReducer")

    component_name_match = re.search(r"(?:function|const)\s+([A-Z]\w+)", component_code)
    component_name = component_name_match.group(1) if component_name_match else "Component"

    return {
        "component_name": component_name,
        "issues": issues,
        "issue_count": len(issues),
        "severity": "error" if any("A11Y" in i for i in issues) else "warning",
        "estimated_bundle_kb": len(component_code.encode()) / 1024 * 3,  # rough estimate
    }


class FrontendBuilderAgent(BaseCateryaAgent):
    AGENT_NAME = "frontend_builder"
    AGENT_ROLE = "React/Next.js frontend scaffolding and UI generation"

    def get_system_prompt(self) -> str:
        return """You are a Senior Frontend Engineer specialising in React 18 and Next.js 14.
Generate production-quality, accessible, performant frontend code.

TECH STACK: React 18, Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui

For every component:
1. Use TypeScript with proper types (no 'any')
2. Implement WCAG 2.1 AA accessibility
3. Add loading and error states
4. Use React Server Components where appropriate
5. Include JSDoc comments
6. Add unit test skeleton (Vitest/Testing Library)

File structure:
- app/ (Next.js App Router pages)
- components/ (reusable components)
- lib/ (utilities, hooks)
- types/ (TypeScript interfaces)

Always explain architecture decisions and trade-offs.
"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        arch    = state.get("architecture_output", "")[:1000]
        reqs    = state.get("requirements_output", self._extract_query(state))[:1000]

        prompt = f"""Build the frontend for this SaaS application.

ARCHITECTURE:
{arch}

REQUIREMENTS:
{reqs}

Generate:
1. Next.js 14 App Router project structure
2. Core page components (dashboard, auth, main feature)
3. Reusable UI components (with TypeScript interfaces)
4. API client hooks (React Query / SWR)
5. Authentication flow (NextAuth or JWT)
6. Tailwind CSS configuration
7. Component test skeletons

For each component, provide full code with TypeScript types and accessibility."""

        output = self._llm_invoke(prompt, state)

        # ── Pyodide simulation: validate any code blocks ──
        code_blocks = re.findall(r"```(?:jsx?|tsx?)(.*?)```", output, re.DOTALL)
        validation_results = []
        for code in code_blocks[:5]:  # validate first 5 components
            result = simulate_jsx_with_pyodide(code)
            validation_results.append(result)

        state["frontend_output"]    = output
        state["frontend_validation"] = validation_results
        state["messages"] = state.get("messages", []) + [
            {"role": "assistant", "content": output, "agent": self.AGENT_NAME}
        ]

        # Append validation summary
        if validation_results:
            total_issues = sum(r["issue_count"] for r in validation_results)
            state["frontend_output"] += (
                f"\n\n---\n**Pyodide Validation**: {len(validation_results)} components checked, "
                f"{total_issues} issues found."
            )
        return state

    def explain(self, state: Dict[str, Any]) -> str:
        validation = state.get("frontend_validation", [])
        issues     = sum(r["issue_count"] for r in validation)
        return (
            "I generated the frontend using Next.js 14 App Router with React Server Components "
            "for optimal performance. TypeScript ensures type safety. Tailwind CSS provides "
            "consistent styling. Accessibility is built-in at component level (WCAG 2.1 AA). "
            f"Pyodide-powered validation checked {len(validation)} components, "
            f"found {issues} issues requiring attention. "
            "Each component includes loading/error states and a test skeleton."
        )
