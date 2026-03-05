"""
AWS Lambda — Serverless Agent Execution Fallback
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Deployed as Lambda function for burst/serverless agent execution.
Triggered by SQS queue when Kubernetes HPA max replicas are reached.

Deploy:
  zip lambda.zip lambda_handler.py
  aws lambda create-function --function-name caterya-agent-executor ...
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from typing import Any, Dict

# Lambda has /opt/python in PYTHONPATH if layers are used
sys.path.insert(0, "/opt/python")
sys.path.insert(0, os.path.dirname(__file__))

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda entry point.

    Event structure (from SQS or direct invoke):
    {
        "task_type": "evaluate" | "single_agent" | "saas_pipeline",
        "tenant_id": "acme",
        "payload": {
            "query": "...",
            "agent": "requirements_analyst",
            "llm_provider": "groq",
            "llm_model": "llama3-8b-8192"
        }
    }
    """
    logger.info("Lambda invoked | task=%s | request_id=%s",
                event.get("task_type"), context.aws_request_id)

    # ── Handle SQS batch ──
    if "Records" in event:
        results = []
        for record in event["Records"]:
            body = json.loads(record["body"])
            result = _process_task(body)
            results.append(result)
        return {"statusCode": 200, "body": json.dumps({"results": results})}

    # ── Direct invoke ──
    result = _process_task(event)
    return {"statusCode": 200, "body": json.dumps(result, default=str)}


def _process_task(task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = task.get("task_type", "evaluate")
    payload   = task.get("payload", {})
    tenant_id = task.get("tenant_id", "lambda")

    try:
        if task_type == "evaluate":
            return _run_evaluator(tenant_id, payload)
        elif task_type == "single_agent":
            return _run_single_agent(tenant_id, payload)
        elif task_type == "saas_pipeline":
            return _run_pipeline(tenant_id, payload)
        else:
            return {"error": f"Unknown task_type: {task_type}"}
    except Exception as exc:
        logger.error("Task failed: %s\n%s", exc, traceback.format_exc())
        return {"error": str(exc), "task_type": task_type}


def _run_evaluator(tenant_id: str, payload: Dict) -> Dict:
    from src.caterya.core.evaluator import CATERYAEvaluator
    ev     = CATERYAEvaluator(threshold=0.7, tenant_id=tenant_id)
    result = ev.evaluate(
        output=payload.get("output", ""),
        context={"tenant_id": tenant_id, **payload.get("context", {})},
    )
    return result.to_dict()


def _run_single_agent(tenant_id: str, payload: Dict) -> Dict:
    agent_name   = payload.get("agent", "requirements_analyst")
    query        = payload.get("query", "")
    llm_provider = payload.get("llm_provider", "groq")  # prefer groq on Lambda (no Ollama)
    llm_model    = payload.get("llm_model", "llama3-8b-8192")

    agent_map = {
        "requirements_analyst":  ("src.agents.requirements_analyst", "RequirementsAnalystAgent"),
        "market_analyst":        ("src.agents.market_analyst",        "MarketAnalystAgent"),
        "data_analyst":          ("src.agents.data_analyst",          "DataAnalystAgent"),
        "architect":             ("src.agents.builder_architect",      "BuilderArchitectAgent"),
        "frontend_builder":      ("src.agents.frontend_builder",       "FrontendBuilderAgent"),
        "backend_builder":       ("src.agents.backend_builder",        "BackendBuilderAgent"),
        "developer_tester":      ("src.agents.specialist_agents",      "DeveloperTesterAgent"),
        "devops_integrator":     ("src.agents.specialist_agents",      "DevOpsIntegratorAgent"),
        "performance_optimizer": ("src.agents.specialist_agents",      "PerformanceOptimizerAgent"),
        "security_auditor":      ("src.agents.specialist_agents",      "SecurityAuditorAgent"),
    }

    if agent_name not in agent_map:
        return {"error": f"Unknown agent: {agent_name}"}

    module_path, class_name = agent_map[agent_name]
    module = __import__(module_path, fromlist=[class_name])
    AgentClass = getattr(module, class_name)

    agent = AgentClass(tenant_id=tenant_id, llm_provider=llm_provider, llm_model=llm_model)
    state = {"messages": [{"role": "user", "content": query}], "tenant_id": tenant_id}
    result_state = agent.safe_execute(state)

    output_key = f"{agent.AGENT_NAME}_output"
    return {
        "agent":   agent_name,
        "output":  result_state.get(output_key, ""),
        "cos":     result_state.get("agent_cos_scores", {}).get(agent_name, {}),
    }


def _run_pipeline(tenant_id: str, payload: Dict) -> Dict:
    from workflows.saas_builder_workflow import SaaSBuilderWorkflow
    wf = SaaSBuilderWorkflow(
        tenant_id=tenant_id,
        llm_provider=payload.get("llm_provider", "groq"),
        llm_model=payload.get("llm_model", "llama3-8b-8192"),
    )
    result = wf.run(query=payload.get("query", ""), user_id=payload.get("user_id"))
    return {
        "session_id":       result.get("session_id"),
        "pipeline_complete": result.get("pipeline_complete"),
        "cos_result":       result.get("cos_result"),
        "stability_index":  result.get("stability_index"),
    }
