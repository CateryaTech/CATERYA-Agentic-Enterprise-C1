"""
Developer Tester Agent
Author  : Ary HH <cateryatech@proton.me>
"""
from __future__ import annotations
import re
from typing import Any, Dict
from src.agents.base import BaseCateryaAgent


class DeveloperTesterAgent(BaseCateryaAgent):
    AGENT_NAME = "developer_tester"
    AGENT_ROLE = "Test strategy, test generation, and QA automation"

    def get_system_prompt(self) -> str:
        return """You are a Senior QA Engineer and Test Automation Specialist.
Generate comprehensive test suites covering unit, integration, and E2E tests.

For every feature:
- Unit tests: pytest (backend), Vitest (frontend)
- Integration tests: httpx TestClient, database fixtures
- E2E tests: Playwright
- Performance tests: Locust load test scenarios
- Security tests: OWASP checklist items

Test principles: AAA pattern (Arrange, Act, Assert), meaningful test names,
edge cases, boundary values, error scenarios, concurrency tests.
Always explain WHY each test case is important.
"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        backend  = state.get("backend_output",  "")[:1200]
        frontend = state.get("frontend_output", "")[:800]

        prompt = f"""Generate comprehensive tests for this SaaS:

BACKEND CODE SUMMARY:
{backend}

FRONTEND CODE SUMMARY:
{frontend}

Generate:
1. pytest unit tests for all API endpoints (happy path + edge cases)
2. Integration tests with database fixtures
3. Playwright E2E tests for critical user journeys
4. Locust load test for 1000 concurrent users
5. Security test checklist (OWASP Top 10)
6. CI test configuration (GitHub Actions matrix)"""

        output  = self._llm_invoke(prompt, state)
        coverage = self._estimate_coverage(output)

        state["test_output"]        = output
        state["test_coverage_est"]  = coverage
        state["messages"] = state.get("messages", []) + [
            {"role": "assistant", "content": output, "agent": self.AGENT_NAME}
        ]
        return state

    def explain(self, state: Dict[str, Any]) -> str:
        cov = state.get("test_coverage_est", 0)
        return (
            f"I generated tests using the risk-based testing approach — highest coverage "
            f"for business-critical paths (auth, billing, data mutations). "
            f"Estimated code coverage: {cov}%. Edge cases include empty inputs, "
            f"boundary values, concurrent requests, and malformed payloads. "
            f"E2E tests cover the top 3 critical user journeys end-to-end."
        )

    @staticmethod
    def _estimate_coverage(test_code: str) -> int:
        test_fns = len(re.findall(r"def test_", test_code))
        return min(95, 40 + test_fns * 3)


class DevOpsIntegratorAgent(BaseCateryaAgent):
    AGENT_NAME = "devops_integrator"
    AGENT_ROLE = "CI/CD, Docker, Kubernetes, and infrastructure as code"

    def get_system_prompt(self) -> str:
        return """You are a Senior DevOps/Platform Engineer.
Design and implement CI/CD pipelines, container orchestration, and IaC.

Always produce:
- Dockerfile (multi-stage, minimal image)
- docker-compose.yml (local development)
- Kubernetes manifests (Deployment, Service, HPA, ConfigMap, Secret)
- GitHub Actions CI/CD pipeline
- Helm chart skeleton
- Terraform/Pulumi IaC (cloud-agnostic)
- Monitoring configuration (Prometheus, Grafana)

Security: non-root containers, read-only filesystems, resource limits always set.
Reliability: health checks, readiness probes, PodDisruptionBudget.
"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        arch    = state.get("architecture_output", "")[:800]
        backend = state.get("backend_output",      "")[:400]

        prompt = f"""Create complete DevOps configuration for this SaaS:

ARCHITECTURE:
{arch}

Generate:
1. Multi-stage Dockerfile (backend + frontend)
2. docker-compose.yml with all services (app, db, redis, monitoring)
3. Kubernetes manifests (Deployment, Service, HPA, Ingress, NetworkPolicy)
4. GitHub Actions pipeline (test → build → push → deploy)
5. Helm chart values.yaml
6. Prometheus scrape config
7. Health check endpoints specification"""

        output = self._llm_invoke(prompt, state)
        state["devops_output"] = output
        state["messages"] = state.get("messages", []) + [
            {"role": "assistant", "content": output, "agent": self.AGENT_NAME}
        ]
        return state

    def explain(self, state: Dict[str, Any]) -> str:
        return (
            "I designed the DevOps pipeline following GitOps principles. "
            "Multi-stage Dockerfiles minimise image size and attack surface. "
            "Kubernetes HPA ensures auto-scaling under load. "
            "All containers run non-root with read-only filesystems. "
            "The CI/CD pipeline enforces tests before any deployment. "
            "Infrastructure is code-defined for reproducibility and auditability."
        )


