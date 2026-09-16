-- 007: account default workspace preference for direct post-login workspace entry.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;
LOCK TABLE classarit.app_users, classarit.workspaces, classarit.workspace_memberships IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE classarit.app_users
    ADD COLUMN default_workspace_id uuid;

ALTER TABLE classarit.app_users
    ADD CONSTRAINT fk_app_users_default_workspace
    FOREIGN KEY (default_workspace_id) REFERENCES classarit.workspaces(id)
    ON DELETE SET NULL;

UPDATE classarit.app_users u
SET default_workspace_id=choice.workspace_id
FROM (
    SELECT DISTINCT ON (m.user_id) m.user_id, m.workspace_id
    FROM classarit.workspace_memberships m
    JOIN classarit.workspaces w ON w.id=m.workspace_id AND w.status='ACTIVE'
    WHERE m.status='ACTIVE'
    ORDER BY m.user_id, w.created_at, w.id
) choice
WHERE choice.user_id=u.id
  AND u.default_workspace_id IS NULL;

COMMENT ON COLUMN classarit.app_users.default_workspace_id IS
    'Preferred active workspace opened from /dashboard and after login when the account still has access.';
COMMIT;
