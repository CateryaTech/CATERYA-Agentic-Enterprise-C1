"""
CATERYA Native LLM Clients
Author : Ary HH <cateryatech@proton.me>

Implements LangChain-compatible .invoke() wrappers for:
  - Gemini  : native REST API  (generateContent endpoint)
  - Ollama  : native ollama SDK (qwen3.5 / qwen3-vl as primary)
  - OpenAI  : openai SDK       (also used for any OpenAI-compat provider)

Each class exposes .invoke(prompt) -> response.content (str)
so they are drop-in replacements for langchain_openai.ChatOpenAI.
"""
from __future__ import annotations
import os, json, logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Shared response wrapper (mimics LangChain AIMessage) ─────────────────────
class _Response:
    """Minimal AIMessage-compatible wrapper."""
    def __init__(self, content: str):
        self.content = content

    def __str__(self) -> str:
        return self.content


# ══════════════════════════════════════════════════════════════════════════════
# 1. Gemini — Native REST  (matches your curl exactly)
# ══════════════════════════════════════════════════════════════════════════════
class GeminiNativeClient:
    """
    Calls Google Gemini via the native generateContent REST endpoint.

    Endpoint used (from your curl):
      POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
      Header: X-goog-api-key: <GEMINI_API_KEY>
      Body:   { "contents": [{ "parts": [{ "text": "..." }] }] }

    Models available (free tier):
      gemini-2.0-flash          <- fastest, recommended default
      gemini-2.0-flash-lite
      gemini-1.5-flash-latest
      gemini-flash-latest       <- alias for latest flash
      gemini-1.5-pro-latest     <- most capable (slower)
    """
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        model:   str = "gemini-2.0-flash",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens:  int   = 8192,
    ):
        self.model       = model
        self.api_key     = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
        self.temperature = temperature
        self.max_tokens  = max_tokens

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY not set.\n"
                "Free key: https://aistudio.google.com/app/apikey\n"
                "Then: Streamlit Cloud → Settings → Secrets → GEMINI_API_KEY = 'AIza...'"
            )

    def invoke(self, prompt: Any) -> _Response:
        """
        Send prompt to Gemini generateContent endpoint.
        Accepts: str | LangChain HumanMessage | list of messages
        """
        import requests

        # Normalise input → plain string
        if isinstance(prompt, str):
            text = prompt
        elif hasattr(prompt, "content"):
            text = prompt.content
        elif isinstance(prompt, list):
            text = "\n".join(
                m.content if hasattr(m,"content") else str(m) for m in prompt
            )
        else:
            text = str(prompt)

        url = f"{self.BASE}/{self.model}:generateContent"

        payload = {
            "contents": [
                {"parts": [{"text": text}]}
            ],
            "generationConfig": {
                "temperature":    self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }

        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self.api_key,
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            # Extract text from Gemini response structure
            content = (
                data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
            )
            if not content:
                # Some models return it differently
                content = json.dumps(data)
            return _Response(content)

        except requests.exceptions.HTTPError as e:
            body = ""
            try: body = e.response.text[:400]
            except Exception: pass
            raise RuntimeError(f"Gemini API error {e.response.status_code}: {body}") from e

        except Exception as exc:
            raise RuntimeError(f"Gemini request failed: {exc}") from exc


# ── Also support LangChain wrapper (better token counting, callbacks) ─────────
def _gemini_langchain(model: str, api_key: str) -> Any:
    """Try langchain-google-genai first, fall back to GeminiNativeClient."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key)
    except ImportError:
        logger.info("langchain-google-genai not installed, using native Gemini REST client")
        return GeminiNativeClient(model=model, api_key=api_key)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Ollama — Native SDK  (qwen3.5 + qwen3-vl as primary models)
# ══════════════════════════════════════════════════════════════════════════════
class OllamaNativeClient:
    """
    Uses the official `ollama` Python SDK.

    Primary models (as requested):
      qwen3.5    — Qwen 3 (5B), fast, great for analysis & code
      qwen3-vl   — Qwen 3 Vision-Language, multimodal

    Usage (same as your example):
      from ollama import chat
      response = chat(
          model='qwen3.5',
          messages=[{'role': 'user', 'content': 'Hello!'}],
      )
      print(response.message.content)
    """
    DEFAULT_MODELS = ["qwen3.5", "qwen3-vl"]  # preferred order

    def __init__(
        self,
        model:    str = "qwen3.5",
        base_url: Optional[str] = None,
        api_key:  Optional[str] = None,
    ):
        self.model    = model
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.api_key  = api_key  or os.getenv("OLLAMA_API_KEY", "")

    def invoke(self, prompt: Any) -> _Response:
        # Normalise prompt → message list
        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        elif isinstance(prompt, list):
            messages = []
            for m in prompt:
                if hasattr(m, "content"):
                    role = getattr(m, "type", "user")
                    if role == "ai": role = "assistant"
                    messages.append({"role": role, "content": m.content})
                elif isinstance(m, dict):
                    messages.append(m)
                else:
                    messages.append({"role": "user", "content": str(m)})
        elif hasattr(prompt, "content"):
            messages = [{"role": "user", "content": prompt.content}]
        else:
            messages = [{"role": "user", "content": str(prompt)}]

        # Try native ollama SDK first
        try:
            from ollama import chat as ollama_chat, Client as OllamaClient

            if self.base_url and self.base_url != "http://localhost:11434":
                # Remote/hosted Ollama — use Client with custom host
                client = OllamaClient(host=self.base_url)
                response = client.chat(model=self.model, messages=messages)
            else:
                # Local Ollama
                response = ollama_chat(model=self.model, messages=messages)

            return _Response(response.message.content)

        except ImportError:
            logger.info("ollama package not installed, falling back to OpenAI-compat /v1 endpoint")
            return self._fallback_openai_compat(messages)

        except Exception as exc:
            err = str(exc)
            if "model" in err.lower() and ("not found" in err.lower() or "pull" in err.lower()):
                raise RuntimeError(
                    f"Model '{self.model}' not found in Ollama.\n"
                    f"Pull it first: `ollama pull {self.model}`\n"
                    f"Available free models: qwen3.5, qwen3-vl, llama3.2, mistral"
                ) from exc
            logger.warning("ollama SDK failed (%s), trying /v1 fallback", exc)
            return self._fallback_openai_compat(messages)

    def _fallback_openai_compat(self, messages: list) -> _Response:
        """Fallback: use OpenAI SDK with Ollama's /v1 endpoint."""
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=f"{self.base_url.rstrip('/')}/v1",
                api_key=self.api_key or "ollama",
            )
            resp = client.chat.completions.create(
                model=self.model, messages=messages
            )
            return _Response(resp.choices[0].message.content or "")
        except ImportError:
            # Last resort: raw requests
            return self._fallback_requests(messages)

    def _fallback_requests(self, messages: list) -> _Response:
        """Final fallback: raw HTTP to Ollama /api/chat."""
        import requests
        url = f"{self.base_url.rstrip('/')}/api/chat"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {"model": self.model, "messages": messages, "stream": False}
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        return _Response(content)


