-- 009: Owner may also teach; Admin, Operator and Teacher are exclusive staff roles.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;
LOCK TABLE classarit.workspace_memberships, classarit.membership_roles, classarit.workspace_invitations IN SHARE ROW EXCLUSIVE MODE;

CREATE FUNCTION classarit.validate_membership_role_exclusivity(
    p_workspace uuid,
    p_membership uuid
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    roles text[];
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM classarit.workspace_memberships
        WHERE workspace_id=p_workspace AND id=p_membership
    ) THEN
        RETURN;
    END IF;

    SELECT COALESCE(array_agg(role ORDER BY role), ARRAY[]::text[])
      INTO roles
      FROM classarit.membership_roles
     WHERE workspace_id=p_workspace AND membership_id=p_membership;

    IF 'OWNER'=ANY(roles) THEN
        IF NOT (roles <@ ARRAY['OWNER','TEACHER']::text[]) THEN
            RAISE EXCEPTION 'Owner may additionally hold the Teacher role only'
                USING ERRCODE='23514';
        END IF;
    ELSIF cardinality(roles) <> 1
       OR NOT (roles <@ ARRAY['ADMIN','OPERATOR','TEACHER']::text[]) THEN
        RAISE EXCEPTION 'Choose exactly one staff role: Admin, Operator or Teacher'
            USING ERRCODE='23514';
    END IF;
END;
$$;

DO $$
DECLARE row record;
BEGIN
    FOR row IN
        SELECT workspace_id,id FROM classarit.workspace_memberships
    LOOP
        PERFORM classarit.validate_membership_role_exclusivity(row.workspace_id,row.id);
    END LOOP;
    IF EXISTS (
        SELECT 1 FROM classarit.workspace_invitations
        WHERE status='PENDING' AND cardinality(proposed_roles) <> 1
    ) THEN
        RAISE EXCEPTION 'Resolve pending invitations with multiple roles before migration 009';
    END IF;
END;
$$;

CREATE FUNCTION classarit.check_membership_role_exclusivity()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM classarit.validate_membership_role_exclusivity(
        COALESCE(NEW.workspace_id,OLD.workspace_id),
        COALESCE(NEW.membership_id,OLD.membership_id)
    );
    IF TG_OP='UPDATE'
       AND (NEW.workspace_id,NEW.membership_id)
           IS DISTINCT FROM (OLD.workspace_id,OLD.membership_id) THEN
        PERFORM classarit.validate_membership_role_exclusivity(
            OLD.workspace_id,OLD.membership_id
        );
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER trg_membership_role_exclusivity
AFTER INSERT OR UPDATE OR DELETE ON classarit.membership_roles
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION classarit.check_membership_role_exclusivity();

CREATE FUNCTION classarit.guard_invitation_role_exclusivity()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF cardinality(NEW.proposed_roles) <> 1 THEN
        RAISE EXCEPTION 'Choose exactly one invitation role: Admin, Operator or Teacher'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_invitation_role_exclusivity
BEFORE INSERT OR UPDATE OF proposed_roles ON classarit.workspace_invitations
FOR EACH ROW EXECUTE FUNCTION classarit.guard_invitation_role_exclusivity();

COMMENT ON FUNCTION classarit.validate_membership_role_exclusivity(uuid,uuid) IS
'Owner may also teach. Admin, Operator and Teacher are mutually exclusive staff roles.';
COMMIT;
