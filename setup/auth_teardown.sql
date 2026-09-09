-- DESTRUCTIVE: permanently removes all rows in the five authentication tables.
-- Scope: only the authentication schema defined in auth_schema.sql.
-- Review the target database and take a backup before executing.
-- Run: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f setup/auth_teardown.sql
-- Not a teardown for all application/business tables.

BEGIN;
SET LOCAL lock_timeout = '5s';

-- Children first. RESTRICT intentionally blocks unexpected dependencies,
-- including business tables referencing app_users. No CASCADE is used.
DROP TABLE IF EXISTS classarit.auth_sessions RESTRICT;
DROP TABLE IF EXISTS classarit.auth_challenges RESTRICT;
DROP TABLE IF EXISTS classarit.password_credentials RESTRICT;
DROP TABLE IF EXISTS classarit.auth_identities RESTRICT;
DROP TABLE IF EXISTS classarit.user_emails RESTRICT;
DROP TABLE IF EXISTS classarit.app_users RESTRICT;

-- Table-owned indexes, constraints and triggers are removed automatically.
-- Keep classarit.set_updated_at() and the citext extension: other tables may use them.
COMMIT;
