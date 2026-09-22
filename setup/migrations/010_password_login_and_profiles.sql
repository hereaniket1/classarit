-- 010: password login, shared user profiles and guardian identity links.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;

ALTER TABLE classarit.app_users
    ADD COLUMN IF NOT EXISTS phone text,
    ADD COLUMN IF NOT EXISTS date_of_birth date,
    ADD COLUMN IF NOT EXISTS country text;

ALTER TABLE classarit.app_users
    DROP CONSTRAINT IF EXISTS app_users_phone_check,
    ADD CONSTRAINT app_users_phone_check
        CHECK (phone IS NULL OR length(btrim(phone)) BETWEEN 5 AND 30),
    DROP CONSTRAINT IF EXISTS app_users_date_of_birth_check,
    ADD CONSTRAINT app_users_date_of_birth_check
        CHECK (date_of_birth IS NULL OR date_of_birth <= CURRENT_DATE),
    DROP CONSTRAINT IF EXISTS app_users_country_check,
    ADD CONSTRAINT app_users_country_check
        CHECK (country IS NULL OR length(btrim(country)) BETWEEN 2 AND 100);

ALTER TABLE classarit.guardians
    ADD COLUMN IF NOT EXISTS linked_user_id uuid
        REFERENCES classarit.app_users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_guardians_linked_user
    ON classarit.guardians(linked_user_id)
    WHERE linked_user_id IS NOT NULL;

INSERT INTO classarit.app_settings(key, value)
VALUES ('email_verification_enabled', 'true')
ON CONFLICT (key) DO NOTHING;

COMMIT;
