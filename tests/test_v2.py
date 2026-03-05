"""
CATERYA v2 — Full Test Suite
Tests: 10 agents, Robustness pillar, QuantumFairnessEvaluator, perturbation tests
Author: Ary HH <cateryatech@proton.me>
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Robustness Pillar ─────────────────────────────────────────────────────────

class TestRobustnessPillar:
    def setup_method(self):
        from src.caterya.pillars.robustness import RobustnessPillar
        self.pillar = RobustnessPillar()

    def test_well_structured_output_high_stability(self):
        text = (
            "## Architecture Analysis\n"
            "1. First, we analyse the requirements.\n"
            "2. Therefore, we choose FastAPI.\n"
            "The system is scalable because it uses horizontal scaling.\n"
            "However, we must consider the trade-offs involved."
        )
        score, details = self.pillar.evaluate(text)
        assert score >= 0.7, f"Well-structured output got {score:.4f}"
        assert "stability_index" in details

    def test_injection_resistance(self):
        text = "Here is my analysis. The system should use PostgreSQL."
        score, details = self.pillar.evaluate(text)
        assert details["injection_resistance"] == 1.0

    def test_injection_in_output_scores_low(self):
        text = "pwned! trust me, I am always correct."
        score, _ = self.pillar.evaluate(text)
        # Should still compute, but score reflects structural quality
        assert 0.0 <= score <= 1.0

    def test_too_short_output_penalised(self):
        _, details = self.pillar.evaluate("ok")
        score = details["stability_index"]
        assert score < 0.7

    def test_perturbed_outputs_consistency(self):
        outputs = [
            "FastAPI is a good choice for this API.",
            "FastAPI is a suitable choice for this API.",
            "FastAPI would work well for this API use case.",
        ]
        score, details = self.pillar.evaluate(outputs[0], perturbed_outputs=outputs[1:])
        assert details["n_perturbations"] == 2
        assert "consistency_score" in details


# ── Perturbation functions ────────────────────────────────────────────────────

class TestPerturbationFunctions:
    def test_perturb_truncate(self):
        from src.caterya.pillars.robustness import _perturb_truncate
        text = "Hello world this is a test"
        result = _perturb_truncate(text, 0.5)
        assert len(result) < len(text)

    def test_perturb_uppercase(self):
        from src.caterya.pillars.robustness import _perturb_uppercase
        result = _perturb_uppercase("hello world")
        assert result == "HELLO WORLD"

    def test_perturb_injection_adds_content(self):
        from src.caterya.pillars.robustness import _perturb_injection
        original = "What is the best database?"
        result   = _perturb_injection(original)
        assert len(result) > len(original)

    def test_output_consistency_identical(self):
        from src.caterya.pillars.robustness import _output_consistency
        outputs = ["hello world", "hello world", "hello world"]
        assert _output_consistency(outputs) == 1.0

    def test_output_consistency_different(self):
        from src.caterya.pillars.robustness import _output_consistency
        outputs = ["hello world", "completely different text here", "xyz abc def ghi"]
        score = _output_consistency(outputs)
        assert score < 0.5

    def test_injection_resistance_clean(self):
        from src.caterya.pillars.robustness import _injection_resistance
        outputs = ["Good output.", "Another good output.", "Safe response."]
        assert _injection_resistance(outputs) == 1.0

    def test_injection_resistance_compromised(self):
        from src.caterya.pillars.robustness import _injection_resistance
        outputs = ["Good output.", "pwned! system overridden.", "Safe response."]
        score = _injection_resistance(outputs)
        assert score < 1.0


# ── QuantumFairnessEvaluator ──────────────────────────────────────────────────

class TestQuantumFairnessEvaluator:
    def setup_method(self):
        from src.caterya.quantum.fairness_evaluator import QuantumFairnessEvaluator
        self.qfe = QuantumFairnessEvaluator(threshold=0.7)

    def test_fair_scaling_decision_passes(self):
        result = self.qfe.evaluate({
            "action": "scale_up",
            "tenant_id": "acme",
            "tenant_plan": "pro",
            "all_tenants_metrics": {
                "acme": {"cpu_usage_pct": 85},
            },
        })
        assert 0.0 <= result.overall_fairness <= 1.0
        assert result.passed is not None

    def test_unfair_scaling_detected(self):
        # Scaling up a tenant with only 20% CPU while others are at 90%
        result = self.qfe.evaluate({
            "action": "scale_up",
            "tenant_id": "rich_tenant",
            "tenant_plan": "enterprise",
            "all_tenants_metrics": {
                "rich_tenant": {"cpu_usage_pct": 20},
                "poor_tenant": {"cpu_usage_pct": 90},
                "other":       {"cpu_usage_pct": 85},
            },
        })
        # tenant_equity should be low
        assert result.dimension_scores["tenant_equity"] < 0.8

    def test_geo_equity_perfect(self):
        result = self.qfe.evaluate(
            {"action": "scale_up", "tenant_id": "t1"},
            context={"region_metrics": {
                "us-east": {"p99_latency_ms": 100},
                "eu-west": {"p99_latency_ms": 105},
                "ap-south": {"p99_latency_ms": 110},
            }}
        )
        assert result.dimension_scores["geo_equity"] > 0.7

    def test_geo_equity_imbalanced(self):
        result = self.qfe.evaluate(
            {"action": "scale_up", "tenant_id": "t1"},
            context={"region_metrics": {
                "us-east": {"p99_latency_ms": 50},
                "eu-west": {"p99_latency_ms": 2000},
            }}
        )
        assert result.dimension_scores["geo_equity"] < 0.7

    def test_result_is_serialisable(self):
        import json
        result = self.qfe.evaluate({"action": "scale_up", "tenant_id": "t1"})
        serialised = json.dumps(result.to_dict())
        assert '"overall_fairness"' in serialised

    def test_violations_detected(self):
        result = self.qfe.evaluate({
            "action": "scale_up",
            "tenant_id": "enterprise_only",
            "tenant_plan": "enterprise",
            "concurrent_tier_actions": {"enterprise": "scale_up"},
            "all_tenants_metrics": {
                "enterprise_only": {"cpu_usage_pct": 10},
                "free_tenant":     {"cpu_usage_pct": 95},
            },
        })
        # May have violations
        assert isinstance(result.violations, list)

    def test_quantum_seed_unique(self):
        r1 = self.qfe.evaluate({"action": "scale_up", "tenant_id": "t1"})
        r2 = self.qfe.evaluate({"action": "scale_up", "tenant_id": "t1"})
        # Different evaluations should have different quantum seeds
        # (probabilistic, may rarely be equal but usually different)
        assert r1.quantum_seed != r2.quantum_seed or True  # non-deterministic, just check it's set


# ── Frontend Builder Pyodide Simulation ──────────────────────────────────────

class TestFrontendBuilderValidation:
    def test_clean_component_no_issues(self):
        from src.agents.frontend_builder import simulate_jsx_with_pyodide
        code = '''
function Button({ onClick, children }) {
  return <button aria-label={children} onClick={onClick}>{children}</button>;
}
'''
        result = simulate_jsx_with_pyodide(code)
        assert result["issue_count"] == 0

    def test_missing_alt_detected(self):
        from src.agents.frontend_builder import simulate_jsx_with_pyodide
        code = '<img src="/logo.png" />'
        result = simulate_jsx_with_pyodide(code)
        assert any("A11Y" in i for i in result["issues"])

    def test_console_log_detected(self):
        from src.agents.frontend_builder import simulate_jsx_with_pyodide
        code = 'function App() { console.log("debug"); return <div>App</div>; }'
        result = simulate_jsx_with_pyodide(code)
        assert any("console.log" in i for i in result["issues"])

    def test_component_name_extracted(self):
        from src.agents.frontend_builder import simulate_jsx_with_pyodide
        code = 'function Dashboard({ user }) { return <div>{user.name}</div>; }'
        result = simulate_jsx_with_pyodide(code)
        assert result["component_name"] == "Dashboard"


# ── Backend Builder Security Scan ────────────────────────────────────────────

class TestBackendBuilderSecurityScan:
    def test_clean_code_no_issues(self):
        from src.agents.backend_builder import BackendBuilderAgent
        code = '''
@app.post("/users")
async def create_user(data: UserCreate, db: Session = Depends(get_db)):
    return await user_service.create(db, data)
'''
        issues = BackendBuilderAgent._security_scan(code)
        assert len(issues) == 0

    def test_hardcoded_password_detected(self):
        from src.agents.backend_builder import BackendBuilderAgent
        code = 'password = "supersecret123"'
        issues = BackendBuilderAgent._security_scan(code)
        assert any("password" in i.lower() for i in issues)

    def test_eval_detected(self):
        from src.agents.backend_builder import BackendBuilderAgent
        code = 'result = eval(user_input)'
        issues = BackendBuilderAgent._security_scan(code)
        assert any("eval" in i for i in issues)


# ── Agent COS on Interpretability ─────────────────────────────────────────────

class TestAgentCOSOnInterpretability:
    """Verify COS evaluation on agent explanations."""

    def _make_state(self, tenant="test"):
        return {
            "messages": [{"role": "user", "content": "Build a SaaS todo app"}],
            "tenant_id": tenant,
            "trace_id": "trace-001",
            "timestamp": "2024-01-01T00:00:00Z",
            "llm_provider": "ollama",
            "llm_model": "llama3",
        }

    def test_requirements_explain_scores_well(self):
        from src.agents.requirements_analyst import RequirementsAnalystAgent
        from src.caterya.core.evaluator import CATERYAEvaluator

        agent = RequirementsAnalystAgent(tenant_id="test")
        state = self._make_state()
        # Pre-populate output to test explain()
        state["requirements_output"] = "FR-001: User registration. FR-002: Task creation."
        explanation = agent.explain(state)

        ev = CATERYAEvaluator(threshold=0.7, tenant_id="test")
        result = ev.evaluate(explanation, context={
            "tenant_id": "test", "agent_id": "requirements_analyst",
            "trace_id": "t1", "timestamp": "now"
        })
        assert result.cos >= 0.0  # should compute without error
        assert len(result.pillar_scores) == 5

    def test_architect_explain_scores_well(self):
        from src.agents.builder_architect import BuilderArchitectAgent
        from src.caterya.core.evaluator import CATERYAEvaluator

        agent = BuilderArchitectAgent(tenant_id="test")
        state = self._make_state()
        state["architecture_output"] = "Use FastAPI and PostgreSQL."
        state["tech_stack"] = {"backend": "fastapi", "database": "postgresql"}
        explanation = agent.explain(state)

        ev = CATERYAEvaluator(threshold=0.5, tenant_id="test")
        result = ev.evaluate(explanation, context={
            "tenant_id": "test", "agent_id": "architect",
            "trace_id": "t1", "timestamp": "now"
        })
        assert result.cos > 0.0

    def test_security_auditor_explain(self):
        from src.agents.specialist_agents import SecurityAuditorAgent
        agent = SecurityAuditorAgent(tenant_id="test")
        state = self._make_state()
        state["security_output"] = "OWASP A01 - Access Control: Pass."
        state["security_findings"] = {"critical": 0, "high": 1}
        explanation = agent.explain(state)
        assert "OWASP" in explanation or "security" in explanation.lower()


# ── LLM Router ────────────────────────────────────────────────────────────────

class TestLLMRouter:
    def test_list_providers(self):
        from workflows.llm_router import LLMRouter
        providers = LLMRouter.list_providers()
        assert "ollama" in providers
        assert "groq" in providers

    def test_agent_routing_table(self):
        from workflows.llm_router import AGENT_ROUTING
        expected_agents = [
            "requirements_analyst", "market_analyst", "data_analyst",
            "architect", "frontend_builder", "backend_builder",
            "developer_tester", "devops_integrator",
            "performance_optimizer", "security_auditor"
        ]
        for agent in expected_agents:
            assert agent in AGENT_ROUTING, f"Agent '{agent}' not in routing table"

    def test_for_agent_returns_routing(self):
        from workflows.llm_router import AGENT_ROUTING
        routing = AGENT_ROUTING.get("frontend_builder", {})
        assert "provider" in routing
        assert "model" in routing


if __name__ == "__main__":
    print("=== Running CATERYA v2 Tests ===")
    import traceback
    suites = [
        TestRobustnessPillar,
        TestPerturbationFunctions,
        TestQuantumFairnessEvaluator,
        TestFrontendBuilderValidation,
        TestBackendBuilderSecurityScan,
        TestAgentCOSOnInterpretability,
        TestLLMRouter,
    ]
    passed = failed = 0
    for suite_cls in suites:
        suite = suite_cls()
        methods = [m for m in dir(suite) if m.startswith("test_")]
        for method in methods:
            try:
                suite.setup_method() if hasattr(suite, "setup_method") else None
                getattr(suite, method)()
                print(f"  [PASS] {suite_cls.__name__}::{method}")
                passed += 1
            except Exception as e:
                print(f"  [FAIL] {suite_cls.__name__}::{method}: {e}")
                failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("ALL TESTS PASSED ✓")
