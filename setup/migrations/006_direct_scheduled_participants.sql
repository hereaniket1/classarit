-- 006: allow students selected directly while scheduling a class.
-- DIRECT means the student is booked into this scheduled session or generated series
-- without creating a long-running class enrollment.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;
LOCK TABLE classarit.session_participants IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE classarit.session_participants
    DROP CONSTRAINT session_participants_participation_kind_check;

ALTER TABLE classarit.session_participants
    ADD CONSTRAINT session_participants_participation_kind_check
    CHECK (participation_kind IN ('ENROLLMENT','EVENT','MAKEUP','DIRECT'));

COMMENT ON COLUMN classarit.session_participants.participation_kind IS
    'ENROLLMENT comes from class enrollment, EVENT is an event booking, MAKEUP is a replacement booking, DIRECT is selected during schedule creation.';
COMMIT;
