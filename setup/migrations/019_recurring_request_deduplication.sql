-- Persist request identity for safe retries of recurring schedule creation.
BEGIN;
ALTER TABLE classarit.recurring_session_series ADD COLUMN client_request_id uuid,
    ADD COLUMN request_hash text;
CREATE UNIQUE INDEX recurring_series_client_request ON classarit.recurring_session_series(workspace_id,client_request_id);
COMMIT;
