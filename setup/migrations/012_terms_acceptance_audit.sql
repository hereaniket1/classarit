-- 012: durable terms acceptance audit. This table is intentionally preserved by
-- the temporary executive data reset and can be deleted only through its own
-- executive-only action.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;

CREATE TABLE IF NOT EXISTS classarit.user_terms_acceptances (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_user_id uuid NOT NULL,
    email text,
    full_name text,
    terms_version text NOT NULL CHECK (length(btrim(terms_version)) > 0),
    acceptance_source text NOT NULL CHECK (acceptance_source IN ('GOOGLE_LOGIN','GOOGLE_PROFILE','PASSWORD_SIGNUP','EMAIL_OTP_SIGNUP')),
    accepted_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_hash text,
    user_agent_hash text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_terms_acceptances_user
ON classarit.user_terms_acceptances(app_user_id, accepted_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_terms_acceptances_version
ON classarit.user_terms_acceptances(terms_version, accepted_at DESC);

COMMENT ON TABLE classarit.user_terms_acceptances IS 'Durable audit of terms acceptance. Preserved by the temporary executive app-data reset.';
COMMENT ON COLUMN classarit.user_terms_acceptances.app_user_id IS 'User UUID at the time of acceptance. No foreign key so audit survives user data resets.';
COMMENT ON COLUMN classarit.user_terms_acceptances.ip_hash IS 'Optional keyed hash of IP metadata; raw IP is not stored.';
COMMENT ON COLUMN classarit.user_terms_acceptances.user_agent_hash IS 'Optional keyed hash of user-agent metadata; raw user-agent is not stored.';

COMMIT;
