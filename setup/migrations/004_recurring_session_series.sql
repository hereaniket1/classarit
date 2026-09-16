-- 004: recurring schedule series metadata for grouping generated sessions.
-- Apply after 003. This stores generated occurrences as normal class_sessions
-- while retaining enough series metadata to render the repeat as one row.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;
LOCK TABLE classarit.workspaces, classarit.teaching_programs, classarit.workspace_memberships, classarit.class_sessions IN SHARE ROW EXCLUSIVE MODE;

CREATE TABLE classarit.recurring_session_series (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    program_id uuid NOT NULL,
    title text,
    start_date date NOT NULL,
    start_time time NOT NULL,
    duration_minutes integer NOT NULL CHECK (duration_minutes > 0 AND duration_minutes <= 1440),
    repeat_weekdays text[] NOT NULL CHECK (
        cardinality(repeat_weekdays) BETWEEN 1 AND 7
        AND repeat_weekdays <@ ARRAY['MON','TUE','WED','THU','FRI','SAT','SUN']::text[]
    ),
    repeat_months integer NOT NULL CHECK (repeat_months BETWEEN 1 AND 24),
    delivery_mode text NOT NULL CHECK (delivery_mode IN ('ONLINE','IN_PERSON','HYBRID')),
    meeting_url text,
    venue_id uuid,
    space_id uuid,
    capacity integer NOT NULL CHECK (capacity > 0),
    created_by_membership_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ARCHIVED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id, program_id) REFERENCES classarit.teaching_programs(workspace_id, id),
    FOREIGN KEY (workspace_id, venue_id) REFERENCES classarit.venues(workspace_id, id),
    FOREIGN KEY (workspace_id, venue_id, space_id) REFERENCES classarit.venue_spaces(workspace_id, venue_id, id),
    FOREIGN KEY (workspace_id, created_by_membership_id) REFERENCES classarit.workspace_memberships(workspace_id, id),
    CHECK (space_id IS NULL OR venue_id IS NOT NULL)
);

CREATE INDEX idx_recurring_session_series_workspace ON classarit.recurring_session_series(workspace_id, status, start_date);

ALTER TABLE classarit.class_sessions
    ADD COLUMN recurring_series_id uuid,
    ADD COLUMN series_original_starts_at timestamptz,
    ADD COLUMN edited_from_series boolean NOT NULL DEFAULT false,
    ADD COLUMN series_edited_at timestamptz,
    ADD CONSTRAINT fk_class_sessions_recurring_series
        FOREIGN KEY (workspace_id, recurring_series_id)
        REFERENCES classarit.recurring_session_series(workspace_id, id),
    ADD CONSTRAINT chk_class_sessions_series_original
        CHECK (recurring_series_id IS NULL OR series_original_starts_at IS NOT NULL),
    ADD CONSTRAINT chk_class_sessions_series_edited_at
        CHECK ((edited_from_series = false AND series_edited_at IS NULL) OR recurring_series_id IS NOT NULL);

CREATE INDEX idx_class_sessions_recurring_series ON classarit.class_sessions(workspace_id, recurring_series_id, edited_from_series, starts_at);

CREATE TRIGGER trg_recurring_session_series_updated_at BEFORE UPDATE ON classarit.recurring_session_series
FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();
COMMIT;
