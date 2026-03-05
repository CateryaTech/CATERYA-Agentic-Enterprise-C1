"""
CATERYA Quantum Utilities
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Quantum-inspired randomness and entropy generation for:
- Non-deterministic agent sampling
- Provenance record entropy seeding
- Future quantum-resistant cryptography hooks
"""
from __future__ import annotations
import hashlib
import os
import struct
import time


def quantum_entropy(n_bytes: int = 32) -> bytes:
    """
    Generate quantum-inspired entropy by combining multiple entropy sources.
    In production, integrate with a QRNG API (e.g. ANU QRNG, IBM Quantum).
    """
    sources = [
        os.urandom(n_bytes),
        struct.pack("d", time.perf_counter()),
        struct.pack("d", time.time()),
    ]
    combined = b"".join(sources)
    return hashlib.sha3_256(combined).digest()[:n_bytes]


def quantum_seed() -> int:
    """Integer seed derived from quantum entropy for reproducible randomness."""
    entropy = quantum_entropy(8)
    return int.from_bytes(entropy, "big")


def superposition_weights(n: int) -> list[float]:
    """
    Generate n weights in a 'superposition' (sum to 1.0) using quantum entropy.
    Useful for randomised pillar weight exploration.
    """
    raw = [int.from_bytes(quantum_entropy(4), "big") for _ in range(n)]
    total = sum(raw)
    return [r / total for r in raw]
