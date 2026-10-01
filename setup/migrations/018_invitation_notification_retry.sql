-- Persist review-link origin so failed owner notifications can be retried.
BEGIN;
ALTER TABLE classarit.interest ADD COLUMN notification_base_url text;
COMMIT;
