-- Preserve planner occurrences while giving each creation batch a stable group.
BEGIN;
ALTER TABLE classarit.student_planner_tasks
    ADD COLUMN series_id uuid NOT NULL DEFAULT gen_random_uuid(),
    ADD COLUMN recurrence jsonb NOT NULL DEFAULT '{}';

WITH groups AS (
    SELECT student_user_id, created_at, title, timezone, location, notes,
           ends_at - starts_at AS duration, min(id::text)::uuid AS series_id
    FROM classarit.student_planner_tasks
    GROUP BY student_user_id, created_at, title, timezone, location, notes, ends_at - starts_at
)
UPDATE classarit.student_planner_tasks task
SET series_id = groups.series_id
FROM groups
WHERE task.student_user_id = groups.student_user_id AND task.created_at = groups.created_at
  AND task.title = groups.title AND task.timezone = groups.timezone
  AND task.location IS NOT DISTINCT FROM groups.location
  AND task.notes IS NOT DISTINCT FROM groups.notes
  AND task.ends_at - task.starts_at = groups.duration;

CREATE INDEX idx_student_planner_series ON classarit.student_planner_tasks(student_user_id, series_id);
COMMIT;
