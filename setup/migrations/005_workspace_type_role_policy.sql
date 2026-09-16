-- 005: role rules depend on workspace type.
-- Individual practices use OWNER + TEACHER for the owner and Teacher-only staff.
-- Institutes may use Admin, Operator and Teacher staff roles.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;
LOCK TABLE classarit.workspaces, classarit.workspace_memberships, classarit.membership_roles, classarit.workspace_invitations IN SHARE ROW EXCLUSIVE MODE;

CREATE FUNCTION classarit.validate_workspace_type_role_policy(p_workspace uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE kind text;
BEGIN
    SELECT workspace_type INTO kind FROM classarit.workspaces WHERE id=p_workspace;
    IF kind IS NULL THEN
        RETURN;
    END IF;
    IF kind='INDIVIDUAL' THEN
        IF EXISTS (
            SELECT 1
            FROM classarit.membership_roles
            WHERE workspace_id=p_workspace
              AND role IN ('ADMIN','OPERATOR')
        ) THEN
            RAISE EXCEPTION 'Individual practices can only use Teacher as an operational staff role' USING ERRCODE='23514';
        END IF;
        IF EXISTS (
            SELECT 1
            FROM classarit.workspaces w
            JOIN classarit.workspace_memberships m
              ON m.workspace_id=w.id
             AND m.user_id=w.owner_user_id
             AND m.status='ACTIVE'
            JOIN classarit.membership_roles owner_role
              ON owner_role.workspace_id=m.workspace_id
             AND owner_role.membership_id=m.id
             AND owner_role.role='OWNER'
            WHERE w.id=p_workspace
              AND NOT EXISTS (
                  SELECT 1
                  FROM classarit.membership_roles teacher_role
                  WHERE teacher_role.workspace_id=m.workspace_id
                    AND teacher_role.membership_id=m.id
                    AND teacher_role.role='TEACHER'
              )
        ) THEN
            RAISE EXCEPTION 'Individual practice owner must remain a Teacher' USING ERRCODE='23514';
        END IF;
    END IF;
END;
$$;

DO $$
DECLARE row record;
BEGIN
    FOR row IN SELECT id FROM classarit.workspaces LOOP
        PERFORM classarit.validate_workspace_type_role_policy(row.id);
    END LOOP;
    IF EXISTS (
        SELECT 1
        FROM classarit.workspace_invitations i
        JOIN classarit.workspaces w ON w.id=i.workspace_id
        WHERE w.workspace_type='INDIVIDUAL'
          AND i.status='PENDING'
          AND NOT (i.proposed_roles <@ ARRAY['TEACHER']::text[])
    ) THEN
        RAISE EXCEPTION 'Resolve pending Admin/Operator invitations for individual practices before migration 005';
    END IF;
END;
$$;

CREATE FUNCTION classarit.check_workspace_type_role_policy() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE wid uuid;
BEGIN
    IF TG_TABLE_NAME='workspaces' THEN
        wid=COALESCE(NEW.id, OLD.id);
    ELSE
        wid=COALESCE(NEW.workspace_id, OLD.workspace_id);
    END IF;
    PERFORM classarit.validate_workspace_type_role_policy(wid);
    IF TG_OP='UPDATE' AND TG_TABLE_NAME IN ('membership_roles','workspace_memberships') THEN
        IF NEW.workspace_id IS DISTINCT FROM OLD.workspace_id THEN
            PERFORM classarit.validate_workspace_type_role_policy(OLD.workspace_id);
        END IF;
    END IF;
    RETURN NULL;
END;
$$;

CREATE FUNCTION classarit.guard_workspace_invitation_role_policy() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE kind text;
BEGIN
    SELECT workspace_type INTO kind FROM classarit.workspaces WHERE id=NEW.workspace_id;
    IF kind='INDIVIDUAL' AND NOT (NEW.proposed_roles <@ ARRAY['TEACHER']::text[]) THEN
        RAISE EXCEPTION 'Individual practices can invite teachers only' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER trg_workspace_type_role_policy_workspace
AFTER INSERT OR UPDATE OF workspace_type ON classarit.workspaces
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION classarit.check_workspace_type_role_policy();

CREATE CONSTRAINT TRIGGER trg_workspace_type_role_policy_membership
AFTER INSERT OR UPDATE OF workspace_id, status OR DELETE ON classarit.workspace_memberships
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION classarit.check_workspace_type_role_policy();

CREATE CONSTRAINT TRIGGER trg_workspace_type_role_policy_role
AFTER INSERT OR UPDATE OR DELETE ON classarit.membership_roles
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION classarit.check_workspace_type_role_policy();

CREATE TRIGGER trg_workspace_invitation_role_policy
BEFORE INSERT OR UPDATE OF workspace_id, proposed_roles ON classarit.workspace_invitations
FOR EACH ROW EXECUTE FUNCTION classarit.guard_workspace_invitation_role_policy();

COMMENT ON FUNCTION classarit.validate_workspace_type_role_policy(uuid) IS 'Individual practices keep the owner as OWNER+TEACHER and allow Teacher-only staff; institutes may use Admin, Operator and Teacher.';
COMMIT;