# ── LangChain ChatOllama wrapper (richer integration) ─────────────────────────
def _ollama_langchain(model: str, base_url: str) -> Any:
    """Try langchain-ollama first, fall back to OllamaNativeClient."""
    try:
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, base_url=base_url)
    except ImportError:
        try:
            from langchain_community.chat_models import ChatOllama as LCOllama
            return LCOllama(model=model, base_url=base_url)
        except ImportError:
            logger.info("langchain-ollama not installed, using native Ollama SDK client")
            return OllamaNativeClient(model=model, base_url=base_url)


# ══════════════════════════════════════════════════════════════════════════════
# 3. OpenAI SDK  (direct + OpenAI-compatible providers)
# ══════════════════════════════════════════════════════════════════════════════
class OpenAIClient:
    """
    Uses the official `openai` Python SDK.
    Works with OpenAI directly or any OpenAI-compatible endpoint
    (Groq, OpenRouter, Together, Fireworks, local Ollama /v1).
    """
    def __init__(
        self,
        model:    str = "gpt-4o-mini",
        api_key:  Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        self.model    = model
        self.api_key  = api_key  or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url
        self.kwargs   = kwargs

    def invoke(self, prompt: Any) -> _Response:
        # Normalise
        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        elif isinstance(prompt, list):
            messages = [
                {"role": getattr(m,"type","user").replace("ai","assistant"),
                 "content": m.content if hasattr(m,"content") else str(m)}
                for m in prompt
            ] if prompt and hasattr(prompt[0],"content") else prompt
        elif hasattr(prompt, "content"):
            messages = [{"role": "user", "content": prompt.content}]
        else:
            messages = [{"role": "user", "content": str(prompt)}]

        try:
            from openai import OpenAI
            kw = {}
            if self.base_url: kw["base_url"] = self.base_url
            client = OpenAI(api_key=self.api_key or "nokey", **kw)
            resp = client.chat.completions.create(model=self.model, messages=messages)
            return _Response(resp.choices[0].message.content or "")
        except ImportError:
            # Fallback: langchain-openai
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model=self.model, api_key=self.api_key,
                             base_url=self.base_url)
            r = llm.invoke(prompt)
            return _Response(r.content if hasattr(r,"content") else str(r))
