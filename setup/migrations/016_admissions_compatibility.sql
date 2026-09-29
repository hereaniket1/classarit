-- Reconstruct the application contract without replacing the lost 014/015 files
-- or their recorded checksums. Safe after 013 on fresh DBs and after 015 on hosted DBs.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, public, pg_catalog;
DO $$
DECLARE extension_schema text;
BEGIN
    SELECT n.nspname INTO extension_schema FROM pg_extension e
    JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='citext';
    PERFORM set_config('search_path', format('classarit,%I,pg_catalog', extension_schema), true);
END;
$$;

CREATE TABLE IF NOT EXISTS classarit.interest (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name text NOT NULL CHECK (length(btrim(full_name)) BETWEEN 1 AND 150),
    email citext NOT NULL,
    country char(2) NOT NULL CHECK (country ~ '^[A-Z]{2}$'),
    usage_type text CHECK (usage_type IN ('INDIVIDUAL','ORGANIZATION')),
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED')),
    requested_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at timestamptz,
    approved_by uuid REFERENCES classarit.app_users(id) ON DELETE SET NULL,
    last_email_sent_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_interest_review_queue ON classarit.interest(status,requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_interest_normalized_email ON classarit.interest(lower(email::text));
ALTER TABLE classarit.app_users ADD COLUMN IF NOT EXISTS account_type text
    CHECK (account_type IN ('INDIVIDUAL','ORGANIZATION'));
CREATE TABLE IF NOT EXISTS classarit.app_content (
    key text PRIMARY KEY,
    title text NOT NULL,
    body text NOT NULL,
    updated_by uuid REFERENCES classarit.app_users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO classarit.app_settings(key,value) VALUES ('invite_request_enabled','false')
ON CONFLICT(key) DO NOTHING;

DROP TRIGGER IF EXISTS trg_interest_updated_at ON classarit.interest;
CREATE TRIGGER trg_interest_updated_at BEFORE UPDATE ON classarit.interest
FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();
DROP TRIGGER IF EXISTS trg_app_content_updated_at ON classarit.app_content;
CREATE TRIGGER trg_app_content_updated_at BEFORE UPDATE ON classarit.app_content
FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

-- Preserve existing business-profile guards while adding the hosted early-access cap.
CREATE OR REPLACE FUNCTION classarit.guard_organization_workspace_limit()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.workspace_type='INSTITUTE' AND NEW.status='ACTIVE' THEN
        PERFORM id FROM classarit.app_users WHERE id=NEW.owner_user_id FOR UPDATE;
        IF (SELECT count(*) FROM classarit.workspaces WHERE owner_user_id=NEW.owner_user_id
            AND workspace_type='INSTITUTE' AND status='ACTIVE' AND id<>NEW.id) >= 3 THEN
            RAISE EXCEPTION 'Organizations can have up to three active workspaces during early access' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_organization_workspace_limit ON classarit.workspaces;
CREATE TRIGGER trg_organization_workspace_limit
BEFORE INSERT OR UPDATE OF workspace_type,owner_user_id,status ON classarit.workspaces
FOR EACH ROW EXECUTE FUNCTION classarit.guard_organization_workspace_limit();
COMMIT;
