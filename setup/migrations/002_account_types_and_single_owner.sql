-- Account-level OWNER/MEMBER/APPOWNER and a single subscription owner per workspace.
-- Apply after 001 with setup/apply_migration.py. Existing ownership must be unambiguous.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;
LOCK TABLE classarit.workspaces, classarit.workspace_memberships, classarit.membership_roles, classarit.app_users IN SHARE ROW EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (
        SELECT w.id FROM classarit.workspaces w
        LEFT JOIN classarit.membership_roles r ON r.workspace_id=w.id AND r.role='OWNER'
        LEFT JOIN classarit.workspace_memberships m ON m.workspace_id=w.id AND m.id=r.membership_id AND m.status='ACTIVE'
        GROUP BY w.id HAVING count(m.id)<>1 OR count(r.membership_id)<>1
    ) THEN
        RAISE EXCEPTION 'Every existing workspace must have exactly one active owner before migration 002; resolve ownership explicitly';
    END IF;
END;
$$;
ALTER TABLE classarit.app_users ADD COLUMN user_type text NOT NULL DEFAULT 'MEMBER'
    CHECK (user_type IN ('MEMBER','OWNER','APPOWNER'));
ALTER TABLE classarit.workspaces ADD COLUMN owner_user_id uuid REFERENCES classarit.app_users(id);
UPDATE classarit.workspaces w SET owner_user_id=m.user_id
FROM classarit.workspace_memberships m JOIN classarit.membership_roles r
ON r.workspace_id=m.workspace_id AND r.membership_id=m.id AND r.role='OWNER'
WHERE m.workspace_id=w.id;
UPDATE classarit.app_users SET user_type='OWNER' WHERE id IN (SELECT owner_user_id FROM classarit.workspaces);
ALTER TABLE classarit.workspaces ALTER COLUMN owner_user_id SET NOT NULL;
CREATE INDEX idx_workspaces_owner ON classarit.workspaces(owner_user_id);
CREATE UNIQUE INDEX uq_one_owner_per_workspace ON classarit.membership_roles(workspace_id) WHERE role='OWNER';
COMMENT ON COLUMN classarit.workspaces.owner_user_id IS 'Single account responsible for future subscription billing; not a charge or subscription record.';
COMMENT ON COLUMN classarit.app_users.user_type IS 'OWNER may also hold teaching/operational membership roles. APPOWNER is exclusive and never a workspace member.';

CREATE FUNCTION classarit.guard_business_account() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE kind text;
BEGIN
    -- Account row locks serialize APPOWNER promotion against membership creation.
    SELECT user_type INTO kind FROM classarit.app_users WHERE id=NEW.user_id FOR UPDATE;
    IF kind='APPOWNER' THEN
        RAISE EXCEPTION 'APPOWNER cannot join a workspace' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_membership_business_account BEFORE INSERT OR UPDATE OF user_id
ON classarit.workspace_memberships FOR EACH ROW EXECUTE FUNCTION classarit.guard_business_account();

CREATE FUNCTION classarit.guard_user_type() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.user_type='APPOWNER' AND NEW.user_type<>'APPOWNER' THEN
        RAISE EXCEPTION 'APPOWNER is a dedicated account and cannot become a business account' USING ERRCODE='23514';
    END IF;
    IF NEW.user_type='APPOWNER' AND (
        EXISTS (SELECT 1 FROM classarit.workspace_memberships WHERE user_id=NEW.id)
        OR EXISTS (SELECT 1 FROM classarit.workspaces WHERE owner_user_id=NEW.id OR created_by=NEW.id)
    ) THEN
        RAISE EXCEPTION 'Use a separate account for APPOWNER; business memberships already exist' USING ERRCODE='23514';
    END IF;
    IF NEW.user_type<>'OWNER' AND EXISTS (SELECT 1 FROM classarit.workspaces WHERE owner_user_id=NEW.id) THEN
        RAISE EXCEPTION 'Workspace subscription owner must have OWNER user type' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_user_type_exclusivity BEFORE UPDATE OF user_type ON classarit.app_users
FOR EACH ROW EXECUTE FUNCTION classarit.guard_user_type();

CREATE FUNCTION classarit.guard_workspace_owner() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE kind text;
BEGIN
    -- Keep the previous deployed app compatible during the rollout: it supplies created_by.
    IF TG_OP='INSERT' AND NEW.owner_user_id IS NULL THEN
        NEW.owner_user_id=NEW.created_by;
        SELECT user_type INTO kind FROM classarit.app_users WHERE id=NEW.owner_user_id FOR UPDATE;
        IF kind='MEMBER' AND NOT EXISTS (SELECT 1 FROM classarit.workspace_memberships WHERE user_id=NEW.owner_user_id) THEN
            UPDATE classarit.app_users SET user_type='OWNER' WHERE id=NEW.owner_user_id;
        END IF;
    END IF;
    SELECT user_type INTO kind FROM classarit.app_users WHERE id=NEW.owner_user_id FOR UPDATE;
    IF kind IS DISTINCT FROM 'OWNER' THEN
        RAISE EXCEPTION 'Workspace requires an OWNER account' USING ERRCODE='23514';
    END IF;
    IF TG_OP='UPDATE' AND NEW.owner_user_id<>OLD.owner_user_id THEN
        RAISE EXCEPTION 'Subscription ownership transfer requires a future dedicated workflow' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_workspace_single_owner BEFORE INSERT OR UPDATE OF owner_user_id ON classarit.workspaces
FOR EACH ROW EXECUTE FUNCTION classarit.guard_workspace_owner();

CREATE FUNCTION classarit.check_workspace_owner_membership() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE wid uuid;
BEGIN
    IF TG_TABLE_NAME='workspaces' THEN
        wid=COALESCE(NEW.id,OLD.id);
    ELSE
        wid=COALESCE(NEW.workspace_id,OLD.workspace_id);
        IF TG_OP='UPDATE' AND NEW.workspace_id<>OLD.workspace_id THEN
            RAISE EXCEPTION 'Membership and role workspace cannot be changed' USING ERRCODE='23514';
        END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM classarit.workspaces WHERE id=wid)
       AND NOT EXISTS (
           SELECT 1 FROM classarit.workspaces w
           JOIN classarit.workspace_memberships m ON m.workspace_id=w.id AND m.user_id=w.owner_user_id AND m.status='ACTIVE'
           JOIN classarit.membership_roles r ON r.workspace_id=m.workspace_id AND r.membership_id=m.id AND r.role='OWNER'
           WHERE w.id=wid
       ) THEN
        RAISE EXCEPTION 'Workspace must retain its single active subscription owner' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END;
$$;
-- Deferred checks allow the workspace, membership and roles to be created atomically.
CREATE CONSTRAINT TRIGGER trg_workspace_owner_consistency AFTER INSERT OR UPDATE ON classarit.workspaces
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION classarit.check_workspace_owner_membership();
CREATE CONSTRAINT TRIGGER trg_membership_owner_consistency AFTER INSERT OR UPDATE OR DELETE ON classarit.workspace_memberships
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION classarit.check_workspace_owner_membership();
CREATE CONSTRAINT TRIGGER trg_role_owner_consistency AFTER INSERT OR UPDATE OR DELETE ON classarit.membership_roles
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION classarit.check_workspace_owner_membership();
COMMIT;
