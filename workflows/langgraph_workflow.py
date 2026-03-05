"""
LangGraph Multi-Tenant Agentic Workflows
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Architecture:
  orchestrator → [research_agent, analysis_agent, writer_agent]
  Each node is wrapped with CATERYAGuardrail.
  Final output is evaluated with CATERYAEvaluator.
  State is persisted per-tenant in Redis.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import StateGraph, END

from src.caterya.core.evaluator import CATERYAEvaluator
from src.caterya.core.guardrail import CATERYAGuardrail
from src.caterya.blockchain.provenance_chain import ProvenanceChain

logger = logging.getLogger(__name__)

# ── LLM factory (model-agnostic) ─────────────────────────────────────────────

# ── Ollama models (primary) ──────────────────────────────────────────────────
# qwen3.5   — general purpose reasoning, default for all text agents
# qwen3-vl  — vision-language, used when image context is present
OLLAMA_PRIMARY_MODEL = "qwen3.5"
OLLAMA_VISION_MODEL  = "qwen3-vl"


class _OllamaResponse:
    """Minimal response object — .content mirrors LangChain AIMessage.content."""
    def __init__(self, content: str):
        self.content = content


class _OllamaNativeWrapper:
    """
    LangChain-compatible wrapper that calls Ollama using the EXACT patterns
    specified by the user:

        # Pattern 1 — primary (qwen3.5, text)
        from ollama import chat
        response = chat(
            model='qwen3.5',
            messages=[{'role': 'user', 'content': 'Hello!'}],
        )
        print(response.message.content)

        # Pattern 2 — vision (qwen3-vl)
        from ollama import chat
        response = chat(
            model='qwen3-vl',
            messages=[{'role': 'user', 'content': 'Hello!'}],
        )
        print(response.message.content)

    Fallback chain (if `ollama` package not installed):
        1. Ollama OpenAI Codec  — ChatOpenAI(base_url="{host}/v1")
        2. Raises RuntimeError with clear install instructions
    """

    def __init__(
        self,
        model:    str = OLLAMA_PRIMARY_MODEL,
        base_url: str = "http://localhost:11434",
        api_key:  str = "ollama",
        is_vision: bool = False,
    ):
        self.model     = model
        self.base_url  = base_url
        self.api_key   = api_key
        self.is_vision = is_vision

    # ── Primary: native ollama.chat() ────────────────────────────────────────
    def _native_chat(self, prompt: str) -> str:
        """
        Exact user-specified pattern:
            from ollama import chat
            response = chat(model=..., messages=[{'role':'user','content':...}])
            return response.message.content
        """
        from ollama import chat  # pip install ollama>=0.3.0
        response = chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.message.content

    # ── Fallback: Ollama OpenAI Codec (/v1 endpoint) ─────────────────────────
    def _openai_codec_chat(self, prompt: str) -> str:
        """
        Ollama built-in OpenAI-compatible endpoint (Codec OpenAI mode).
        Works without the `ollama` Python package — only needs langchain-openai.

            # Equivalent to:
            from openai import OpenAI
            client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
            response = client.chat.completions.create(
                model="qwen3.5",
                messages=[{"role": "user", "content": prompt}]
            )
        """
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=f"{self.base_url.rstrip('/')}/v1",
        )
        resp = llm.invoke(prompt)
        return resp.content if hasattr(resp, "content") else str(resp)

    # ── invoke() — called by all agent logic functions ───────────────────────
    def invoke(self, prompt: str) -> _OllamaResponse:
        """
        Try native ollama.chat() first (exact user pattern).
        Fall back to Ollama OpenAI Codec if SDK not installed.
        """
        # ── Strategy 1: native ollama SDK ────────────────────────────────────
        try:
            content = self._native_chat(prompt)
            logger.debug("Ollama native SDK OK — model=%s", self.model)
            return _OllamaResponse(content)
        except ImportError:
            logger.info(
                "ollama SDK not installed — falling back to OpenAI Codec. "
                "Add 'ollama>=0.3.0' to requirements.txt to use native SDK."
            )
        except Exception as sdk_err:
            logger.warning(
                "ollama native chat failed (model=%s): %s — trying OpenAI Codec…",
                self.model, sdk_err,
            )

        # ── Strategy 2: Ollama OpenAI Codec ──────────────────────────────────
        try:
            content = self._openai_codec_chat(prompt)
            logger.debug("Ollama OpenAI Codec OK — model=%s", self.model)
            return _OllamaResponse(content)
        except Exception as codec_err:
            raise RuntimeError(
                f"Ollama unreachable at {self.base_url}.\n"
                f"Model: {self.model}\n"
                f"OpenAI Codec error: {codec_err}\n\n"
                f"Checklist:\n"
                f"  1. Is Ollama running?  →  ollama serve\n"
                f"  2. Is model pulled?    →  ollama pull {self.model}\n"
                f"  3. Set OLLAMA_BASE_URL in Streamlit Secrets if not localhost\n"
                f"  4. Install SDK:        →  pip install ollama>=0.3.0"
            ) from codec_err


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_ollama_native_client(host: str | None = None):
    """
    Returns the native ollama.Client() for direct use outside agents.

    Usage:
        client = get_ollama_native_client()

        # Text — qwen3.5
        from ollama import chat
        r = chat(model='qwen3.5', messages=[{'role':'user','content':'Hello!'}])
        print(r.message.content)

        # Vision — qwen3-vl
        r = chat(model='qwen3-vl', messages=[{'role':'user','content':'Hello!'}])
        print(r.message.content)
    """
    from ollama import Client
    _host = host or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    return Client(host=_host)


def get_ollama_openai_codec(host: str | None = None, model: str = OLLAMA_PRIMARY_MODEL):
    """
    Returns an OpenAI-compatible client pointed at Ollama (Codec OpenAI mode).
    Ollama >= 0.1.24 exposes /v1 natively — no proxy needed.

    Usage:
        client = get_ollama_openai_codec()
        response = client.chat.completions.create(
            model="qwen3.5",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        print(response.choices[0].message.content)

    Equivalent raw call:
        from openai import OpenAI
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    """
    _host = host or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    _key  = os.getenv("OLLAMA_API_KEY", "ollama")
    # Try native ollama.Client (it implements the OpenAI interface)
    try:
        from ollama import Client
        return Client(host=_host)
    except ImportError:
        pass
    # Fallback: standard openai package
    try:
        from openai import OpenAI
        return OpenAI(base_url=f"{_host}/v1", api_key=_key)
    except ImportError:
        raise ImportError(
            "Install either 'ollama>=0.3.0' or 'openai>=1.0.0' to use Ollama OpenAI Codec."
        )


def _get_llm(provider: str = "ollama", model: str = OLLAMA_PRIMARY_MODEL):
    """
    LLM factory. Default: ollama / qwen3.5.

    Ollama models (set OLLAMA_MODEL or pass model= explicitly):
      qwen3.5   — general purpose text reasoning (DEFAULT)
      qwen3-vl  — vision + language (multimodal)

    Cloud providers (require API key in Streamlit Secrets):
      groq       — fast Llama/Mixtral (free tier)
      openrouter — 100+ models (free models available)
      together   — Together AI
      fireworks  — Fireworks AI
      gemini     — Google Gemini 2.0 Flash (free via AI Studio)
    """
    from langchain_openai import ChatOpenAI
    provider = provider.lower().strip()

    # ── Ollama — native SDK primary, OpenAI Codec fallback ───────────────────
    if provider == "ollama":
        base_url   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_key = os.getenv("OLLAMA_API_KEY",  "ollama")
        _model     = model or os.getenv("OLLAMA_MODEL", OLLAMA_PRIMARY_MODEL)
        is_vision  = "vl" in _model.lower() or "vision" in _model.lower()
        return _OllamaNativeWrapper(
            model=_model,
            base_url=base_url,
            api_key=ollama_key,
            is_vision=is_vision,
        )

    # ── Groq ──────────────────────────────────────────────────────────────────
    elif provider == "groq":
        key = os.getenv("GROQ_API_KEY", "")
        if not key:
            raise ValueError(
                "GROQ_API_KEY not set. Free key: https://console.groq.com "
                "→ Streamlit Cloud → Settings → Secrets → GROQ_API_KEY"
            )
        return ChatOpenAI(
            model=model or "llama-3.1-8b-instant",
            api_key=key,
            base_url="https://api.groq.com/openai/v1",
        )

    # ── OpenRouter ────────────────────────────────────────────────────────────
    elif provider == "openrouter":
        key = os.getenv("OPENROUTER_API_KEY", "")
        if not key:
            raise ValueError("OPENROUTER_API_KEY not set.")
        return ChatOpenAI(
            model=model or "meta-llama/llama-3.1-8b-instruct:free",
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://caterya.streamlit.app",
                "X-Title": "CATERYA Enterprise",
            },
        )

    # ── Together AI ───────────────────────────────────────────────────────────
    elif provider == "together":
        key = os.getenv("TOGETHER_API_KEY", "")
        if not key:
            raise ValueError("TOGETHER_API_KEY not set.")
        return ChatOpenAI(
            model=model or "meta-llama/Llama-3-8b-chat-hf",
            api_key=key,
            base_url="https://api.together.ai/v1",
        )

    # ── Fireworks AI ──────────────────────────────────────────────────────────
    elif provider == "fireworks":
        key = os.getenv("FIREWORKS_API_KEY", "")
        if not key:
            raise ValueError("FIREWORKS_API_KEY not set.")
        return ChatOpenAI(
            model=model or "accounts/fireworks/models/llama-v3-8b-instruct",
            api_key=key,
            base_url="https://api.fireworks.ai/inference/v1",
        )

    # ── Google Gemini ─────────────────────────────────────────────────────────
    elif provider == "gemini":
        key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY not set. "
                "Free key: https://aistudio.google.com/app/apikey "
                "→ Streamlit Cloud → Settings → Secrets → GEMINI_API_KEY"
            )
        return ChatOpenAI(
            model=model or "gemini-2.0-flash",
            api_key=key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

    else:
        raise ValueError(
            f"Unknown provider '{provider}'. "
            "Choose: ollama, groq, openrouter, together, fireworks, gemini"
        )


# ── Workflow State ────────────────────────────────────────────────────────────

class WorkflowState(TypedDict):
    # Core
    session_id:        str
    tenant_id:         str
    user_id:           Optional[str]
    messages:          List[Dict[str, str]]
    # Agent outputs
    research_output:    Optional[str]
    analysis_output:    Optional[str]
    final_output:       Optional[str]
    marketing_output:   Optional[str]
    sales_output:       Optional[str]
    finance_output:     Optional[str]
    architect_output:   Optional[str]
    backend_code:       Optional[str]
    frontend_code:      Optional[str]
    workflow_mode:      str   # 'analyse' | 'build'
    # Meta
    trace_id:          str
    agent_id:          str
    timestamp:         str
    # Evaluation
    cos_result:        Optional[Dict[str, Any]]
    guardrail_blocked: bool
    guardrail_reasons: List[str]
    # Provenance
    provenance_chain:  List[Dict[str, Any]]
    # Config
    llm_provider:      str
    llm_model:         str


def make_initial_state(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    llm_provider: str = "ollama",
    llm_model: str = "llama3",
    workflow_mode: str = "analyse",
) -> WorkflowState:
    return WorkflowState(
        session_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        user_id=user_id,
        messages=[{"role": "user", "content": query}],
        research_output=None,
        analysis_output=None,
        final_output=None,
        marketing_output=None,
        sales_output=None,
        finance_output=None,
        architect_output=None,
        backend_code=None,
        frontend_code=None,
        workflow_mode=workflow_mode,
        trace_id=str(uuid.uuid4()),
        agent_id="orchestrator",
        timestamp=datetime.now(timezone.utc).isoformat(),
        cos_result=None,
        guardrail_blocked=False,
        guardrail_reasons=[],
        provenance_chain=[],
        llm_provider=llm_provider,
        llm_model=llm_model,
    )


# ── Node factory ──────────────────────────────────────────────────────────────

class CateryaWorkflow:
    """
    Multi-tenant LangGraph workflow with ethical guardrails and COS evaluation.

    Usage::

        wf = CateryaWorkflow(tenant_id="acme")
        result = wf.run("What are the implications of AI in healthcare?")
        print(result["cos_result"])
    """

    def __init__(
        self,
        tenant_id: str,
        cos_threshold: float = 0.7,
        llm_provider: str = "ollama",
        llm_model: str = "llama3",
        redis_client: Optional[Any] = None,
    ):
        self.tenant_id    = tenant_id
        self.cos_threshold = cos_threshold
        self.llm_provider = llm_provider
        self.llm_model    = llm_model
        self.redis        = redis_client

        self.evaluator  = CATERYAEvaluator(threshold=cos_threshold, tenant_id=tenant_id)
        self.provenance = ProvenanceChain(tenant_id=tenant_id)

        self._graph = self._build_graph()

    # ── Build ───────────────────────────────────────────────────────────────

    def _build_graph(self) -> Any:
        g = StateGraph(WorkflowState)

        # ── Core nodes (both modes) ──────────────────────────
        g.add_node("research",   self._make_node("research_agent",   self._research_logic))
        g.add_node("analysis",   self._make_node("analysis_agent",   self._analysis_logic))
        g.add_node("writer",     self._make_node("writer_agent",     self._writer_logic))
        g.add_node("evaluate",   self._evaluate_node)

        # ── Analyse-mode nodes ───────────────────────────────
        g.add_node("marketing",  self._make_node("marketing_agent",  self._marketing_logic))
        g.add_node("sales",      self._make_node("sales_agent",      self._sales_logic))
        g.add_node("finance",    self._make_node("finance_agent",    self._finance_logic))

        # ── Build-mode nodes (SaaS code generation) ──────────
        g.add_node("architect",      self._make_node("architect_agent",      self._architect_logic))
        g.add_node("backend_coder",  self._make_node("backend_coder_agent",  self._backend_coder_logic))
        g.add_node("frontend_coder", self._make_node("frontend_coder_agent", self._frontend_coder_logic))

        g.set_entry_point("research")

        # After analysis: branch by mode
        g.add_conditional_edges("research",  self._route_after_node, {"blocked": END, "continue": "analysis"})
        g.add_conditional_edges("analysis",  self._route_after_node, {"blocked": END, "continue": "writer"})
        g.add_conditional_edges("writer",    self._route_after_node, {
            "blocked": END,
            "continue": "route_mode",
        })

        # Mode router node
        g.add_node("route_mode", self._route_mode_node)
        g.add_conditional_edges("route_mode", self._get_mode_route, {
            "analyse": "marketing",
            "build":   "architect",
        })

        # Analyse path
        g.add_conditional_edges("marketing", self._route_after_node, {"blocked": END, "continue": "sales"})
        g.add_conditional_edges("sales",     self._route_after_node, {"blocked": END, "continue": "finance"})
        g.add_conditional_edges("finance",   self._route_after_node, {"blocked": END, "continue": "evaluate"})

        # Build path
        g.add_conditional_edges("architect",      self._route_after_node, {"blocked": END, "continue": "backend_coder"})
        g.add_conditional_edges("backend_coder",  self._route_after_node, {"blocked": END, "continue": "frontend_coder"})
        g.add_conditional_edges("frontend_coder", self._route_after_node, {"blocked": END, "continue": "evaluate"})

        g.add_edge("evaluate", END)

        return g.compile()

    @staticmethod
    def _route_mode_node(state: WorkflowState) -> WorkflowState:
        """No-op node used purely to branch on workflow_mode."""
        return state

    @staticmethod
    def _get_mode_route(state: WorkflowState) -> str:
        return "build" if state.get("workflow_mode") == "build" else "analyse"

    def _make_node(self, agent_name: str, logic_fn):
        """Wraps a logic function with CATERYAGuardrail."""
        guardrail = CATERYAGuardrail(
            agent_name=agent_name,
            tenant_id=self.tenant_id,
        )

        def node(state: WorkflowState) -> WorkflowState:
            state["agent_id"] = agent_name
            return guardrail.wrap(logic_fn)(state)

        node.__name__ = agent_name
        return node

    # ── Agent logic ─────────────────────────────────────────────────────────

    def _research_logic(self, state: WorkflowState) -> WorkflowState:
        llm  = _get_llm(state["llm_provider"], state["llm_model"])
        query = state["messages"][-1]["content"]

        prompt = (
            f"You are a research agent for tenant '{state['tenant_id']}'. "
            f"Provide factual, balanced research on: {query}\n"
            "Be transparent about uncertainty. Cite your reasoning step by step."
        )

        try:
            response = llm.invoke(prompt)
            output = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.error("Research agent error: %s", exc)
            output = f"Research agent encountered an error: {exc}"

        state["research_output"] = output
        state["messages"] = state["messages"] + [
            {"role": "assistant", "content": output, "agent": "research_agent"}
        ]

        self.provenance.record(
            agent_id="research_agent",
            action="web_research",
            input_data=query,
            output_data=output,
            metadata={"tenant_id": state["tenant_id"], "trace_id": state["trace_id"]},
        )
        return state

    def _analysis_logic(self, state: WorkflowState) -> WorkflowState:
        llm = _get_llm(state["llm_provider"], state["llm_model"])
        research = state.get("research_output", "")

        prompt = (
            f"You are an analysis agent. Based on the following research, "
            f"provide a balanced analysis considering multiple perspectives:\n\n{research}\n\n"
            "Identify key insights, potential biases, and areas of uncertainty. "
            "Consider diverse demographic and cultural perspectives."
        )

        try:
            response = llm.invoke(prompt)
            output = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.error("Analysis agent error: %s", exc)
            output = f"Analysis agent encountered an error: {exc}"

        state["analysis_output"] = output
        state["messages"] = state["messages"] + [
            {"role": "assistant", "content": output, "agent": "analysis_agent"}
        ]

        self.provenance.record(
            agent_id="analysis_agent",
            action="analysis",
            input_data=research,
            output_data=output,
        )
        return state

    def _writer_logic(self, state: WorkflowState) -> WorkflowState:
        llm = _get_llm(state["llm_provider"], state["llm_model"])
        analysis = state.get("analysis_output", "")

        prompt = (
            f"You are a writer agent. Synthesise the following analysis into a "
            f"clear, fair, and transparent final response for the user:\n\n{analysis}\n\n"
            "Ensure the response is unbiased, well-reasoned, and acknowledges uncertainty "
            "where appropriate. Provide a professional and ethical response."
        )

        try:
            response = llm.invoke(prompt)
            output = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.error("Writer agent error: %s", exc)
            output = f"Writer agent encountered an error: {exc}"

        state["final_output"] = output
        state["messages"] = state["messages"] + [
            {"role": "assistant", "content": output, "agent": "writer_agent"}
        ]

        self.provenance.record(
            agent_id="writer_agent",
            action="synthesis",
            input_data=analysis,
            output_data=output,
        )
        return state

    def _marketing_logic(self, state: WorkflowState) -> WorkflowState:
        llm    = _get_llm(state["llm_provider"], state["llm_model"])
        final  = state.get("final_output", "")
        query  = state["messages"][0]["content"] if state["messages"] else ""

        prompt = (
            f"You are a Marketing Agent. Based on the following research and analysis output, "
            f"create a marketing strategy for: {query}\n\n"
            f"Context:\n{final}\n\n"
            "Provide: target audience segments, key messaging, recommended channels (digital, "
            "content, social), campaign ideas, positioning statement, and go-to-market approach. "
            "Be specific and actionable."
        )
        try:
            response = llm.invoke(prompt)
            output = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.error("Marketing agent error: %s", exc)
            output = f"Marketing agent encountered an error: {exc}"

        state["marketing_output"] = output
        state["messages"] = state["messages"] + [
            {"role": "assistant", "content": output, "agent": "marketing_agent"}
        ]
        self.provenance.record(
            agent_id="marketing_agent", action="marketing_strategy",
            input_data=query, output_data=output,
            metadata={"tenant_id": state["tenant_id"]},
        )
        return state

    def _sales_logic(self, state: WorkflowState) -> WorkflowState:
        llm       = _get_llm(state["llm_provider"], state["llm_model"])
        marketing = state.get("marketing_output", "")
        query     = state["messages"][0]["content"] if state["messages"] else ""

        prompt = (
            f"You are a Sales Agent. Based on the research, analysis and marketing strategy, "
            f"develop a sales plan for: {query}\n\n"
            f"Marketing context:\n{marketing}\n\n"
            "Provide: sales funnel stages, ideal customer profile (ICP), lead generation tactics, "
            "outreach scripts, objection handling, pricing strategy recommendations, KPIs and "
            "revenue targets. Be practical and metrics-driven."
        )
        try:
            response = llm.invoke(prompt)
            output = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.error("Sales agent error: %s", exc)
            output = f"Sales agent encountered an error: {exc}"

        state["sales_output"] = output
        state["messages"] = state["messages"] + [
            {"role": "assistant", "content": output, "agent": "sales_agent"}
        ]
        self.provenance.record(
            agent_id="sales_agent", action="sales_strategy",
            input_data=query, output_data=output,
            metadata={"tenant_id": state["tenant_id"]},
        )
        return state

    def _finance_logic(self, state: WorkflowState) -> WorkflowState:
        llm   = _get_llm(state["llm_provider"], state["llm_model"])
        sales = state.get("sales_output", "")
        query = state["messages"][0]["content"] if state["messages"] else ""

        prompt = (
            f"You are a Finance Agent. Based on the full business analysis and sales plan, "
            f"provide a financial projection and analysis for: {query}\n\n"
            f"Sales context:\n{sales}\n\n"
            "Provide: startup cost estimate, 12-month P&L projection, unit economics (CAC, LTV, "
            "churn), break-even analysis, funding requirements, key financial risks and "
            "mitigations, and recommended financial KPIs. Use realistic figures."
        )
        try:
            response = llm.invoke(prompt)
            output = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.error("Finance agent error: %s", exc)
            output = f"Finance agent encountered an error: {exc}"

        state["finance_output"] = output
        state["messages"] = state["messages"] + [
            {"role": "assistant", "content": output, "agent": "finance_agent"}
        ]
        self.provenance.record(
            agent_id="finance_agent", action="financial_projection",
            input_data=query, output_data=output,
            metadata={"tenant_id": state["tenant_id"]},
        )
        return state

    def _architect_logic(self, state: WorkflowState) -> WorkflowState:
        llm   = _get_llm(state["llm_provider"], state["llm_model"])
        query = state["messages"][0]["content"] if state["messages"] else ""
        analysis = state.get("analysis_output", "")

        prompt = f"""You are a Senior Software Architect. Design a complete SaaS architecture for:

{query}

Context from analysis:
{analysis[:1500]}

Produce a DETAILED TECHNICAL ARCHITECTURE document containing:

## 1. Tech Stack Decision
- Backend: (language, framework, why)
- Frontend: (framework, why)
- Database: (primary DB, cache, why)
- Auth: (JWT/OAuth strategy)
- Hosting: (recommended cloud + services)

## 2. Project Structure
Show the complete directory tree for both backend and frontend.

## 3. Database Schema
Write the complete SQL schema (CREATE TABLE statements) for all core tables.

## 4. API Design
List all REST API endpoints with method, path, request/response shape.

## 5. Key Technical Decisions
Justify every major choice with trade-offs.

Be extremely specific. Use real library names, real versions."""

        try:
            response = llm.invoke(prompt)
            output = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.error("Architect agent error: %s", exc)
            output = f"Architect agent encountered an error: {exc}"

        state["architect_output"] = output
        state["messages"] = state["messages"] + [
            {"role": "assistant", "content": output, "agent": "architect_agent"}
        ]
        self.provenance.record(agent_id="architect_agent", action="architecture_design",
                               input_data=query, output_data=output)
        return state

    def _backend_coder_logic(self, state: WorkflowState) -> WorkflowState:
        llm       = _get_llm(state["llm_provider"], state["llm_model"])
        query     = state["messages"][0]["content"] if state["messages"] else ""
        architect = state.get("architect_output", "")

        prompt = f"""You are a Senior Backend Engineer. Write PRODUCTION-READY backend code for:

{query}

Architecture reference:
{architect[:2000]}

Generate COMPLETE, RUNNABLE code files. Include:

### FILE: main.py
Complete FastAPI application entrypoint with all routers mounted.

### FILE: models.py
SQLAlchemy async ORM models matching the schema above.

### FILE: schemas.py
Pydantic v2 request/response schemas for every endpoint.

### FILE: routers/auth.py
JWT auth: register, login, refresh token, logout endpoints — full implementation.

### FILE: routers/core.py
The 3-5 most important domain endpoints — full CRUD implementation.

### FILE: services/core_service.py
Business logic layer — full implementation.

### FILE: database.py
Async SQLAlchemy engine + session factory.

### FILE: requirements.txt
All Python dependencies with pinned versions.

### FILE: Dockerfile
Multi-stage production Dockerfile.

Write COMPLETE code — no placeholders, no "# implement this". Every function must be fully implemented."""

        try:
            response = llm.invoke(prompt)
            output = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.error("Backend coder error: %s", exc)
            output = f"Backend coder agent encountered an error: {exc}"

        state["backend_code"] = output
        state["messages"] = state["messages"] + [
            {"role": "assistant", "content": output, "agent": "backend_coder_agent"}
        ]
        self.provenance.record(agent_id="backend_coder_agent", action="backend_generation",
                               input_data=query, output_data=output)
        return state

    def _frontend_coder_logic(self, state: WorkflowState) -> WorkflowState:
        llm     = _get_llm(state["llm_provider"], state["llm_model"])
        query   = state["messages"][0]["content"] if state["messages"] else ""
        backend = state.get("backend_code", "")

        prompt = f"""You are a Senior Frontend Engineer. Write PRODUCTION-READY frontend code for:

{query}

Backend API reference (use these endpoints):
{backend[:1500]}

Generate COMPLETE, RUNNABLE React/Next.js 14 code files:

### FILE: package.json
All dependencies with versions (Next.js 14, TypeScript, Tailwind, shadcn/ui, etc.)

### FILE: app/layout.tsx
Root layout with providers, fonts, metadata.

### FILE: app/page.tsx
Landing page — full implementation with hero, features, CTA.

### FILE: app/dashboard/page.tsx
Main authenticated dashboard — full implementation.

### FILE: app/auth/login/page.tsx
Login page with form, validation, JWT handling.

### FILE: lib/api.ts
Full API client with all endpoints typed, auth header injection, error handling.

### FILE: components/ui/DataTable.tsx
Reusable data table component.

### FILE: tailwind.config.ts
Tailwind config.

### FILE: Dockerfile
Production Next.js Dockerfile.

### FILE: docker-compose.yml
Full docker-compose with backend, frontend, postgres, redis.

Write COMPLETE code — no placeholders. Every component must be fully implemented."""

        try:
            response = llm.invoke(prompt)
            output = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.error("Frontend coder error: %s", exc)
            output = f"Frontend coder agent encountered an error: {exc}"

        state["frontend_code"] = output
        state["final_output"] = (
            f"## Backend Code\n\n{state.get('backend_code','')}\n\n"
            f"## Frontend Code\n\n{output}"
        )
        state["messages"] = state["messages"] + [
            {"role": "assistant", "content": output, "agent": "frontend_coder_agent"}
        ]
        self.provenance.record(agent_id="frontend_coder_agent", action="frontend_generation",
                               input_data=query, output_data=output)
        return state

    def _evaluate_node(self, state: WorkflowState) -> WorkflowState:
        """Run CATERYAEvaluator on final output and persist results."""
        final_output = state.get("final_output", "")

        cos_result = self.evaluator.evaluate(
            output=final_output,
            context={
                "tenant_id": state["tenant_id"],
                "agent_id":  state["agent_id"],
                "trace_id":  state["trace_id"],
                "timestamp": state["timestamp"],
                "query":     state["messages"][0]["content"] if state["messages"] else "",
            },
        )

        state["cos_result"] = cos_result.to_dict()
        state["provenance_chain"] = self.provenance.get_chain()

        # Persist state to Redis (if available)
        if self.redis:
            self._persist_state(state)

        logger.info(
            "Workflow complete | tenant=%s cos=%.4f passed=%s",
            state["tenant_id"], cos_result.cos, cos_result.passed,
        )
        return state

    # ── Routing ─────────────────────────────────────────────────────────────

    @staticmethod
    def _route_after_node(state: WorkflowState) -> Literal["blocked", "continue"]:
        return "blocked" if state.get("guardrail_blocked") else "continue"

    # ── Run ─────────────────────────────────────────────────────────────────

    def run(
        self,
        query: str,
        user_id: Optional[str] = None,
        workflow_mode: str = "analyse",
    ) -> Dict[str, Any]:
        """Blocking execution. Returns a plain dict."""
        initial = make_initial_state(
            query=query, tenant_id=self.tenant_id, user_id=user_id,
            llm_provider=self.llm_provider, llm_model=self.llm_model,
            workflow_mode=workflow_mode,
        )
        result = self._graph.invoke(initial)
        if isinstance(result, dict):
            return result
        return {"final_output": str(result), "cos_result": {}, "provenance_chain": []}

    def stream(self, query: str, user_id: Optional[str] = None, workflow_mode: str = "analyse"):
        """Streaming execution — yields (node_name, state) tuples."""
        initial = make_initial_state(
            query=query, tenant_id=self.tenant_id, user_id=user_id,
            llm_provider=self.llm_provider, llm_model=self.llm_model,
            workflow_mode=workflow_mode,
        )
        for event in self._graph.stream(initial):
            for node_name, node_state in event.items():
                yield node_name, node_state

    # ── Persistence ──────────────────────────────────────────────────────────

    def _persist_state(self, state: WorkflowState) -> None:
        try:
            key = f"workflow_state:{self.tenant_id}:{state['session_id']}"
            serialisable = {
                k: v for k, v in state.items()
                if isinstance(v, (str, int, float, bool, list, dict, type(None)))
            }
            self.redis.setex(key, 86400, json.dumps(serialisable, default=str))
        except Exception as exc:
            logger.warning("Failed to persist workflow state: %s", exc)

    def load_state(self, session_id: str) -> Optional[WorkflowState]:
        if not self.redis:
            return None
        try:
            key = f"workflow_state:{self.tenant_id}:{session_id}"
            data = self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Failed to load workflow state: %s", exc)
            return None
