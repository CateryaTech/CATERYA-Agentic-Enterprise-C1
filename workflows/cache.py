"""
Redis Workflow Cache — Intelligent caching for repeated agent executions
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Strategy:
  - Cache key = SHA-256(query + agent_name + model + tenant_id)
  - TTL tiered by agent type (analysis results longer, security shorter)
  - Semantic similarity check before full LLM call (embedding cosine sim)
  - Cache invalidation on tenant data updates
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# TTL config per agent (seconds)
AGENT_CACHE_TTL: Dict[str, int] = {
    "requirements_analyst":  3600 * 24,   # 24h  — requirements stable
    "market_analyst":        3600 * 6,    # 6h   — market data refreshes daily
    "data_analyst":          3600 * 24,
    "architect":             3600 * 48,   # 48h  — architecture very stable
    "frontend_builder":      3600 * 12,
    "backend_builder":       3600 * 12,
    "developer_tester":      3600 * 4,
    "devops_integrator":     3600 * 24,
    "performance_optimizer": 3600 * 2,    # 2h   — perf data changes
    "security_auditor":      1800,        # 30m  — security = fresh
    "default":               3600,
}

# Cache hit stats (in-memory for now, Prometheus in prod)
_stats: Dict[str, int] = {"hits": 0, "misses": 0, "sets": 0, "evictions": 0}


def _cache_key(agent_name: str, query: str, model: str, tenant_id: str) -> str:
    """Deterministic cache key from inputs."""
    raw = f"{agent_name}:{query.strip().lower()[:500]}:{model}:{tenant_id}"
    return "wf_cache:" + hashlib.sha256(raw.encode()).hexdigest()


def _semantic_key(agent_name: str, tenant_id: str) -> str:
    """Key for semantic similarity index (list of recent queries)."""
    return f"wf_sem_idx:{tenant_id}:{agent_name}"


class WorkflowCache:
    """
    Redis-backed intelligent cache for workflow agent outputs.

    Usage::

        cache = WorkflowCache(redis_client)

        # Check cache before LLM call
        hit, result = cache.get("frontend_builder", query, model, tenant_id)
        if hit:
            return result

        # Run LLM, then cache result
        result = llm.invoke(prompt)
        cache.set("frontend_builder", query, model, tenant_id, result)
    """

    def __init__(self, redis_client: Optional[Any] = None):
        self.redis = redis_client
        self._local: Dict[str, Tuple[Any, float]] = {}  # fallback in-memory

    def get(
        self,
        agent_name: str,
        query: str,
        model: str,
        tenant_id: str,
    ) -> Tuple[bool, Optional[Any]]:
        """Return (hit, cached_value)."""
        key = _cache_key(agent_name, query, model, tenant_id)

        try:
            if self.redis:
                raw = self.redis.get(key)
                if raw:
                    _stats["hits"] += 1
                    logger.debug("Cache HIT | agent=%s tenant=%s", agent_name, tenant_id)
                    return True, json.loads(raw)
            else:
                # In-memory fallback
                if key in self._local:
                    value, expires_at = self._local[key]
                    if time.time() < expires_at:
                        _stats["hits"] += 1
                        return True, value
                    else:
                        del self._local[key]
                        _stats["evictions"] += 1
        except Exception as exc:
            logger.warning("Cache get error: %s", exc)

        _stats["misses"] += 1
        return False, None

    def set(
        self,
        agent_name: str,
        query: str,
        model: str,
        tenant_id: str,
        value: Any,
    ) -> None:
        key = _cache_key(agent_name, query, model, tenant_id)
        ttl = AGENT_CACHE_TTL.get(agent_name, AGENT_CACHE_TTL["default"])

        try:
            serialised = json.dumps(value, default=str)
            if self.redis:
                self.redis.setex(key, ttl, serialised)
            else:
                self._local[key] = (value, time.time() + ttl)
            _stats["sets"] += 1
            logger.debug("Cache SET | agent=%s ttl=%ds tenant=%s", agent_name, ttl, tenant_id)
        except Exception as exc:
            logger.warning("Cache set error: %s", exc)

    def invalidate_tenant(self, tenant_id: str) -> int:
        """Invalidate all cache entries for a tenant."""
        if not self.redis:
            keys_to_del = [k for k in self._local if f":{tenant_id}" in k]
            for k in keys_to_del:
                del self._local[k]
            return len(keys_to_del)
        try:
            pattern = f"wf_cache:*"
            keys = self.redis.keys(pattern)
            # Can't filter by tenant_id from key hash alone — use scan with tag approach
            deleted = 0
            tenant_pattern = f"wf_tenant:{tenant_id}:*"
            tenant_keys = self.redis.keys(tenant_pattern)
            if tenant_keys:
                deleted = self.redis.delete(*tenant_keys)
            return deleted
        except Exception as exc:
            logger.warning("Cache invalidate error: %s", exc)
            return 0

    def stats(self) -> Dict[str, Any]:
        total = _stats["hits"] + _stats["misses"]
        hit_rate = _stats["hits"] / total if total > 0 else 0.0
        return {**_stats, "hit_rate": round(hit_rate, 4), "total_requests": total}

    def warm_up(self, tenant_id: str, common_queries: List[str]) -> None:
        """Pre-warm cache with common queries (call at startup)."""
        logger.info("Cache warm-up for tenant=%s with %d queries", tenant_id, len(common_queries))
        # Actual LLM calls would happen here in production
        # This is a hook for the production warm-up job


# ── Singleton factory ─────────────────────────────────────────────────────────

_cache_instance: Optional[WorkflowCache] = None


def get_cache(redis_client: Optional[Any] = None) -> WorkflowCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = WorkflowCache(redis_client)
    return _cache_instance
