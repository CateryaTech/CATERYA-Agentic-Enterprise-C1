# Building a SaaS with CATERYA Enterprise
**Author:** Ary HH — CATERYA Tech

This guide walks through building a complete SaaS product using the 10-agent pipeline.

---

## Example: Build a Project Management SaaS (like Linear)

### 1. Start the pipeline

```python
from workflows.saas_builder_workflow import SaaSBuilderWorkflow

wf = SaaSBuilderWorkflow(
    tenant_id="acme",
    cos_threshold=0.7,
    llm_provider="ollama",
    llm_model="llama3",
)

result = wf.run(
    query="Build a project management SaaS with issues, sprints, roadmaps, and team collaboration. Similar to Linear but with better AI integration.",
    target_market="startup to mid-market tech teams",
    scale="100 to 10,000 users",
    backend_framework="fastapi",
)

print(result["requirements_output"])   # FR-001, FR-002...
print(result["architecture_output"])  # C4 diagrams, tech stack
print(result["frontend_output"])      # Next.js 14 components
print(result["backend_output"])       # FastAPI endpoints
print(result["security_output"])      # OWASP audit
print(result["cos_result"]["cos"])    # e.g. 0.87
```

---

### 2. Stream the pipeline for real-time UI

```python
for stage, state in wf.run_streaming("Build a billing SaaS"):
    print(f"Stage: {stage}")
    output_key = f"{stage}_output"
    if output_key in state:
        print(f"Output preview: {str(state[output_key])[:200]}")
    cos = state.get("agent_cos_scores", {}).get(stage, {})
    if cos:
        print(f"COS: {cos.get('cos', 0):.4f}")
```

---

### 3. Run a single agent

```python
from src.agents.requirements_analyst import RequirementsAnalystAgent

agent = RequirementsAnalystAgent(
    tenant_id="acme",
    llm_provider="groq",
    llm_model="llama3-8b-8192",
)

state = {
    "messages": [{"role": "user", "content": "Build a SaaS invoice generator"}],
    "tenant_id": "acme",
    "trace_id": "my-trace",
    "timestamp": "2024-01-01T00:00:00Z",
}

result_state = agent.safe_execute(state)
print(result_state["requirements_output"])

# Get interpretability explanation
explanation = agent.explain(result_state)
print(explanation)

# Get COS on the explanation
cos = result_state["agent_cos_scores"]["requirements_analyst"]
print(f"COS: {cos['cos']:.4f} | Passed: {cos['passed']}")
```

---

### 4. Pyodide JSX validation (Frontend Builder)

```python
from src.agents.frontend_builder import simulate_jsx_with_pyodide

component = '''
function Dashboard({ userId }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetch(`/api/dashboard/${userId}`).then(r => r.json()).then(setData);
  }, [userId]);
  
  return (
    <div className="p-4">
      <img src="/logo.png" />  {/* Missing alt! */}
      <h1>Dashboard</h1>
      {data && <DataTable data={data} />}
    </div>
  );
}
'''

result = simulate_jsx_with_pyodide(component)
print(result["issues"])
# ["A11Y: <img> missing alt attribute"]
```

---

### 5. QuantumFairnessEvaluator — scaling decisions

```python
from src.caterya.quantum.fairness_evaluator import QuantumFairnessEvaluator

qfe = QuantumFairnessEvaluator(threshold=0.7)

result = qfe.evaluate(
    scaling_decision={
        "action": "scale_up",
        "tenant_id": "acme",
        "tenant_plan": "pro",
        "resources_before": {"cpu": "2", "memory": "4Gi"},
        "resources_after":  {"cpu": "4", "memory": "8Gi"},
        "trigger": "cpu_threshold_80pct",
        "all_tenants_metrics": {
            "acme":   {"cpu_usage_pct": 85},
            "globex": {"cpu_usage_pct": 40},
        },
    }
)

print(f"Fairness Score: {result.overall_fairness:.4f}")
print(f"Passed: {result.passed}")
for v in result.violations:
    print(f"  Violation: {v.dimension} ({v.severity}): {v.description}")
```

---

### 6. Perturbation Tests — Stability Index

```python
from src.caterya.pillars.robustness import RobustnessPillar, PerturbationTestRunner

# Offline (single output)
pillar = RobustnessPillar()
score, details = pillar.evaluate(
    "## Architecture\n1. Use FastAPI for backend\n2. PostgreSQL for storage\n"
    "Therefore, the system will be scalable and maintainable."
)
print(f"Stability Index: {score:.4f}")  # >= 0.7 required

# Live (with agent)
from src.agents.requirements_analyst import RequirementsAnalystAgent

def agent_fn(state):
    agent = RequirementsAnalystAgent(tenant_id="test", llm_provider="ollama")
    return agent.safe_execute(state)

runner = PerturbationTestRunner(agent_fn=agent_fn)
result = runner.run("Build a todo app", n_perturbations=5)
print(f"Stability: {result['stability_index']:.4f} | Passed: {result['passed']}")
```

---

### 7. REST API usage

```bash
# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "acme", "email": "user@acme.com", "password": "secret"}'

# Run SaaS pipeline
curl -X POST http://localhost:8000/workflow/saas \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Build a SaaS analytics dashboard",
    "llm_provider": "ollama",
    "llm_model": "llama3",
    "cos_threshold": 0.7
  }'

# Evaluate output
curl -X POST http://localhost:8000/evaluate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"output": "Based on research, here is my analysis..."}'
```

---

### 8. Stripe billing

```python
from billing.billing import StripeClient, get_plan_limits

client = StripeClient()

# Create checkout for Pro plan
checkout = client.create_checkout_session(
    tenant_id="acme",
    plan="pro",
    success_url="https://app.caterya.tech/billing/success",
    cancel_url="https://app.caterya.tech/billing",
    customer_email="admin@acme.com",
)
print(checkout["url"])  # Redirect user here

# Check plan limits
limits = get_plan_limits("pro")
print(limits["max_agents"])  # 10
```

---

### 9. Monitoring

Access dashboards:
- **Grafana:** http://localhost:3000 (admin / see .env)
- **Prometheus:** http://localhost:9090
- **Alertmanager:** http://localhost:9093

Key metrics:
- `caterya_cos_score{tenant_id="acme"}` — real-time COS per tenant
- `caterya_stability_index` — robustness
- `caterya_guardrail_violations_total` — ethical violations
- `caterya_pipeline_stage_count` — pipeline throughput
