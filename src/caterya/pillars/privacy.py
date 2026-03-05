"""
Privacy Pillar
Author  : Ary HH <cateryatech@proton.me>
"""
from __future__ import annotations
import re
from typing import Any, Dict, Optional, Tuple


class PrivacyPillar:
    _PII = [
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
        re.compile(r"\b(?:\d[ -]?){13,16}\b"),
        re.compile(r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
        re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    ]

    def evaluate(self, output: str, ctx: Optional[Dict[str, Any]] = None) -> Tuple[float, Dict]:
        ctx = ctx or {}
        pii_hits = sum(1 for p in self._PII if p.search(output))
        score = max(0.0, 1.0 - pii_hits * 0.25)
        return score, {"pii_detected": pii_hits, "pii_redacted": ctx.get("pii_redacted", False)}
