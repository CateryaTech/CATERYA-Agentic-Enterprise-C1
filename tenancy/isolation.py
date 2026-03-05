"""
Multi-Tenant Isolation Manager
Author  : Ary HH <cateryatech@proton.me>
Company : CATERYA Tech
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from tenancy.models import Base, Tenant, User, make_tenant_models

logger = logging.getLogger(__name__)


class TenantManager:
    """
    Manages tenant lifecycle: provisioning, isolation, schema creation.

    Usage::

        mgr = TenantManager(database_url="postgresql://...")
        mgr.provision_tenant(slug="acme", name="Acme Corp")

        with mgr.tenant_session("acme") as session:
            # All queries are scoped to tenant schema
            runs = session.query(mgr.models("acme")["AgentRun"]).all()
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._engine = create_engine(database_url, poolclass=NullPool)
        self._SessionFactory = sessionmaker(bind=self._engine)
        self._tenant_models: Dict[str, Any] = {}
        self._ensure_public_schema()

    # ── Provisioning ───────────────────────────────────────────────────────

    def provision_tenant(
        self,
        slug: str,
        name: str,
        plan: str = "free",
        admin_email: Optional[str] = None,
    ) -> Tenant:
        schema = f"tenant_{slug.lower().replace('-', '_')}"

        with self._SessionFactory() as session:
            existing = session.query(Tenant).filter_by(slug=slug).first()
            if existing:
                logger.info("Tenant '%s' already exists", slug)
                return existing

            tenant = Tenant(
                id=uuid.uuid4(),
                slug=slug,
                name=name,
                plan=plan,
                db_schema=schema,
            )
            session.add(tenant)
            session.commit()

        self._create_tenant_schema(schema)
        self._create_tenant_tables(schema)
        logger.info("Tenant '%s' provisioned with schema '%s'", slug, schema)
        return tenant

    def deprovision_tenant(self, slug: str) -> None:
        with self._SessionFactory() as session:
            tenant = session.query(Tenant).filter_by(slug=slug).first()
            if not tenant:
                return
            schema = tenant.db_schema
            session.delete(tenant)
            session.commit()

        with self._engine.connect() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.commit()
        logger.info("Tenant '%s' deprovisioned", slug)

    # ── Session context manager ────────────────────────────────────────────

    @contextmanager
    def tenant_session(self, slug: str) -> Generator[Session, None, None]:
        tenant = self._get_tenant(slug)
        session = self._SessionFactory()
        try:
            # Set search_path so bare table names resolve to tenant schema
            session.execute(
                text(f"SET search_path TO {tenant.db_schema}, public")
            )
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def models(self, slug: str) -> Dict[str, Any]:
        """Return SQLAlchemy model classes for a given tenant slug."""
        tenant = self._get_tenant(slug)
        schema = tenant.db_schema
        if schema not in self._tenant_models:
            self._tenant_models[schema] = make_tenant_models(schema)
        return self._tenant_models[schema]

    # ── Internal ───────────────────────────────────────────────────────────

    def _ensure_public_schema(self) -> None:
        Base.metadata.create_all(self._engine, tables=[
            Base.metadata.tables.get("public.tenants"),
            Base.metadata.tables.get("public.users"),
        ])

    def _create_tenant_schema(self, schema: str) -> None:
        with self._engine.connect() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            conn.commit()

    def _create_tenant_tables(self, schema: str) -> None:
        models = make_tenant_models(schema)
        self._tenant_models[schema] = models
        Base.metadata.create_all(self._engine)

    def _get_tenant(self, slug: str) -> Tenant:
        with self._SessionFactory() as session:
            tenant = session.query(Tenant).filter_by(slug=slug, is_active=True).first()
            if not tenant:
                raise ValueError(f"Tenant '{slug}' not found or inactive")
            return tenant
