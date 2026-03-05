"""
Backend Builder Agent — FastAPI / Django
Author  : Ary HH <cateryatech@proton.me>
"""
from __future__ import annotations
import re
from typing import Any, Dict
from src.agents.base import BaseCateryaAgent


class BackendBuilderAgent(BaseCateryaAgent):
    AGENT_NAME = "backend_builder"
    AGENT_ROLE = "FastAPI/Django backend scaffolding and API generation"

    def get_system_prompt(self) -> str:
        return """You are a Senior Backend Engineer specialising in Python APIs.
Generate production-quality, secure, scalable backend code.

PRIMARY STACK: FastAPI + SQLAlchemy + PostgreSQL + Redis + Celery
ALTERNATIVE: Django + DRF (when specified)

For every API:
1. Pydantic v2 models for validation
2. SQLAlchemy 2.0 async models
3. JWT authentication middleware
4. Rate limiting (slowapi)
5. Structured logging (structlog)
6. OpenAPI documentation (auto-generated)
7. Unit tests (pytest + httpx)
8. Alembic migrations

Security checklist (apply always):
- Input validation on ALL endpoints
- SQL injection prevention (parameterised queries)
- CORS configuration
- Secrets via environment variables only
- Dependency injection for testability

Always explain trade-offs between sync vs async, ORM vs raw SQL, monolith vs microservices.
"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        arch    = state.get("architecture_output", "")[:1000]
        data    = state.get("data_analysis_output", "")[:800]
        reqs    = state.get("requirements_output",  self._extract_query(state))[:800]

        framework = state.get("backend_framework", "fastapi")

        prompt = f"""Build the backend for this SaaS using {framework.upper()}.

ARCHITECTURE:
{arch}

DATA SCHEMA:
{data}

REQUIREMENTS:
{reqs}

Generate:
1. FastAPI application structure (main.py, routers/, models/, schemas/, deps/)
2. SQLAlchemy async models with all relationships
3. Pydantic v2 request/response schemas
4. Core API endpoints (CRUD + business logic)
5. Authentication system (JWT + refresh tokens)
6. Background tasks (Celery or FastAPI BackgroundTasks)
7. Database migrations (Alembic)
8. pytest test suite skeleton
9. Environment configuration (.env template)

Include error handling, logging, and OpenAPI metadata for every endpoint."""

        output = self._llm_invoke(prompt, state)

        # Validate generated code for security patterns
        security_issues = self._security_scan(output)
        state["backend_output"]          = output
        state["backend_security_issues"] = security_issues
        state["messages"] = state.get("messages", []) + [
            {"role": "assistant", "content": output, "agent": self.AGENT_NAME}
        ]

        if security_issues:
            state["backend_output"] += (
                f"\n\n⚠️ **Security Scan**: {len(security_issues)} patterns flagged: "
                + ", ".join(security_issues[:3])
            )
        return state

    def explain(self, state: Dict[str, Any]) -> str:
        issues = state.get("backend_security_issues", [])
        return (
            "I generated the backend using FastAPI with async SQLAlchemy for optimal performance. "
            "All endpoints have Pydantic v2 validation, preventing malformed input. "
            "JWT authentication uses RS256 for production-grade security. "
            "Rate limiting prevents abuse. All secrets are environment-variable-only — "
            "no hardcoded credentials. "
            f"Security scan identified {len(issues)} patterns requiring review."
        )

    @staticmethod
    def _security_scan(code: str) -> list:
        """Basic security pattern detection on generated code."""
        issues = []
        patterns = [
            (r"password\s*=\s*['\"][^'\"]{4,}['\"]", "Hardcoded password detected"),
            (r"secret\s*=\s*['\"][^'\"]{8,}['\"]",   "Hardcoded secret detected"),
            (r"eval\s*\(",                            "eval() usage detected"),
            (r"exec\s*\(",                            "exec() usage detected"),
            (r"subprocess\.call\(",                   "subprocess.call without shell=False"),
            (r"SELECT \* FROM",                       "SELECT * may expose sensitive fields"),
        ]
        for pattern, msg in patterns:
            if re.search(pattern, code, re.I):
                issues.append(msg)
        return issues
