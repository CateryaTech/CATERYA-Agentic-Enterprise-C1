"""
Accountability Pillar
Author  : Ary HH <cateryatech@proton.me>
"""
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple


class AccountabilityPillar:
    def evaluate(self, output: str, ctx: Optional[Dict[str, Any]] = None) -> Tuple[float, Dict]:
        ctx = ctx or {}
        has_agent_id  = bool(ctx.get("agent_id"))
        has_trace     = bool(ctx.get("trace_id") or ctx.get("run_id"))
        has_tenant    = bool(ctx.get("tenant_id"))
        has_timestamp = bool(ctx.get("timestamp"))
        accountability_hits = sum([has_agent_id, has_trace, has_tenant, has_timestamp])
        score = 0.4 + (accountability_hits / 4) * 0.6
        return score, {
            "has_agent_id": has_agent_id,
            "has_trace_id": has_trace,
            "has_tenant_id": has_tenant,
            "has_timestamp": has_timestamp,
        }
