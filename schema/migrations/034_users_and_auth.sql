-- Migration 034: Users + role-based auth (SPEC_018)
--
-- Adds the users table for the demo auth layer. Three roles in hierarchy:
-- viewer < uploader < enterprise. Anonymous (no row, no token) is always
-- the default — protected routes return 401 when no Authorization header.
--
-- Migration is additive. Idempotent via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb,
    CONSTRAINT users_role_valid CHECK (role IN ('viewer', 'uploader', 'enterprise'))
);

-- Lookup by lowercased email for case-insensitive login
CREATE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role) WHERE is_active;
