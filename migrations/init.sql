-- ── CATERYA Enterprise — Initial Migration ───────────────────────────────────
-- Creates public schema tables (shared across tenants)
-- Tenant-specific schemas are created dynamically by TenantManager

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ── Tenants ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.tenants (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug        VARCHAR(64) UNIQUE NOT NULL,
    name        VARCHAR(255) NOT NULL,
    plan        VARCHAR(32) DEFAULT 'free',
    is_active   BOOLEAN DEFAULT TRUE,
    db_schema   VARCHAR(64) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ,
    settings    JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_tenants_slug ON public.tenants(slug);

-- ── Users ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.users (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id        UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    email            VARCHAR(255) NOT NULL,
    hashed_password  VARCHAR(255),
    role             VARCHAR(32) DEFAULT 'member',
    is_active        BOOLEAN DEFAULT TRUE,
    oauth_provider   VARCHAR(32),
    oauth_sub        VARCHAR(255),
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    last_login       TIMESTAMPTZ,
    CONSTRAINT uq_tenant_user_email UNIQUE (tenant_id, email)
);

CREATE INDEX IF NOT EXISTS ix_users_tenant_id ON public.users(tenant_id);
CREATE INDEX IF NOT EXISTS ix_users_email     ON public.users(email);

-- ── Seed demo tenant ──────────────────────────────────────────────────────────
INSERT INTO public.tenants (slug, name, plan, db_schema)
VALUES ('demo', 'Demo Tenant', 'enterprise', 'tenant_demo')
ON CONFLICT (slug) DO NOTHING;
