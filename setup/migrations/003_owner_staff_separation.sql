-- 003: keep subscription-owner accounts separate from active staff accounts.
-- Apply after 002. OWNER may own multiple workspaces, but the same email/account
-- cannot also be active staff in a workspace it does not own.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;
LOCK TABLE classarit.workspaces, classarit.workspace_memberships, classarit.membership_roles, classarit.app_users IN SHARE ROW EXCLUSIVE MODE;

CREATE FUNCTION classarit.validate_owner_staff_separation(p_user uuid) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF p_user IS NULL THEN
        RETURN;
    END IF;
    IF (
        EXISTS (SELECT 1 FROM classarit.app_users WHERE id=p_user AND user_type='OWNER')
        OR EXISTS (SELECT 1 FROM classarit.workspaces WHERE owner_user_id=p_user)
    ) AND EXISTS (
        SELECT 1
        FROM classarit.workspace_memberships m
        WHERE m.user_id=p_user
          AND m.status='ACTIVE'
          AND NOT EXISTS (
              SELECT 1
              FROM classarit.membership_roles r
              WHERE r.workspace_id=m.workspace_id
                AND r.membership_id=m.id
                AND r.role='OWNER'
          )
    ) THEN
        RAISE EXCEPTION 'Deactivate staff memberships before using this account as an owner' USING ERRCODE='23514';
    END IF;
END;
$$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM classarit.app_users u
        WHERE (
            u.user_type='OWNER'
            OR EXISTS (SELECT 1 FROM classarit.workspaces w WHERE w.owner_user_id=u.id)
        ) AND EXISTS (
            SELECT 1
            FROM classarit.workspace_memberships m
            WHERE m.user_id=u.id
              AND m.status='ACTIVE'
              AND NOT EXISTS (
                  SELECT 1
                  FROM classarit.membership_roles r
                  WHERE r.workspace_id=m.workspace_id
                    AND r.membership_id=m.id
                    AND r.role='OWNER'
              )
        )
    ) THEN
        RAISE EXCEPTION 'Resolve existing owner/staff mixed accounts before migration 003';
    END IF;
END;
$$;

CREATE FUNCTION classarit.check_app_user_owner_staff_separation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM classarit.validate_owner_staff_separation(NEW.id);
    RETURN NULL;
END;
$$;

CREATE FUNCTION classarit.check_workspace_owner_staff_separation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM classarit.validate_owner_staff_separation(NEW.owner_user_id);
    IF TG_OP='UPDATE' AND NEW.owner_user_id IS DISTINCT FROM OLD.owner_user_id THEN
        PERFORM classarit.validate_owner_staff_separation(OLD.owner_user_id);
    END IF;
    RETURN NULL;
END;
$$;

CREATE FUNCTION classarit.check_membership_owner_staff_separation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE uid uuid;
BEGIN
    uid=COALESCE(NEW.user_id, OLD.user_id);
    PERFORM classarit.validate_owner_staff_separation(uid);
    IF TG_OP='UPDATE' AND NEW.user_id IS DISTINCT FROM OLD.user_id THEN
        PERFORM classarit.validate_owner_staff_separation(OLD.user_id);
    END IF;
    RETURN NULL;
END;
$$;

CREATE FUNCTION classarit.check_role_owner_staff_separation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE uid uuid;
BEGIN
    SELECT m.user_id INTO uid
    FROM classarit.workspace_memberships m
    WHERE m.workspace_id=COALESCE(NEW.workspace_id, OLD.workspace_id)
      AND m.id=COALESCE(NEW.membership_id, OLD.membership_id);
    PERFORM classarit.validate_owner_staff_separation(uid);
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER trg_app_user_owner_staff_separation
AFTER INSERT OR UPDATE OF user_type ON classarit.app_users
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION classarit.check_app_user_owner_staff_separation();

CREATE CONSTRAINT TRIGGER trg_workspace_owner_staff_separation
AFTER INSERT OR UPDATE OF owner_user_id ON classarit.workspaces
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION classarit.check_workspace_owner_staff_separation();

CREATE CONSTRAINT TRIGGER trg_membership_owner_staff_separation
AFTER INSERT OR UPDATE OF user_id, status ON classarit.workspace_memberships
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION classarit.check_membership_owner_staff_separation();

CREATE CONSTRAINT TRIGGER trg_role_owner_staff_separation
AFTER INSERT OR UPDATE OR DELETE ON classarit.membership_roles
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION classarit.check_role_owner_staff_separation();

COMMENT ON FUNCTION classarit.validate_owner_staff_separation(uuid) IS 'OWNER accounts can own one or more workspaces, but cannot also be active non-owner staff. Deactivate staff memberships before ownership.';
COMMIT;
