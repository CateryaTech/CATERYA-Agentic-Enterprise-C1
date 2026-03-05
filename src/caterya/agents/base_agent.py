"""
CATERYA Base Agent
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech
"""
from __future__ import annotations
import uuid
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from src.caterya.core.guardrail import CATERYAGuardrail

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all CATERYA agents."""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        guardrail: Optional[CATERYAGuardrail] = None,
    ):
        self.agent_id  = agent_id or str(uuid.uuid4())
        self.tenant_id = tenant_id
        self.guardrail = guardrail or CATERYAGuardrail(
            agent_name=self.__class__.__name__,
            tenant_id=tenant_id,
        )

    @abstractmethod
    def run(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> Any:
        """Execute the agent's primary logic."""

    def safe_run(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> Any:
        """Run with pre/post guardrail checks."""
        ctx = context or {}
        ctx.update({"agent_id": self.agent_id, "tenant_id": self.tenant_id})

        pre = self.guardrail.check(str(input_data), context=ctx)
        if not pre.allowed:
            return {"error": "Guardrail blocked input", "reasons": pre.reasons}

        result = self.run(input_data, ctx)

        post = self.guardrail.check(str(result), context=ctx)
        if not post.allowed:
            return {"error": "Guardrail blocked output", "reasons": post.reasons}

        return post.sanitized_output or result
