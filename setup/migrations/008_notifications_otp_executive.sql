-- 008: email OTP registration, product controls and lightweight API telemetry.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;
LOCK TABLE classarit.app_users, classarit.auth_challenges IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE classarit.auth_challenges
    DROP CONSTRAINT IF EXISTS auth_challenges_purpose_check;
ALTER TABLE classarit.auth_challenges
    ADD CONSTRAINT auth_challenges_purpose_check CHECK (purpose IN
        ('EMAIL_VERIFY', 'PASSWORD_SETUP', 'PASSWORD_RESET', 'LINK_IDENTITY', 'REGISTRATION_EMAIL_OTP'));

CREATE TABLE classarit.app_settings (
    key text PRIMARY KEY CHECK (key ~ '^[a-z0-9_]{3,80}$'),
    value text NOT NULL CHECK (value IN ('true', 'false')),
    updated_by uuid REFERENCES classarit.app_users(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_app_settings_updated_at BEFORE UPDATE ON classarit.app_settings
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

INSERT INTO classarit.app_settings(key, value) VALUES
    ('google_new_accounts_enabled', 'true'),
    ('signup_enabled', 'true'),
    ('notification_emails_enabled', 'true')
ON CONFLICT (key) DO NOTHING;

CREATE TABLE classarit.api_request_metrics (
    id bigserial PRIMARY KEY,
    captured_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    method text NOT NULL CHECK (method ~ '^[A-Z]{3,10}$'),
    path text NOT NULL CHECK (length(path) <= 300),
    route_template text NOT NULL CHECK (length(route_template) <= 300),
    status_code integer NOT NULL CHECK (status_code BETWEEN 100 AND 599),
    latency_ms integer NOT NULL CHECK (latency_ms >= 0 AND latency_ms <= 600000),
    user_id uuid REFERENCES classarit.app_users(id) ON DELETE SET NULL
);
CREATE INDEX idx_api_request_metrics_captured_at ON classarit.api_request_metrics(captured_at DESC);
CREATE INDEX idx_api_request_metrics_route_day ON classarit.api_request_metrics(route_template, captured_at DESC);

COMMENT ON TABLE classarit.api_request_metrics IS 'Minimal request telemetry for executive dashboard: no query strings, request bodies, IPs or user agents.';
COMMENT ON TABLE classarit.app_settings IS 'Runtime product controls managed from the executive dashboard.';
COMMIT;
