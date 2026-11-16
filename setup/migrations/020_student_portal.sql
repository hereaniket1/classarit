-- Student accounts and opt-in class discovery. Existing classes stay private.
BEGIN;
DO $$
DECLARE c record;
BEGIN
 FOR c IN SELECT conrelid::regclass AS tbl, conname FROM pg_constraint
 WHERE contype='c' AND ((conrelid='classarit.app_users'::regclass AND pg_get_constraintdef(oid) LIKE '%account_type%')
 OR (conrelid='classarit.interest'::regclass AND pg_get_constraintdef(oid) LIKE '%usage_type%'))
 LOOP EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I',c.tbl,c.conname); END LOOP;
END $$;
ALTER TABLE classarit.app_users ADD CONSTRAINT app_users_account_type_check CHECK (account_type IN ('INDIVIDUAL','ORGANIZATION','STUDENT'));
ALTER TABLE classarit.interest ADD CONSTRAINT interest_usage_type_check CHECK (usage_type IN ('INDIVIDUAL','ORGANIZATION','STUDENT'));
ALTER TABLE classarit.teaching_programs ADD COLUMN student_discoverable boolean NOT NULL DEFAULT false;
CREATE INDEX idx_student_discovery ON classarit.teaching_programs(name,id) WHERE student_discoverable AND status='ACTIVE' AND program_kind='COURSE';
COMMIT;
