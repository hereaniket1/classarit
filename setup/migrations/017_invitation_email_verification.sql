-- Invitation verification is separate from signup and creates no user account.
BEGIN;
ALTER TABLE classarit.interest
 ADD COLUMN email_verified_at timestamptz,
 ADD COLUMN verification_required boolean NOT NULL DEFAULT false,
 ADD COLUMN verification_id uuid,
 ADD COLUMN verification_digest text,
 ADD COLUMN verification_expires_at timestamptz,
 ADD COLUMN verification_attempts integer NOT NULL DEFAULT 0,
 ADD COLUMN verification_sent_at timestamptz,
 ADD COLUMN owner_notified_at timestamptz,
 ADD COLUMN receipt_sent_at timestamptz;
CREATE UNIQUE INDEX interest_verification_id ON classarit.interest(verification_id);
COMMIT;
