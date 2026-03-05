"""
Hybrid LLM Mode — Local (Ollama) + Cloud (Groq) + Model Distillation
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Strategy:
  1. Try local Ollama first (privacy, zero-cost)
  2. If latency > threshold OR local unavailable → fallback to Groq
  3. Knowledge distillation: run teacher (large model) once,
     cache responses to fine-tune smaller student model prompts
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Distillation registry: maps task → best small model
DISTILLED_MODELS: Dict[str, Dict[str, str]] = {
    "requirements_analyst":  {"local": "phi3:mini",     "cloud": "llama3-8b-8192"},
    "market_analyst":        {"local": "llama3:8b",     "cloud": "llama3-8b-8192"},
    "data_analyst":          {"local": "phi3:mini",     "cloud": "mixtral-8x7b-32768"},
    "architect":             {"local": "llama3:8b",     "cloud": "llama3-70b-8192"},
    "frontend_builder":      {"local": "codellama:7b",  "cloud": "llama3-8b-8192"},
    "backend_builder":       {"local": "codellama:7b",  "cloud": "llama3-8b-8192"},
    "developer_tester":      {"local": "codellama:7b",  "cloud": "llama3-8b-8192"},
    "devops_integrator":     {"local": "phi3:mini",     "cloud": "llama3-8b-8192"},
    "performance_optimizer": {"local": "codellama:7b",  "cloud": "mixtral-8x7b-32768"},
    "security_auditor":      {"local": "llama3:8b",     "cloud": "llama3-70b-8192"},
}

# Fallback thresholds
LOCAL_TIMEOUT_SECS   = float(os.getenv("OLLAMA_TIMEOUT", "30"))
LATENCY_FALLBACK_MS  = float(os.getenv("HYBRID_LATENCY_THRESHOLD_MS", "5000"))


class HybridLLM:
    """
    Transparent local/cloud LLM with automatic fallback and distillation.

    Usage::

        llm = HybridLLM(agent_name="frontend_builder", tenant_id="acme")
        response = llm.invoke("Generate a React component...")
        print(response, llm.last_provider, llm.last_latency_ms)
    """

    def __init__(
        self,
        agent_name: str = "default",
        tenant_id: Optional[str] = None,
        force_cloud: bool = False,
        force_local: bool = False,
    ):
        self.agent_name    = agent_name
        self.tenant_id     = tenant_id
        self.force_cloud   = force_cloud
        self.force_local   = force_local
        self.last_provider = "unknown"
        self.last_latency_ms = 0.0
        self._models = DISTILLED_MODELS.get(agent_name, {"local": "llama3", "cloud": "llama3-8b-8192"})

    def invoke(self, prompt: str) -> str:
        if self.force_cloud:
            return self._cloud_invoke(prompt)
        if self.force_local:
            return self._local_invoke(prompt)

        # Try local first
        t0 = time.perf_counter()
        try:
            result = self._local_invoke(prompt)
            latency = (time.perf_counter() - t0) * 1000
            self.last_latency_ms = latency

            if latency > LATENCY_FALLBACK_MS:
                logger.info(
                    "Local latency %.0fms > threshold %.0fms, falling back to cloud | agent=%s",
                    latency, LATENCY_FALLBACK_MS, self.agent_name,
                )
                return self._cloud_invoke(prompt)

            self.last_provider = "ollama"
            return result

        except Exception as exc:
            logger.warning("Local LLM failed (%s), using cloud fallback", exc)
            return self._cloud_invoke(prompt)

    def _local_invoke(self, prompt: str) -> str:
        from langchain_community.llms import Ollama
        model = self._models["local"]
        llm = Ollama(
            model=model,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            timeout=LOCAL_TIMEOUT_SECS,
        )
        response = llm.invoke(prompt)
        self.last_provider = f"ollama/{model}"
        return response if isinstance(response, str) else response.content

    def _cloud_invoke(self, prompt: str) -> str:
        from langchain_groq import ChatGroq
        model = self._models["cloud"]
        llm = ChatGroq(
            model_name=model,
            api_key=os.getenv("GROQ_API_KEY"),
            timeout=60,
        )
        t0 = time.perf_counter()
        response = llm.invoke(prompt)
        self.last_latency_ms = (time.perf_counter() - t0) * 1000
        self.last_provider = f"groq/{model}"
        return response.content if hasattr(response, "content") else str(response)


class ModelDistiller:
    """
    Knowledge distillation: runs a large teacher model once and uses
    its output to craft optimised few-shot prompts for smaller student models.

    In production: fine-tunes smaller models via LoRA on cached teacher outputs.
    Here: builds dynamic few-shot prompt examples.
    """

    def __init__(self, cache=None):
        self.cache = cache
        self._examples: Dict[str, list] = {}

    def distill(
        self,
        agent_name: str,
        query: str,
        teacher_output: str,
        quality_score: float,
    ) -> None:
        """Store a high-quality teacher example for future few-shot prompting."""
        if quality_score < 0.75:
            return  # Only distil high-quality outputs

        if agent_name not in self._examples:
            self._examples[agent_name] = []

        self._examples[agent_name].append({
            "query":        query[:300],
            "output":       teacher_output[:1000],
            "quality_score": quality_score,
        })

        # Keep top-5 highest quality examples per agent
        self._examples[agent_name] = sorted(
            self._examples[agent_name],
            key=lambda x: x["quality_score"],
            reverse=True,
        )[:5]

    def build_few_shot_prompt(self, agent_name: str, new_query: str) -> str:
        """Inject distilled examples into the prompt for the small student model."""
        examples = self._examples.get(agent_name, [])
        if not examples:
            return new_query

        shots = "\n\n".join(
            f"EXAMPLE {i+1}:\nQ: {ex['query']}\nA: {ex['output'][:500]}"
            for i, ex in enumerate(examples[:3])
        )
        return f"""Here are examples of high-quality responses:

{shots}

Now answer this query following the same quality and structure:
{new_query}"""

    def stats(self) -> Dict[str, int]:
        return {agent: len(exs) for agent, exs in self._examples.items()}
