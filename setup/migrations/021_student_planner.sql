-- Personal student planner tasks are independent of workspaces and teaching classes.
BEGIN;
CREATE TABLE classarit.student_planner_tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    student_user_id uuid NOT NULL REFERENCES classarit.app_users(id) ON DELETE CASCADE,
    title text NOT NULL CHECK (length(btrim(title)) BETWEEN 1 AND 200),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    timezone text NOT NULL DEFAULT 'Asia/Kolkata',
    location text,
    notes text,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','COMPLETED','CANCELLED')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (ends_at > starts_at)
);
CREATE INDEX idx_student_planner_tasks_time ON classarit.student_planner_tasks(student_user_id,starts_at) WHERE status='ACTIVE';
COMMIT;
