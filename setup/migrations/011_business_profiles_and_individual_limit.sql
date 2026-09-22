-- 011: owner business profile for institute/company workspaces and one active
-- individual workspace per independent teacher.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;

LOCK TABLE classarit.workspaces, classarit.app_users IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE IF NOT EXISTS classarit.business_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES classarit.app_users(id),
    legal_name text NOT NULL CHECK (length(btrim(legal_name)) > 0),
    gstin text CHECK (gstin IS NULL OR gstin ~ '^[0-9A-Z-]{6,30}$'),
    owner_aadhaar_number text CHECK (owner_aadhaar_number IS NULL OR owner_aadhaar_number ~ '^[0-9A-Z-]{6,30}$'),
    address_line1 text,
    address_line2 text,
    city text,
    state text,
    postal_code text,
    country char(2) NOT NULL DEFAULT 'IN',
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ARCHIVED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_business_profile_owner
ON classarit.business_profiles(owner_user_id)
WHERE status='ACTIVE';

CREATE UNIQUE INDEX IF NOT EXISTS uq_business_profiles_gstin
ON classarit.business_profiles(gstin)
WHERE gstin IS NOT NULL AND status='ACTIVE';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='classarit' AND table_name='workspaces'
          AND column_name='business_profile_id'
    ) THEN
        ALTER TABLE classarit.workspaces
            ADD COLUMN business_profile_id uuid REFERENCES classarit.business_profiles(id);
    END IF;
END;
$$;

INSERT INTO classarit.business_profiles(owner_user_id, legal_name)
SELECT w.owner_user_id, min(w.name)
FROM classarit.workspaces w
WHERE w.workspace_type='INSTITUTE'
  AND w.status='ACTIVE'
  AND NOT EXISTS (
      SELECT 1 FROM classarit.business_profiles b
      WHERE b.owner_user_id=w.owner_user_id AND b.status='ACTIVE'
  )
GROUP BY w.owner_user_id;

UPDATE classarit.workspaces w
SET business_profile_id=b.id
FROM classarit.business_profiles b
WHERE w.workspace_type='INSTITUTE'
  AND w.business_profile_id IS NULL
  AND b.owner_user_id=w.owner_user_id
  AND b.status='ACTIVE';

CREATE OR REPLACE FUNCTION classarit.validate_workspace_business_profile()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.workspace_type='INDIVIDUAL' AND NEW.business_profile_id IS NOT NULL THEN
        RAISE EXCEPTION 'Individual workspaces do not use business profiles' USING ERRCODE='23514';
    END IF;
    IF NEW.workspace_type='INSTITUTE' AND NEW.business_profile_id IS NULL THEN
        RAISE EXCEPTION 'Institute workspaces require an owner business profile' USING ERRCODE='23514';
    END IF;
    IF NEW.workspace_type='INSTITUTE' AND NOT EXISTS (
        SELECT 1 FROM classarit.business_profiles b
        WHERE b.id=NEW.business_profile_id
          AND b.owner_user_id=NEW.owner_user_id
          AND b.status='ACTIVE'
    ) THEN
        RAISE EXCEPTION 'Business profile must belong to the workspace owner' USING ERRCODE='23514';
    END IF;
    IF NEW.workspace_type='INDIVIDUAL'
       AND NEW.status='ACTIVE'
       AND EXISTS (
           SELECT 1 FROM classarit.workspaces w
           WHERE w.owner_user_id=NEW.owner_user_id
             AND w.workspace_type='INDIVIDUAL'
             AND w.status='ACTIVE'
             AND w.id<>NEW.id
       ) THEN
        RAISE EXCEPTION 'Independent teachers can have one active individual workspace' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_workspace_business_profile ON classarit.workspaces;
CREATE TRIGGER trg_workspace_business_profile
BEFORE INSERT OR UPDATE OF workspace_type, owner_user_id, business_profile_id, status
ON classarit.workspaces
FOR EACH ROW EXECUTE FUNCTION classarit.validate_workspace_business_profile();

DROP TRIGGER IF EXISTS trg_business_profiles_updated_at ON classarit.business_profiles;
CREATE TRIGGER trg_business_profiles_updated_at BEFORE UPDATE ON classarit.business_profiles
FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

COMMENT ON TABLE classarit.business_profiles IS 'Company or organization identity for institute workspaces and future SaaS subscription billing.';
COMMENT ON COLUMN classarit.business_profiles.gstin IS 'Unique business identification number, such as GSTN/GSTIN in India.';
COMMENT ON COLUMN classarit.business_profiles.owner_aadhaar_number IS 'Owner government ID number, such as Aadhaar in India; consider encryption before production use.';
COMMENT ON COLUMN classarit.workspaces.business_profile_id IS 'Set for institute/company workspaces; null for individual teacher workspaces.';

COMMIT;