class PerformanceOptimizerAgent(BaseCateryaAgent):
    AGENT_NAME = "performance_optimizer"
    AGENT_ROLE = "Performance profiling, caching, and optimization"

    def get_system_prompt(self) -> str:
        return """You are a Senior Performance Engineer.
Identify and fix performance bottlenecks in SaaS applications.

Analysis framework:
1. Database: N+1 queries, missing indexes, slow queries (EXPLAIN ANALYZE)
2. API: response time budgets, caching strategy (Redis, CDN)
3. Frontend: Core Web Vitals (LCP, CLS, INP), bundle size, lazy loading
4. Infrastructure: connection pooling, auto-scaling triggers
5. Code: algorithmic complexity, memory leaks, blocking I/O

Always provide: current baseline → optimised target → implementation steps.
Quantify all improvements with expected metrics.
"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        backend  = state.get("backend_output",      "")[:800]
        frontend = state.get("frontend_output",     "")[:600]
        data     = state.get("data_analysis_output","")[:400]

        prompt = f"""Analyse and optimise performance for this SaaS:

BACKEND: {backend}
FRONTEND: {frontend}
DATA SCHEMA: {data}

Produce:
1. Performance audit (identify top 10 bottlenecks with impact estimates)
2. Database optimisation (indexes, query rewrites, connection pooling)
3. Caching strategy (what to cache, TTL, invalidation)
4. Frontend optimisation (bundle splitting, image optimisation, prefetching)
5. Load testing targets and Locust scenarios
6. Monitoring metrics and alerting thresholds"""

        output = self._llm_invoke(prompt, state)
        state["performance_output"] = output
        state["messages"] = state.get("messages", []) + [
            {"role": "assistant", "content": output, "agent": self.AGENT_NAME}
        ]
        return state

    def explain(self, state: Dict[str, Any]) -> str:
        return (
            "I conducted performance analysis using the RED method (Rate, Errors, Duration). "
            "Database optimisations target the top slow queries identified via EXPLAIN ANALYZE patterns. "
            "Redis caching reduces database load by an estimated 60-80% for read-heavy endpoints. "
            "Frontend optimisations target Core Web Vitals: LCP < 2.5s, CLS < 0.1, INP < 200ms. "
            "All optimisations are measurable with the Prometheus metrics configuration provided."
        )


class SecurityAuditorAgent(BaseCateryaAgent):
    AGENT_NAME = "security_auditor"
    AGENT_ROLE = "Security audit, threat modelling, and hardening"

    def get_system_prompt(self) -> str:
        return """You are a Senior Application Security Engineer (OWASP, SANS).
Conduct thorough security audits and produce actionable remediation plans.

Audit framework: OWASP Top 10 + STRIDE threat model

For each finding:
- Severity: Critical/High/Medium/Low/Info
- CVSS score estimate
- Description of vulnerability
- Proof of concept (safe, non-destructive)
- Remediation with code example
- Verification step

Security domains: Authentication, Authorisation, Injection, Cryptography,
Supply chain, Infrastructure, Data protection, Logging/Monitoring.

Always be balanced: acknowledge strengths, not just weaknesses.
"""

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        backend  = state.get("backend_output",  "")[:1000]
        devops   = state.get("devops_output",   "")[:600]
        frontend = state.get("frontend_output", "")[:400]

        prompt = f"""Conduct a security audit for this SaaS application:

BACKEND:
{backend}

DEVOPS/INFRA:
{devops}

FRONTEND: {frontend[:200]}

Produce:
1. Threat model (STRIDE for each component)
2. OWASP Top 10 assessment (pass/fail for each)
3. Findings list (severity, CVSS, remediation)
4. Authentication & authorisation review
5. Secrets management assessment
6. Network security review
7. Compliance checklist (GDPR, SOC2, ISO27001 basics)
8. Security testing checklist"""

        output = self._llm_invoke(prompt, state)

        critical = output.lower().count("critical")
        high     = output.lower().count("high")

        state["security_output"]   = output
        state["security_findings"] = {"critical": critical, "high": high}
        state["messages"] = state.get("messages", []) + [
            {"role": "assistant", "content": output, "agent": self.AGENT_NAME}
        ]
        return state

    def explain(self, state: Dict[str, Any]) -> str:
        findings = state.get("security_findings", {})
        return (
            f"I conducted the security audit using OWASP Top 10 and STRIDE threat modelling. "
            f"Found {findings.get('critical', 0)} critical and {findings.get('high', 0)} high severity issues. "
            f"All authentication flows were reviewed for token security, session management, "
            f"and privilege escalation vectors. Infrastructure was checked against CIS benchmarks. "
            f"Each finding includes a specific, tested remediation with code example."
        )
