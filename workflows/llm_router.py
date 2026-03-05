"""
LLM Router — Model-agnostic provider routing
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech
"""
from __future__ import annotations
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Default models per provider
_DEFAULTS: Dict[str, str] = {
    "ollama":      "llama3",
    "groq":        "llama3-8b-8192",
    "openrouter":  "openai/gpt-4o-mini",
    "together":    "meta-llama/Llama-3-8b-chat-hf",
    "fireworks":   "accounts/fireworks/models/llama-v3-8b-instruct",
}

# Agent-specific model routing overrides
AGENT_ROUTING: Dict[str, Dict[str, str]] = {
    "requirements_analyst":  {"provider": "ollama", "model": "llama3"},
    "market_analyst":        {"provider": "ollama", "model": "llama3"},
    "data_analyst":          {"provider": "ollama", "model": "llama3"},
    "architect":             {"provider": "ollama", "model": "llama3"},
    "frontend_builder":      {"provider": "ollama", "model": "codellama"},
    "backend_builder":       {"provider": "ollama", "model": "codellama"},
    "developer_tester":      {"provider": "ollama", "model": "codellama"},
    "devops_integrator":     {"provider": "ollama", "model": "llama3"},
    "performance_optimizer": {"provider": "ollama", "model": "codellama"},
    "security_auditor":      {"provider": "ollama", "model": "llama3"},
    # Legacy
    "research_agent":        {"provider": "ollama", "model": "llama3"},
    "analysis_agent":        {"provider": "ollama", "model": "llama3"},
    "writer_agent":          {"provider": "ollama", "model": "llama3"},
}


class LLMRouter:
    """
    Central LLM factory.

    Usage::

        llm = LLMRouter.get("groq", "llama3-8b-8192")
        response = llm.invoke("Hello world")

        # Agent-aware routing
        llm = LLMRouter.for_agent("frontend_builder")
    """

    @staticmethod
    def get(provider: str = "ollama", model: Optional[str] = None) -> Any:
        provider = provider.lower().strip()
        model = model or _DEFAULTS.get(provider, "llama3")

        if provider == "ollama":
            from langchain_community.llms import Ollama
            return Ollama(
                model=model,
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            )
        elif provider == "groq":
            from langchain_groq import ChatGroq
            return ChatGroq(model_name=model, api_key=os.getenv("GROQ_API_KEY"))
        elif provider == "openrouter":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model,
                openai_api_key=os.getenv("OPENROUTER_API_KEY"),
                openai_api_base="https://openrouter.ai/api/v1",
                default_headers={"HTTP-Referer": "https://caterya.tech"},
            )
        elif provider == "together":
            from langchain_together import ChatTogether
            return ChatTogether(model=model, api_key=os.getenv("TOGETHER_API_KEY"))
        elif provider == "fireworks":
            from langchain_fireworks import ChatFireworks
            return ChatFireworks(model=model, api_key=os.getenv("FIREWORKS_API_KEY"))
        else:
            logger.warning("Unknown provider '%s', falling back to Ollama", provider)
            from langchain_community.llms import Ollama
            return Ollama(model="llama3", base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))

    @classmethod
    def for_agent(cls, agent_name: str) -> Any:
        routing = AGENT_ROUTING.get(agent_name, {"provider": "ollama", "model": "llama3"})
        return cls.get(routing["provider"], routing["model"])

    @staticmethod
    def list_providers() -> list:
        return list(_DEFAULTS.keys())
