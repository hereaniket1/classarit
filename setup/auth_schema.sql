-- PostgreSQL 14+; fresh installation only, not an existing app_users migration.
-- Execute with psql -v ON_ERROR_STOP=1 -f setup/auth_schema.sql.
BEGIN;
CREATE SCHEMA IF NOT EXISTS classarit;
CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA classarit;
-- Reuse an existing shared citext installation without relocating it.
DO $$
DECLARE extension_schema text;
BEGIN
    SELECT n.nspname INTO extension_schema FROM pg_extension e
    JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='citext';
    PERFORM set_config('search_path', format('classarit,%I,pg_catalog', extension_schema), true);
END;
$$;

-- Fail before changes if a legacy account table already exists.
DO $$
BEGIN
    IF to_regclass('classarit.app_users') IS NOT NULL THEN
        RAISE EXCEPTION 'app_users already exists; use a reviewed data migration, not this fresh-install DDL';
    END IF;
END;
$$;

-- Created before the triggers that depend on it.
CREATE OR REPLACE FUNCTION classarit.set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TABLE classarit.app_users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username citext UNIQUE,
    full_name text,
    avatar_url text,
    base_currency varchar(3) NOT NULL DEFAULT 'USD'
        CHECK (base_currency ~ '^[A-Z]{3}$'),
    status varchar(30) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'ACTIVE', 'BLOCKED', 'INACTIVE')),
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (username IS NULL OR username::text ~ '^[A-Za-z0-9_]{3,50}$')
);

CREATE TABLE classarit.user_emails (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_user_id uuid NOT NULL REFERENCES classarit.app_users(id) ON DELETE CASCADE,
    email citext NOT NULL UNIQUE,
    verified_at timestamptz,
    is_primary boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (email::text = btrim(email::text) AND length(email::text) > 0)
);
CREATE INDEX idx_user_emails_user ON classarit.user_emails(app_user_id);
CREATE UNIQUE INDEX uq_user_primary_email ON classarit.user_emails(app_user_id)
    WHERE is_primary;

CREATE TABLE classarit.auth_identities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_user_id uuid NOT NULL REFERENCES classarit.app_users(id) ON DELETE CASCADE,
    provider text NOT NULL CHECK (provider IN ('GOOGLE', 'APPLE', 'FACEBOOK')),
    provider_subject text NOT NULL CHECK (length(btrim(provider_subject)) > 0),
    provider_email citext,
    provider_email_verified boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_provider_subject UNIQUE (provider, provider_subject)
);
CREATE INDEX idx_auth_identities_user ON classarit.auth_identities(app_user_id);

CREATE TABLE classarit.password_credentials (
    app_user_id uuid PRIMARY KEY REFERENCES classarit.app_users(id) ON DELETE CASCADE,
    password_hash text NOT NULL CHECK (length(btrim(password_hash)) > 0),
    password_changed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.auth_challenges (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_user_id uuid NOT NULL REFERENCES classarit.app_users(id) ON DELETE CASCADE,
    target_email citext NOT NULL,
    purpose text NOT NULL CHECK (purpose IN
        ('EMAIL_VERIFY', 'PASSWORD_SETUP', 'PASSWORD_RESET', 'LINK_IDENTITY', 'REGISTRATION_EMAIL_OTP')),
    -- Keyed HMAC of a random code/token, challenge ID, purpose and target.
    -- The HMAC key belongs in server secrets, never in this database.
    secret_digest text NOT NULL CHECK (length(btrim(secret_digest)) > 0),
    -- Bind linking proof to the provider identity validated by the backend.
    pending_provider text CHECK (pending_provider IN ('GOOGLE', 'APPLE', 'FACEBOOK')),
    pending_subject text,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 5,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expires_at > created_at),
    CHECK (attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts),
    CHECK (
        (purpose = 'LINK_IDENTITY' AND pending_provider IS NOT NULL
         AND pending_subject IS NOT NULL AND length(btrim(pending_subject)) > 0)
        OR (purpose <> 'LINK_IDENTITY' AND pending_provider IS NULL AND pending_subject IS NULL)
    )
);
CREATE INDEX idx_auth_challenges_user ON classarit.auth_challenges(app_user_id);
CREATE INDEX idx_auth_challenges_expiry ON classarit.auth_challenges(expires_at)
    WHERE consumed_at IS NULL;

CREATE TRIGGER trg_app_users_updated_at BEFORE UPDATE ON classarit.app_users
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();
CREATE TRIGGER trg_user_emails_updated_at BEFORE UPDATE ON classarit.user_emails
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();
CREATE TRIGGER trg_auth_identities_updated_at BEFORE UPDATE ON classarit.auth_identities
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();
CREATE TRIGGER trg_password_credentials_updated_at BEFORE UPDATE ON classarit.password_credentials
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TABLE IF NOT EXISTS classarit.auth_sessions (
    token_hash text PRIMARY KEY,
    app_user_id uuid NOT NULL REFERENCES classarit.app_users(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON classarit.auth_sessions(app_user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON classarit.auth_sessions(expires_at);
COMMIT;
