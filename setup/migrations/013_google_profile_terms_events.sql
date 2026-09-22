-- 013: support first-time Google profile completion as its own terms event.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;

ALTER TABLE IF EXISTS classarit.user_terms_acceptances
    DROP CONSTRAINT IF EXISTS user_terms_acceptances_app_user_id_terms_version_key;

ALTER TABLE IF EXISTS classarit.user_terms_acceptances
    DROP CONSTRAINT IF EXISTS user_terms_acceptances_acceptance_source_check;

ALTER TABLE IF EXISTS classarit.user_terms_acceptances
    ADD CONSTRAINT user_terms_acceptances_acceptance_source_check
    CHECK (acceptance_source IN ('GOOGLE_LOGIN','GOOGLE_PROFILE','PASSWORD_SIGNUP','EMAIL_OTP_SIGNUP'));

CREATE INDEX IF NOT EXISTS idx_user_terms_acceptances_user_version
ON classarit.user_terms_acceptances(app_user_id, terms_version, accepted_at DESC);

COMMIT;
