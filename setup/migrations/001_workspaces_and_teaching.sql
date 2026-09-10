-- Versioned DDL: apply with setup/apply_migration.py; never run at application startup.
-- 001: workspaces, teaching/coaching, venues, events, attendance and make-ups.
-- Prerequisite: existing classarit.app_users and classarit.set_updated_at().
-- PostgreSQL 14+. This is an additive, one-time migration, not a data import.
-- Does not modify the existing SQLite teaching database or authentication tables.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = classarit, pg_catalog;
DO $$
BEGIN
    IF to_regclass('classarit.app_users') IS NULL
       OR to_regprocedure('classarit.set_updated_at()') IS NULL THEN
        RAISE EXCEPTION 'Install the authentication schema and set_updated_at() dependency first';
    END IF;
END;
$$;

CREATE TABLE classarit.workspaces (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    workspace_type text NOT NULL CHECK (workspace_type IN ('INDIVIDUAL', 'INSTITUTE')),
    created_by uuid NOT NULL REFERENCES classarit.app_users(id),
    timezone text NOT NULL DEFAULT 'Asia/Kolkata',
    currency varchar(3) NOT NULL DEFAULT 'INR' CHECK (currency ~ '^[A-Z]{3}$'),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.workspace_memberships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    user_id uuid NOT NULL REFERENCES classarit.app_users(id),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'SUSPENDED', 'LEFT')),
    joined_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (workspace_id, user_id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_workspace_memberships_user ON classarit.workspace_memberships(user_id);

CREATE TABLE classarit.membership_roles (
    workspace_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    role text NOT NULL CHECK (role IN ('OWNER', 'ADMIN', 'OPERATOR', 'TEACHER')),
    PRIMARY KEY (workspace_id, membership_id, role),
    FOREIGN KEY (workspace_id, membership_id)
        REFERENCES classarit.workspace_memberships(workspace_id, id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.workspace_invitations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    email text NOT NULL CHECK (email = lower(btrim(email)) AND email <> ''),
    invited_by_membership_id uuid NOT NULL,
    proposed_roles text[] NOT NULL CHECK (
        cardinality(proposed_roles) > 0
        AND array_position(proposed_roles, NULL) IS NULL
        AND proposed_roles <@ ARRAY['ADMIN','OPERATOR','TEACHER']::text[]),
    token_hash text NOT NULL UNIQUE CHECK (length(btrim(token_hash)) > 0),
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','ACCEPTED','REVOKED','EXPIRED')),
    expires_at timestamptz NOT NULL,
    accepted_by uuid REFERENCES classarit.app_users(id),
    accepted_at timestamptz,
    FOREIGN KEY (workspace_id, invited_by_membership_id)
        REFERENCES classarit.workspace_memberships(workspace_id, id),
    CHECK (expires_at > created_at),
    CHECK ((status = 'ACCEPTED' AND accepted_by IS NOT NULL AND accepted_at IS NOT NULL)
        OR (status <> 'ACCEPTED' AND accepted_by IS NULL AND accepted_at IS NULL)),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uq_pending_workspace_invitation ON classarit.workspace_invitations(workspace_id, email) WHERE status = 'PENDING';

CREATE TABLE classarit.activities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    category text NOT NULL DEFAULT 'OTHER' CHECK (category IN ('ACADEMIC','ARTS','SPORTS','OTHER')),
    description text,
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uq_workspace_activity_name ON classarit.activities(workspace_id, lower(btrim(name)));

CREATE TABLE classarit.venues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    address text NOT NULL CHECK (length(btrim(address)) > 0),
    directions text,
    map_url text CHECK (map_url IS NULL OR map_url ~ '^https?://'),
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.venue_spaces (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    venue_id uuid NOT NULL,
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    capacity integer CHECK (capacity > 0),
    archived_at timestamptz,
    UNIQUE (workspace_id, venue_id, id),
    FOREIGN KEY (workspace_id, venue_id) REFERENCES classarit.venues(workspace_id, id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uq_venue_space_name ON classarit.venue_spaces(workspace_id, venue_id, lower(btrim(name)));

CREATE TABLE classarit.teaching_programs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    activity_id uuid NOT NULL,
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    program_kind text NOT NULL DEFAULT 'COURSE' CHECK (program_kind IN ('COURSE','EVENT')),
    teaching_format text NOT NULL DEFAULT 'GROUP' CHECK (teaching_format IN ('ONE_TO_ONE','GROUP')),
    level text,
    description text,
    capacity integer NOT NULL CHECK (capacity > 0),
    default_duration_minutes integer NOT NULL DEFAULT 60 CHECK (default_duration_minutes > 0),
    default_delivery_mode text NOT NULL DEFAULT 'ONLINE' CHECK (default_delivery_mode IN ('ONLINE','IN_PERSON','HYBRID')),
    default_meeting_url text CHECK (default_meeting_url IS NULL OR default_meeting_url ~ '^https?://'),
    default_venue_id uuid,
    default_space_id uuid,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','ARCHIVED')),
    FOREIGN KEY (workspace_id, activity_id) REFERENCES classarit.activities(workspace_id, id),
    FOREIGN KEY (workspace_id, default_venue_id) REFERENCES classarit.venues(workspace_id, id),
    FOREIGN KEY (workspace_id, default_venue_id, default_space_id)
        REFERENCES classarit.venue_spaces(workspace_id, venue_id, id),
    CHECK (default_space_id IS NULL OR default_venue_id IS NOT NULL),
    CHECK (teaching_format <> 'ONE_TO_ONE' OR capacity = 1),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.program_teachers (
    workspace_id uuid NOT NULL,
    program_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    assignment_type text NOT NULL DEFAULT 'ASSISTANT' CHECK (assignment_type IN ('LEAD','ASSISTANT')),
    PRIMARY KEY (workspace_id, program_id, membership_id),
    FOREIGN KEY (workspace_id, program_id) REFERENCES classarit.teaching_programs(workspace_id, id),
    FOREIGN KEY (workspace_id, membership_id) REFERENCES classarit.workspace_memberships(workspace_id, id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.students (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    full_name text NOT NULL CHECK (length(btrim(full_name)) > 0),
    email text,
    phone text,
    date_of_birth date,
    notes text,
    linked_user_id uuid REFERENCES classarit.app_users(id),
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ARCHIVED')),
    UNIQUE (workspace_id, linked_user_id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.guardians (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    full_name text NOT NULL CHECK (length(btrim(full_name)) > 0),
    email text,
    phone text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.student_guardians (
    workspace_id uuid NOT NULL,
    student_id uuid NOT NULL,
    guardian_id uuid NOT NULL,
    relationship text NOT NULL,
    is_primary boolean NOT NULL DEFAULT false,
    PRIMARY KEY (workspace_id, student_id, guardian_id),
    FOREIGN KEY (workspace_id, student_id) REFERENCES classarit.students(workspace_id, id),
    FOREIGN KEY (workspace_id, guardian_id) REFERENCES classarit.guardians(workspace_id, id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uq_primary_guardian ON classarit.student_guardians(workspace_id, student_id) WHERE is_primary;

CREATE TABLE classarit.enrollments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    program_id uuid NOT NULL,
    student_id uuid NOT NULL,
    starts_on date NOT NULL,
    ends_on date,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAUSED','COMPLETED','CANCELLED')),
    UNIQUE (workspace_id, program_id, student_id, id),
    FOREIGN KEY (workspace_id, program_id) REFERENCES classarit.teaching_programs(workspace_id, id),
    FOREIGN KEY (workspace_id, student_id) REFERENCES classarit.students(workspace_id, id),
    CHECK (ends_on IS NULL OR ends_on >= starts_on),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uq_current_enrollment ON classarit.enrollments(workspace_id, program_id, student_id) WHERE status IN ('ACTIVE','PAUSED');

CREATE TABLE classarit.class_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    program_id uuid NOT NULL,
    title text,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    session_kind text NOT NULL DEFAULT 'REGULAR' CHECK (session_kind IN ('REGULAR','MAKEUP','EVENT')),
    delivery_mode text NOT NULL CHECK (delivery_mode IN ('ONLINE','IN_PERSON','HYBRID')),
    meeting_url text CHECK (meeting_url IS NULL OR meeting_url ~ '^https?://'),
    venue_id uuid,
    space_id uuid,
    capacity integer NOT NULL CHECK (capacity > 0),
    status text NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED','COMPLETED','CANCELLED')),
    cancellation_reason text,
    cancelled_at timestamptz,
    UNIQUE (workspace_id, program_id, id),
    FOREIGN KEY (workspace_id, program_id) REFERENCES classarit.teaching_programs(workspace_id, id),
    FOREIGN KEY (workspace_id, venue_id) REFERENCES classarit.venues(workspace_id, id),
    FOREIGN KEY (workspace_id, venue_id, space_id) REFERENCES classarit.venue_spaces(workspace_id, venue_id, id),
    CHECK (ends_at > starts_at),
    CHECK (space_id IS NULL OR venue_id IS NOT NULL),
    CHECK ((delivery_mode = 'ONLINE' AND meeting_url IS NOT NULL AND venue_id IS NULL)
        OR (delivery_mode = 'IN_PERSON' AND venue_id IS NOT NULL AND meeting_url IS NULL)
        OR (delivery_mode = 'HYBRID' AND venue_id IS NOT NULL AND meeting_url IS NOT NULL)),
    CHECK (status <> 'CANCELLED' OR cancelled_at IS NOT NULL),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_workspace_session_time ON classarit.class_sessions(workspace_id, starts_at);

CREATE TABLE classarit.session_teachers (
    workspace_id uuid NOT NULL,
    session_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    PRIMARY KEY (workspace_id, session_id, membership_id),
    FOREIGN KEY (workspace_id, session_id) REFERENCES classarit.class_sessions(workspace_id, id),
    FOREIGN KEY (workspace_id, membership_id) REFERENCES classarit.workspace_memberships(workspace_id, id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.session_participants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    program_id uuid NOT NULL,
    session_id uuid NOT NULL,
    student_id uuid NOT NULL,
    enrollment_id uuid,
    participation_kind text NOT NULL DEFAULT 'ENROLLMENT' CHECK (participation_kind IN ('ENROLLMENT','EVENT','MAKEUP')),
    status text NOT NULL DEFAULT 'BOOKED' CHECK (status IN ('BOOKED','CANCELLED')),
    UNIQUE (workspace_id, session_id, student_id),
    UNIQUE (workspace_id, student_id, id),
    FOREIGN KEY (workspace_id, program_id, session_id) REFERENCES classarit.class_sessions(workspace_id, program_id, id),
    FOREIGN KEY (workspace_id, student_id) REFERENCES classarit.students(workspace_id, id),
    FOREIGN KEY (workspace_id, program_id, student_id, enrollment_id)
        REFERENCES classarit.enrollments(workspace_id, program_id, student_id, id),
    CHECK (participation_kind <> 'ENROLLMENT' OR enrollment_id IS NOT NULL),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.attendance (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    participant_id uuid NOT NULL,
    status text NOT NULL CHECK (status IN ('PRESENT','LATE','ABSENT','EXCUSED')),
    marked_by_membership_id uuid NOT NULL,
    marked_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes text,
    UNIQUE (workspace_id, participant_id),
    FOREIGN KEY (workspace_id, participant_id) REFERENCES classarit.session_participants(workspace_id, id),
    FOREIGN KEY (workspace_id, marked_by_membership_id) REFERENCES classarit.workspace_memberships(workspace_id, id),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.makeup_policies (
    workspace_id uuid PRIMARY KEY REFERENCES classarit.workspaces(id),
    teacher_cancellation_eligible boolean NOT NULL DEFAULT true,
    student_absence_eligible boolean NOT NULL DEFAULT false,
    minimum_notice_hours integer NOT NULL DEFAULT 0 CHECK (minimum_notice_hours >= 0),
    validity_days integer CHECK (validity_days > 0),
    included_in_original_fee boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.makeup_entitlements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    student_id uuid NOT NULL,
    original_participant_id uuid NOT NULL,
    reason text NOT NULL CHECK (reason IN ('TEACHER_CANCELLED','VENUE_UNAVAILABLE','WEATHER','STUDENT_ABSENT','OTHER')),
    reason_notes text,
    granted_by_membership_id uuid NOT NULL,
    expires_at timestamptz,
    included_in_original_fee boolean NOT NULL DEFAULT true,
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','FULFILLED','WAIVED','EXPIRED')),
    UNIQUE (workspace_id, original_participant_id),
    UNIQUE (workspace_id, student_id, id),
    FOREIGN KEY (workspace_id, student_id, original_participant_id)
        REFERENCES classarit.session_participants(workspace_id, student_id, id),
    FOREIGN KEY (workspace_id, granted_by_membership_id) REFERENCES classarit.workspace_memberships(workspace_id, id),
    CHECK (expires_at IS NULL OR expires_at > created_at),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classarit.makeup_bookings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES classarit.workspaces(id),
    UNIQUE (workspace_id, id),
    student_id uuid NOT NULL,
    entitlement_id uuid NOT NULL,
    replacement_participant_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'BOOKED' CHECK (status IN ('BOOKED','FULFILLED','CANCELLED','NO_SHOW')),
    fulfilled_at timestamptz,
    cancelled_at timestamptz,
    FOREIGN KEY (workspace_id, student_id, entitlement_id)
        REFERENCES classarit.makeup_entitlements(workspace_id, student_id, id),
    FOREIGN KEY (workspace_id, student_id, replacement_participant_id)
        REFERENCES classarit.session_participants(workspace_id, student_id, id),
    CHECK ((status = 'FULFILLED') = (fulfilled_at IS NOT NULL)),
    CHECK (status <> 'CANCELLED' OR cancelled_at IS NOT NULL),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX uq_committed_makeup_booking ON classarit.makeup_bookings(workspace_id, entitlement_id) WHERE status IN ('BOOKED','FULFILLED');

CREATE UNIQUE INDEX uq_replacement_makeup_credit ON classarit.makeup_bookings(workspace_id, replacement_participant_id) WHERE status IN ('BOOKED','FULFILLED');

-- Keep staff calendars and student history queries efficient.
CREATE INDEX idx_program_teachers_member ON classarit.program_teachers(workspace_id, membership_id);
CREATE INDEX idx_session_teachers_member ON classarit.session_teachers(workspace_id, membership_id);
CREATE INDEX idx_student_enrollments ON classarit.enrollments(workspace_id, student_id);
CREATE INDEX idx_student_sessions ON classarit.session_participants(workspace_id, student_id);
CREATE INDEX idx_student_makeup_entitlements ON classarit.makeup_entitlements(workspace_id, student_id, status);

CREATE TRIGGER trg_workspaces_updated_at BEFORE UPDATE ON classarit.workspaces
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_workspace_memberships_updated_at BEFORE UPDATE ON classarit.workspace_memberships
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_workspace_invitations_updated_at BEFORE UPDATE ON classarit.workspace_invitations
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_activities_updated_at BEFORE UPDATE ON classarit.activities
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_venues_updated_at BEFORE UPDATE ON classarit.venues
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_venue_spaces_updated_at BEFORE UPDATE ON classarit.venue_spaces
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_teaching_programs_updated_at BEFORE UPDATE ON classarit.teaching_programs
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_students_updated_at BEFORE UPDATE ON classarit.students
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_guardians_updated_at BEFORE UPDATE ON classarit.guardians
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_enrollments_updated_at BEFORE UPDATE ON classarit.enrollments
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_class_sessions_updated_at BEFORE UPDATE ON classarit.class_sessions
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_session_participants_updated_at BEFORE UPDATE ON classarit.session_participants
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_attendance_updated_at BEFORE UPDATE ON classarit.attendance
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_makeup_policies_updated_at BEFORE UPDATE ON classarit.makeup_policies
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_makeup_entitlements_updated_at BEFORE UPDATE ON classarit.makeup_entitlements
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

CREATE TRIGGER trg_makeup_bookings_updated_at BEFORE UPDATE ON classarit.makeup_bookings
    FOR EACH ROW EXECUTE FUNCTION classarit.set_updated_at();

-- Application transactions must enforce: active membership/roles, last-owner
-- protection, capacity/conflict checks, roster eligibility, and make-up state transitions.
-- The composite foreign keys prevent cross-workspace and cross-student links;
-- they are not a substitute for authorization on reads or writes.
COMMIT;
