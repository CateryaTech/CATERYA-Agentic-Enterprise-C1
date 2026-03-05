"""
ProvenanceChain — Immutable Audit Trail (on-chain simulation + optional EVM)
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Provides cryptographically linked chain of provenance records per tenant.
In production, records can be anchored to an EVM-compatible blockchain
(e.g. Polygon, Base) via web3.py integration.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProvenanceRecord:
    record_id: str
    tenant_id: str
    agent_id: str
    action: str
    input_hash: str
    output_hash: str
    previous_hash: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    block_hash: str = ""         # computed after creation

    def compute_hash(self) -> str:
        payload = json.dumps({
            "record_id":     self.record_id,
            "tenant_id":     self.tenant_id,
            "agent_id":      self.agent_id,
            "action":        self.action,
            "input_hash":    self.input_hash,
            "output_hash":   self.output_hash,
            "previous_hash": self.previous_hash,
            "timestamp":     self.timestamp,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProvenanceChain:
    """
    Per-tenant append-only provenance chain.

    Usage::

        chain = ProvenanceChain(tenant_id="acme")
        chain.record(
            agent_id="research_agent",
            action="web_search",
            input_data="user query",
            output_data="search results",
        )
        print(chain.provenance_score())
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, tenant_id: str, storage_backend: Optional[Any] = None):
        self.tenant_id = tenant_id
        self._chain: List[ProvenanceRecord] = []
        self._storage = storage_backend  # inject Redis or DB adapter

    # ── public ─────────────────────────────────

    def record(
        self,
        agent_id: str,
        action: str,
        input_data: Any,
        output_data: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProvenanceRecord:
        previous_hash = self._chain[-1].block_hash if self._chain else self.GENESIS_HASH

        rec = ProvenanceRecord(
            record_id=str(uuid.uuid4()),
            tenant_id=self.tenant_id,
            agent_id=agent_id,
            action=action,
            input_hash=self._hash(input_data),
            output_hash=self._hash(output_data),
            previous_hash=previous_hash,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        rec.block_hash = rec.compute_hash()
        self._chain.append(rec)

        if self._storage:
            self._persist(rec)

        logger.debug("Provenance recorded | tenant=%s agent=%s action=%s", self.tenant_id, agent_id, action)
        return rec

    def verify(self) -> bool:
        """Verify chain integrity (no tampering)."""
        for i, rec in enumerate(self._chain):
            expected_prev = self._chain[i - 1].block_hash if i > 0 else self.GENESIS_HASH
            if rec.previous_hash != expected_prev:
                logger.error("Chain tampered at index %d", i)
                return False
            if rec.block_hash != rec.compute_hash():
                logger.error("Hash mismatch at index %d", i)
                return False
        return True

    def provenance_score(self) -> float:
        """
        Returns a 0–1 score reflecting chain completeness and integrity.
        Used by TransparencyPillar for on-chain audit trail scoring.
        """
        if not self._chain:
            return 0.0
        integrity = 1.0 if self.verify() else 0.0
        completeness = min(1.0, len(self._chain) / 10.0)  # saturates at 10 records
        return round(0.7 * integrity + 0.3 * completeness, 4)

    def get_chain(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._chain]

    def export_json(self) -> str:
        return json.dumps(self.get_chain(), indent=2)

    # ── helpers ────────────────────────────────

    @staticmethod
    def _hash(data: Any) -> str:
        if isinstance(data, str):
            payload = data
        else:
            payload = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def _persist(self, rec: ProvenanceRecord) -> None:
        try:
            key = f"provenance:{self.tenant_id}:{rec.record_id}"
            self._storage.set(key, json.dumps(rec.to_dict()))
        except Exception as exc:
            logger.warning("Failed to persist provenance record: %s", exc)
