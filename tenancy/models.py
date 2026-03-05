"""
Multi-Tenant Database Models
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech

Strategy: Schema-per-tenant on PostgreSQL.
Each tenant gets an isolated schema (e.g. tenant_acme, tenant_globex).
Shared tables (tenants, auth) live in the 'public' schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    Column, String, Text, Boolean, Float, DateTime, ForeignKey,
    JSON, Integer, UniqueConstraint, Index, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship, Session
from sqlalchemy.sql import func


# ── Base ───────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Public schema: Tenant registry ────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "public"}

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug        = Column(String(64), unique=True, nullable=False, index=True)
    name        = Column(String(255), nullable=False)
    plan        = Column(String(32), default="free")   # free | pro | enterprise
    is_active   = Column(Boolean, default=True)
    db_schema   = Column(String(64), nullable=False)   # e.g. "tenant_acme"
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    settings    = Column(JSON, default=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "slug": self.slug,
            "name": self.name,
            "plan": self.plan,
            "is_active": self.is_active,
            "db_schema": self.db_schema,
        }


# ── Public schema: Users ──────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "public"}

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id    = Column(UUID(as_uuid=True), ForeignKey("public.tenants.id"), nullable=False)
    email        = Column(String(255), nullable=False)
    hashed_password = Column(String(255))                # null if OAuth-only
    role         = Column(String(32), default="member")  # admin | member | viewer
    is_active    = Column(Boolean, default=True)
    oauth_provider = Column(String(32))                  # supabase | auth0 | google
    oauth_sub    = Column(String(255))                   # external subject ID
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    last_login   = Column(DateTime(timezone=True))

    tenant = relationship("Tenant")

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_tenant_user_email"),
        {"schema": "public"},
    )


# ── Tenant-specific tables (created per-schema) ───────────────────────────

def make_tenant_models(schema: str):
    """
    Dynamically create SQLAlchemy models bound to a specific tenant schema.
    Call this once per tenant during onboarding.
    """

    class AgentRun(Base):
        __tablename__ = "agent_runs"
        __table_args__ = (
            Index(f"ix_{schema}_agent_runs_created", "created_at"),
            {"schema": schema},
        )

        id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
        workflow_id = Column(String(128), nullable=False, index=True)
        agent_id    = Column(String(128), nullable=False)
        user_id     = Column(UUID(as_uuid=True), nullable=True)
        input_text  = Column(Text)
        output_text = Column(Text)
        cos_score   = Column(Float)
        status      = Column(String(32), default="pending")  # pending|running|done|failed
        trace_id    = Column(String(64), index=True)
        created_at  = Column(DateTime(timezone=True), server_default=func.now())
        completed_at = Column(DateTime(timezone=True))
        metadata    = Column(JSON, default=dict)

    class EvaluationResult(Base):
        __tablename__ = "evaluation_results"
        __table_args__ = {"schema": schema}

        id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
        run_id          = Column(UUID(as_uuid=True), ForeignKey(f"{schema}.agent_runs.id"))
        evaluation_id   = Column(String(64), unique=True, nullable=False)
        cos             = Column(Float, nullable=False)
        passed          = Column(Boolean, nullable=False)
        pillar_scores   = Column(JSON)
        created_at      = Column(DateTime(timezone=True), server_default=func.now())

        run = relationship("AgentRun")

    class ProvenanceRecord(Base):
        __tablename__ = "provenance_records"
        __table_args__ = {"schema": schema}

        id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
        record_id       = Column(String(64), unique=True, nullable=False)
        agent_id        = Column(String(128), nullable=False)
        action          = Column(String(128), nullable=False)
        input_hash      = Column(String(64))
        output_hash     = Column(String(64))
        previous_hash   = Column(String(64))
        block_hash      = Column(String(64))
        timestamp       = Column(Float)
        meta            = Column(JSON, default=dict)

    class WorkflowState(Base):
        __tablename__ = "workflow_states"
        __table_args__ = {"schema": schema}

        id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
        workflow_id = Column(String(128), unique=True, nullable=False, index=True)
        state_json  = Column(JSON, nullable=False)
        updated_at  = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    return {
        "AgentRun": AgentRun,
        "EvaluationResult": EvaluationResult,
        "ProvenanceRecord": ProvenanceRecord,
        "WorkflowState": WorkflowState,
    }
