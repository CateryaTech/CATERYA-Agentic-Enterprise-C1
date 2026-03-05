"""
Prometheus Metrics Instrumentation
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech
"""
from __future__ import annotations
from typing import Optional
from prometheus_client import Counter, Histogram, Gauge, Summary, REGISTRY, generate_latest
from prometheus_client import CollectorRegistry

# ── Metrics definitions ───────────────────────────────────────────────────────

# COS
cos_score = Gauge(
    "caterya_cos_score",
    "Composite Overall Score per tenant",
    ["tenant_id", "agent_name"],
)

cos_passed = Gauge(
    "caterya_cos_passed",
    "Whether latest COS evaluation passed threshold",
    ["tenant_id"],
)

# Pillar scores
pillar_score = Gauge(
    "caterya_pillar_score",
    "Individual pillar score",
    ["tenant_id", "pillar"],
)

# Stability index
stability_index = Gauge(
    "caterya_stability_index",
    "Robustness Stability Index",
    ["tenant_id", "agent_name"],
)

# Guardrail
guardrail_violations = Counter(
    "caterya_guardrail_violations_total",
    "Total guardrail violations",
    ["tenant_id", "agent_name", "violation_type"],
)

# Agent execution
agent_duration_ms = Histogram(
    "caterya_agent_duration_ms",
    "Agent execution duration in milliseconds",
    ["agent_name", "tenant_id"],
    buckets=[50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000],
)

# Pipeline
pipeline_stage_count = Counter(
    "caterya_pipeline_stage_count",
    "Pipeline stage execution count",
    ["stage", "tenant_id", "status"],
)

pipeline_complete = Counter(
    "caterya_pipeline_complete_total",
    "Completed pipeline runs",
    ["tenant_id", "passed"],
)

# LLM
llm_errors = Counter(
    "caterya_llm_errors_total",
    "LLM provider errors",
    ["provider", "model"],
)

llm_latency_ms = Histogram(
    "caterya_llm_latency_ms",
    "LLM call latency in milliseconds",
    ["provider", "model"],
    buckets=[100, 500, 1000, 3000, 10000, 30000],
)

# ── Helper functions ──────────────────────────────────────────────────────────

def record_cos(tenant_id: str, agent_name: str, cos: float, passed: bool):
    cos_score.labels(tenant_id=tenant_id, agent_name=agent_name).set(cos)
    cos_passed.labels(tenant_id=tenant_id).set(1.0 if passed else 0.0)


def record_pillars(tenant_id: str, pillar_scores: dict):
    for pillar, score in pillar_scores.items():
        pillar_score.labels(tenant_id=tenant_id, pillar=pillar).set(score)


def record_stability(tenant_id: str, agent_name: str, score: float):
    stability_index.labels(tenant_id=tenant_id, agent_name=agent_name).set(score)


def record_violation(tenant_id: str, agent_name: str, violation_type: str):
    guardrail_violations.labels(
        tenant_id=tenant_id,
        agent_name=agent_name,
        violation_type=violation_type,
    ).inc()


def record_agent_duration(agent_name: str, tenant_id: str, duration_ms: float):
    agent_duration_ms.labels(agent_name=agent_name, tenant_id=tenant_id).observe(duration_ms)


def metrics_response():
    """Return Prometheus metrics as bytes (for /metrics endpoint)."""
    return generate_latest()
