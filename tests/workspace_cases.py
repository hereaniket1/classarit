"""Behavioral cases run against LoginTests' isolated PostgreSQL fixture."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import uuid4


class WorkspaceCases:
    def ws_setup(self, workspace_type="INDIVIDUAL"):
        csrf = self.login()
        self.headers = {"X-CSRF-Token": csrf}
        r = self.client.post(
            "/api/workspaces",
            headers=self.headers,
            json={"name": "Music studio", "workspace_type": workspace_type},
        )
        self.assertEqual(r.status_code, 201, r.text)
        self.w = r.json()["id"]
        self.base = "/api/workspaces/" + self.w
        return self.w

    def post(self, path, data, code=201):
        r = self.client.post(self.base + path, headers=self.headers, json=data)
        self.assertEqual(r.status_code, code, r.text)
        return r.json()

    def new_program(self, name="Piano", **extra):
        return self.post(
            "/programs",
            {
                "name": name,
                "activity_name": "Piano",
                "default_meeting_url": "https://meet.example.com/piano",
                **extra,
            },
        )

    def new_session(self, program, days=2, **extra):
        return self.post(
            "/sessions",
            {
                "program_id": program["id"],
                "starts_at": (
                    datetime.now(timezone.utc) + timedelta(days=days)
                ).isoformat(),
                **extra,
            },
        )

    def test_workspace_calendar_month_api(self):
        self.ws_setup()
        prog = self.new_program()
        start = datetime.now(timezone.utc) + timedelta(days=10)
        session = self.post(
            "/sessions",
            {
                "program_id": prog["id"],
                "starts_at": start.isoformat(),
            },
        )
        data = self.client.get(
            self.base + "/calendar?month=" + start.strftime("%Y-%m")
        ).json()
        self.assertEqual(data["month"], start.strftime("%Y-%m"))
        self.assertEqual([s["id"] for s in data["sessions"]], [session["id"]])
        self.assertEqual(self.client.get(self.base + "/calendar?month=bad").status_code, 422)
        calendar_default = self.client.get(self.base + "/section/calendar")
        self.assertEqual(calendar_default.status_code, 200, calendar_default.text)
        self.assertRegex(calendar_default.json()["calendar"]["month"], r"^\d{4}-\d{2}$")
        calendar_section = self.client.get(
            self.base + "/section/calendar?month=" + start.strftime("%Y-%m")
        )
        self.assertEqual(calendar_section.status_code, 200, calendar_section.text)
        payload = calendar_section.json()
        self.assertEqual(payload["calendar"]["month"], start.strftime("%Y-%m"))
        self.assertEqual([s["id"] for s in payload["sessions"]], [session["id"]])
        self.assertEqual(payload["participants"], [])
        classes_section = self.client.get(self.base + "/section/classes")
        self.assertEqual(classes_section.status_code, 200, classes_section.text)
        self.assertEqual([p["id"] for p in classes_section.json()["programs"]], [prog["id"]])
        self.assertEqual(classes_section.json()["sessions"], [])
        self.assertEqual(self.client.get(self.base + "/section/not-real").status_code, 404)


    def test_schedule_can_add_students_directly(self):
        self.ws_setup()
        prog = self.new_program(capacity=2)
        student = self.post("/students", {"full_name": "Direct student"})
        calendar_payload = self.client.get(self.base + "/section/calendar")
        self.assertEqual(calendar_payload.status_code, 200, calendar_payload.text)
        self.assertEqual(
            [row["id"] for row in calendar_payload.json()["students"]],
            [student["id"]],
        )
        start = datetime.now(timezone.utc) + timedelta(days=3)
        session = self.post(
            "/sessions",
            {
                "program_id": prog["id"],
                "starts_at": start.isoformat(),
                "student_ids": [student["id"]],
            },
        )
        snap = self.client.get(self.base + "/snapshot").json()
        participant = next(
            row
            for row in snap["participants"]
            if row["session_id"] == session["id"] and row["student_id"] == student["id"]
        )
        self.assertEqual(participant["participation_kind"], "DIRECT")
        self.assertIsNone(participant["enrollment_id"])
        duplicate = self.client.post(
            self.base + "/sessions",
            headers=self.headers,
            json={
                "program_id": prog["id"],
                "starts_at": (start + timedelta(minutes=30)).isoformat(),
                "student_ids": [student["id"]],
            },
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)

        small_group = self.new_program("Small group", capacity=1)
        second_student = self.post("/students", {"full_name": "Second direct student"})
        over_capacity = self.client.post(
            self.base + "/sessions",
            headers=self.headers,
            json={
                "program_id": small_group["id"],
                "starts_at": (start + timedelta(days=2)).isoformat(),
                "student_ids": [student["id"], second_student["id"]],
            },
        )
        self.assertEqual(over_capacity.status_code, 409, over_capacity.text)
        self.assertIn("2 students would be booked", over_capacity.text)
        roomier = self.client.post(
            self.base + "/sessions",
            headers=self.headers,
            json={
                "program_id": small_group["id"],
                "starts_at": (start + timedelta(days=2)).isoformat(),
                "student_ids": [student["id"], second_student["id"]],
                "capacity": 2,
            },
        )
        self.assertEqual(roomier.status_code, 201, roomier.text)

        event = self.new_program("Workshop", program_kind="EVENT")
        event_student = self.post("/students", {"full_name": "Event student"})
        event_session = self.post(
            "/sessions",
            {
                "program_id": event["id"],
                "starts_at": (start + timedelta(days=1)).isoformat(),
                "student_ids": [event_student["id"]],
            },
        )
        snap = self.client.get(self.base + "/snapshot").json()
        participant = next(
            row
            for row in snap["participants"]
            if row["session_id"] == event_session["id"]
            and row["student_id"] == event_student["id"]
        )
        self.assertEqual(participant["participation_kind"], "EVENT")


    def test_recurring_weekly_schedule_generates_selected_days(self):
        self.ws_setup()
        prog = self.new_program(default_duration_minutes=60)
        student = self.post("/students", {"full_name": "Recurring student"})
        start = date.today() + timedelta(days=7)
        second_day = start + timedelta(days=2)
        weekday_keys = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        repeat_days = [weekday_keys[start.weekday()], weekday_keys[second_day.weekday()]]
        from app.workspaces.services.scheduling import recurring_dates

        expected_dates = recurring_dates(start, 2, repeat_days)
        response = self.client.post(
            self.base + "/sessions/recurring",
            headers=self.headers,
            json={
                "program_id": prog["id"],
                "start_date": start.isoformat(),
                "start_time": "09:30",
                "duration_minutes": 45,
                "student_ids": [student["id"]],
                "repeat_weekdays": repeat_days,
                "repeat_months": 2,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()
        self.assertEqual(data["count"], len(expected_dates))
        self.assertGreaterEqual(data["count"], 8)
        snap = self.client.get(self.base + "/snapshot").json()
        local_dates = sorted(
            datetime.fromisoformat(session["starts_at"]).astimezone(ZoneInfo("Asia/Kolkata")).date()
            for session in snap["sessions"]
            if session["program_id"] == prog["id"]
        )
        self.assertEqual(local_dates, expected_dates)
        direct = [
            row
            for row in snap["participants"]
            if row["student_id"] == student["id"]
            and row["participation_kind"] == "DIRECT"
        ]
        self.assertEqual(len(direct), len(expected_dates))
        self.assertEqual(len(snap["recurring_series"]), 1)
        series_id = snap["recurring_series"][0]["id"]
        for session in snap["sessions"]:
            if session["program_id"] == prog["id"]:
                self.assertEqual(session["recurring_series_id"], series_id)
                self.assertFalse(session["edited_from_series"])
                start_at = datetime.fromisoformat(session["starts_at"])
                ends_at = datetime.fromisoformat(session["ends_at"])
                self.assertEqual(ends_at - start_at, timedelta(minutes=45))
        renamed = self.client.patch(
            self.base + "/recurring-series/" + series_id,
            headers=self.headers,
            json={"title": "Fall piano"},
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        snap = self.client.get(self.base + "/snapshot").json()
        self.assertEqual(snap["recurring_series"][0]["title"], "Fall piano")
        self.assertTrue(
            all(
                row["title"] == "Fall piano"
                for row in snap["sessions"]
                if row["recurring_series_id"] == series_id
            )
        )
        target = sorted(snap["sessions"], key=lambda row: row["starts_at"])[0]
        moved_start = datetime.fromisoformat(target["starts_at"]) + timedelta(hours=3)
        moved = self.client.patch(
            self.base + "/sessions/" + target["id"],
            headers=self.headers,
            json={
                "starts_at": moved_start.isoformat(),
                "ends_at": (moved_start + timedelta(minutes=45)).isoformat(),
                "delivery_mode": "ONLINE",
                "meeting_url": "https://meet.example.com/piano",
            },
        )
        self.assertEqual(moved.status_code, 200, moved.text)
        edited = next(
            row
            for row in self.client.get(self.base + "/snapshot").json()["sessions"]
            if row["id"] == target["id"]
        )
        self.assertTrue(edited["edited_from_series"])
        self.assertTrue(edited["title"].endswith(" - Edited"))
        retry = self.client.post(
            self.base + "/sessions/recurring",
            headers=self.headers,
            json={
                "program_id": prog["id"],
                "start_date": start.isoformat(),
                "start_time": "09:30",
                "duration_minutes": 45,
                "repeat_weekdays": repeat_days,
                "repeat_months": 2,
            },
        )
        self.assertEqual(retry.status_code, 409, retry.text)
        self.assertEqual(
            len(self.client.get(self.base + "/snapshot").json()["sessions"]),
            len(expected_dates),
        )
        disabled = self.client.post(
            self.base + "/recurring-series/" + series_id + "/disable",
            headers=self.headers,
        )
        self.assertEqual(disabled.status_code, 200, disabled.text)
        self.assertEqual(disabled.json()["cancelled_count"], len(expected_dates) - 1)
        snap = self.client.get(self.base + "/snapshot").json()
        self.assertEqual(snap["recurring_series"][0]["status"], "ARCHIVED")
        edited = [row for row in snap["sessions"] if row["edited_from_series"]]
        standard = [row for row in snap["sessions"] if row["recurring_series_id"] == series_id and not row["edited_from_series"]]
        self.assertEqual(len(edited), 1)
        self.assertEqual(edited[0]["status"], "SCHEDULED")
        self.assertTrue(all(row["status"] == "CANCELLED" for row in standard))
        active_section = self.client.get(self.base + "/section/sessions")
        self.assertEqual(active_section.status_code, 200, active_section.text)
        self.assertFalse(active_section.json()["history_included"])
        self.assertEqual(
            [row["id"] for row in active_section.json()["sessions"]],
            [edited[0]["id"]],
        )
        history_section = self.client.get(self.base + "/section/sessions?history=1")
        self.assertEqual(history_section.status_code, 200, history_section.text)
        self.assertTrue(history_section.json()["history_included"])
        self.assertEqual(len(history_section.json()["sessions"]), len(expected_dates))
        self.assertTrue(any(row["status"] == "CANCELLED" for row in history_section.json()["sessions"]))
        calendar = self.client.get(
            self.base + "/calendar?month=" + moved_start.strftime("%Y-%m")
        ).json()
        self.assertEqual([row["id"] for row in calendar["sessions"]], [edited[0]["id"]])
        restored = self.client.post(
            self.base + "/recurring-series/" + series_id + "/restore",
            headers=self.headers,
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["restored_count"], len(expected_dates) - 1)
        snap = self.client.get(self.base + "/snapshot").json()
        self.assertEqual(snap["recurring_series"][0]["status"], "ACTIVE")
        standard = [row for row in snap["sessions"] if row["recurring_series_id"] == series_id and not row["edited_from_series"]]
        self.assertTrue(all(row["status"] == "SCHEDULED" for row in standard))
        self.assertEqual(
            [row["id"] for row in snap["sessions"] if row["edited_from_series"]],
            [edited[0]["id"]],
        )

    def test_workspace_lifecycle_and_makeup(self):
        self.ws_setup()
        student = self.post(
            "/students", {"full_name": "Student", "guardian_name": "Parent"}
        )
        prog = self.new_program()
        self.post(
            "/programs/" + prog["id"] + "/enrollments",
            {"student_id": student["id"], "starts_on": "2020-01-01"},
        )
        original = self.new_session(prog)
        self.post(
            "/sessions/" + original["id"] + "/cancel",
            {"reason": "Teacher unavailable", "grant_makeups": True},
            200,
        )
        snap = self.client.get(self.base + "/snapshot").json()
        self.assertEqual(len(snap["guardians"]), 1)
        self.assertEqual(len(snap["entitlements"]), 1)
        # A separate matching class has no regular enrollment occupying the replacement seat.
        replacement_program = self.new_program("Piano makeup")
        replacement = self.new_session(replacement_program, days=3)
        credit = snap["entitlements"][0]
        booking = self.post(
            "/makeup-entitlements/" + credit["id"] + "/book",
            {"session_id": replacement["id"]},
        )
        self.post(
            "/makeup-entitlements/" + credit["id"] + "/book",
            {"session_id": replacement["id"]},
            409,
        )
        too_late = datetime.now(timezone.utc) + timedelta(days=40)
        moved = self.client.patch(
            self.base + "/sessions/" + replacement["id"],
            headers=self.headers,
            json={
                "starts_at": too_late.isoformat(),
                "ends_at": (too_late + timedelta(hours=1)).isoformat(),
                "delivery_mode": "ONLINE",
                "meeting_url": "https://meet.example.com/piano",
            },
        )
        self.assertEqual(moved.status_code, 409, moved.text)

        self.post(
            "/sessions/" + replacement["id"] + "/cancel",
            {"reason": "Venue unavailable", "grant_makeups": True},
            200,
        )
        again = self.new_session(replacement_program, days=4)
        booking = self.post(
            "/makeup-entitlements/" + credit["id"] + "/book",
            {"session_id": again["id"]},
        )
        from app.auth.database import auth_engine
        from sqlalchemy import text

        with auth_engine().begin() as c:
            c.execute(
                text(
                    "UPDATE classarit.class_sessions SET starts_at=CURRENT_TIMESTAMP-interval '2 hours',ends_at=CURRENT_TIMESTAMP-interval '1 hour' WHERE id=:id"
                ),
                {"id": again["id"]},
            )
        r = self.client.put(
            self.base
            + "/participants/"
            + booking["replacement_participant_id"]
            + "/attendance",
            headers=self.headers,
            json={"status": "PRESENT"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.post("/sessions/" + again["id"] + "/complete", {}, 200)
        snap = self.client.get(self.base + "/snapshot").json()
        self.assertEqual(snap["entitlements"][0]["status"], "FULFILLED")
        self.assertEqual(len(snap["entitlements"]), 1)
        self.assertEqual(
            {b["status"] for b in snap["bookings"]}, {"CANCELLED", "FULFILLED"}
        )

    def test_workspace_capacity_conflicts_and_csrf(self):
        self.ws_setup()
        self.assertEqual(
            self.client.post(
                self.base + "/students", json={"full_name": "No csrf"}
            ).status_code,
            403,
        )
        prog = self.new_program(capacity=1)
        first = self.post("/students", {"full_name": "One"})
        second = self.post("/students", {"full_name": "Two"})
        self.post(
            "/programs/" + prog["id"] + "/enrollments",
            {"student_id": first["id"], "starts_on": "2020-01-01"},
        )
        self.post(
            "/programs/" + prog["id"] + "/enrollments",
            {"student_id": second["id"], "starts_on": "2020-01-01"},
            409,
        )
        ss = self.new_session(prog)
        self.post(
            "/sessions", {"program_id": prog["id"], "starts_at": ss["starts_at"]}, 409
        )
        self.post(
            "/venues",
            {
                "name": "Court",
                "address": "Main street",
                "map_url": "javascript:alert(1)",
            },
            422,
        )
        venue = self.post(
            "/venues",
            {
                "name": "Ground",
                "address": "Main street",
                "space_names": ["Court A", "Court B"],
            },
        )
        event = self.new_program(
            "Soccer",
            program_kind="EVENT",
            default_delivery_mode="IN_PERSON",
            default_venue_id=venue["id"],
        )
        game = self.new_session(event, days=4)
        self.assertIsNone(game["meeting_url"])
        self.post(
            "/sessions/" + game["id"] + "/participants", {"student_id": second["id"]}
        )
        self.assertEqual(self.client.get(self.base + "/snapshot").status_code, 200)

    def test_workspace_invitation_and_tenant_isolation(self):
        self.ws_setup()
        prog = self.new_program()
        self.post("/students", {"full_name": "Private student"})
        invite = self.post(
            "/invitations", {"email": "bob@example.com", "roles": ["TEACHER"]}
        )
        token = invite["url"].rsplit("/", 1)[1]
        other = self.client_type(self.app, base_url="http://127.0.0.1:8000")
        other.__enter__()
        self.addCleanup(other.__exit__, None, None, None)
        bob_csrf = self.login(other, "bob", "bob@example.com")
        headers = {"X-CSRF-Token": bob_csrf}
        self.assertEqual(other.get(self.base + "/snapshot").status_code, 404)
        self.assertEqual(
            self.client.post(
                "/api/invitations/" + token + "/accept", headers=self.headers
            ).status_code,
            403,
        )
        accepted = other.post("/api/invitations/" + token + "/accept", headers=headers)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(
            other.post(
                "/api/invitations/" + token + "/accept", headers=headers
            ).status_code,
            409,
        )
        snap = other.get(self.base + "/snapshot").json()
        self.assertEqual(snap["students"], [])
        self.assertEqual(snap["programs"], [])
        self.assertEqual(
            other.post(
                self.base + "/students", headers=headers, json={"full_name": "Blocked"}
            ).status_code,
            403,
        )
        owner = self.client.get(self.base + "/snapshot").json()["membership_id"]
        r = self.client.patch(
            self.base + "/members/" + owner,
            headers=self.headers,
            json={"roles": ["TEACHER"]},
        )
        self.assertEqual(r.status_code, 200, r.text)
        owner_roles = self.client.get(self.base + "/snapshot").json()["roles"]
        self.assertIn("OWNER", owner_roles)
        self.assertIn("TEACHER", owner_roles)
        workspace2 = self.client.post(
            "/api/workspaces",
            headers=self.headers,
            json={"name": "Second", "workspace_type": "INSTITUTE"},
        ).json()
        r = self.client.post(
            "/api/workspaces/"
            + workspace2["id"]
            + "/programs/"
            + prog["id"]
            + "/enrollments",
            headers=self.headers,
            json={"student_id": str(uuid4()), "starts_on": "2020-01-01"},
        )
        self.assertEqual(r.status_code, 404, r.text)

    def test_workspace_roster_rollback_and_ending_enrollment(self):
        self.ws_setup()
        prog = self.new_program()
        session = self.new_session(prog, capacity=1)
        first = self.post("/students", {"full_name": "First"})
        second = self.post("/students", {"full_name": "Second"})
        enrollment = self.post(
            "/programs/" + prog["id"] + "/enrollments",
            {"student_id": first["id"], "starts_on": "2020-01-01"},
        )
        self.post(
            "/programs/" + prog["id"] + "/enrollments",
            {"student_id": second["id"], "starts_on": "2020-01-01"},
            409,
        )
        snap = self.client.get(self.base + "/snapshot").json()
        self.assertEqual(len(snap["enrollments"]), 1)
        self.assertEqual(len(snap["participants"]), 1)
        self.post("/enrollments/" + enrollment["id"] + "/end", {}, 200)
        self.post(
            "/programs/" + prog["id"] + "/enrollments",
            {"student_id": second["id"], "starts_on": "2020-01-01"},
        )
        snap = self.client.get(self.base + "/snapshot").json()
        self.assertEqual(sum(p["status"] == "BOOKED" for p in snap["participants"]), 1)

    def test_workspace_concurrent_last_seat(self):
        from concurrent.futures import ThreadPoolExecutor

        self.ws_setup()
        prog = self.new_program(program_kind="EVENT", capacity=1)
        session = self.new_session(prog)
        students = [
            self.post("/students", {"full_name": name}) for name in ("One", "Two")
        ]

        def attempt(student):
            return self.client.post(
                self.base + "/sessions/" + session["id"] + "/participants",
                headers=self.headers,
                json={"student_id": student["id"]},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(attempt, students))
        self.assertEqual(sorted(statuses), [201, 409])
        snap = self.client.get(self.base + "/snapshot").json()
        self.assertEqual(len(snap["participants"]), 1)

    def test_workspace_assigned_teacher_attendance_and_suspension(self):
        self.ws_setup()
        invite = self.post(
            "/invitations", {"email": "bob@example.com", "roles": ["TEACHER"]}
        )
        other = self.client_type(self.app, base_url="http://127.0.0.1:8000")
        other.__enter__()
        self.addCleanup(other.__exit__, None, None, None)
        headers = {"X-CSRF-Token": self.login(other, "bob", "bob@example.com")}
        self.assertEqual(
            other.post(
                "/api/invitations/" + invite["url"].rsplit("/", 1)[1] + "/accept",
                headers=headers,
            ).status_code,
            200,
        )
        snap = other.get(self.base + "/snapshot").json()
        bob = snap["membership_id"]
        program = self.new_program(teacher_ids=[bob])
        hidden = self.new_program("Private")
        student = self.post("/students", {"full_name": "Assigned"})
        self.post(
            "/programs/" + program["id"] + "/enrollments",
            {"student_id": student["id"], "starts_on": "2020-01-01"},
        )
        session = self.new_session(program)
        snap = other.get(self.base + "/snapshot").json()
        self.assertEqual([p["id"] for p in snap["programs"]], [program["id"]])
        self.assertEqual([st["id"] for st in snap["students"]], [student["id"]])
        from app.auth.database import auth_engine
        from sqlalchemy import text

        with auth_engine().begin() as c:
            c.execute(
                text(
                    "UPDATE classarit.class_sessions SET starts_at=CURRENT_TIMESTAMP-interval '2 hours',ends_at=CURRENT_TIMESTAMP-interval '1 hour' WHERE id=:id"
                ),
                {"id": session["id"]},
            )
        participant = snap["participants"][0]["id"]
        r = other.put(
            self.base + "/participants/" + participant + "/attendance",
            headers=headers,
            json={"status": "PRESENT"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.patch(
            self.base + "/members/" + bob,
            headers=self.headers,
            json={"roles": ["TEACHER"], "status": "SUSPENDED"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(other.get(self.base + "/snapshot").status_code, 404)


    def test_signed_out_invitation_returns_after_google_login(self):
        self.ws_setup()
        invitation = self.post('/invitations', {'email': 'bob@example.com', 'roles': ['TEACHER']})
        invitation_path = '/invitations/' + invitation['url'].rsplit('/', 1)[1]
        other = self.client_type(self.app, base_url='http://127.0.0.1:8000')
        other.__enter__()
        self.addCleanup(other.__exit__, None, None, None)
        response = other.get(invitation_path, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/login')
        self.assertIn('Log in to accept your invitation', other.get('/login').text)
        csrf = self.login(other, 'bob', 'bob@example.com')
        response = other.get('/dashboard', follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], invitation_path)
        self.assertIn('Accept invitation', other.get(invitation_path).text)
        response = other.post('/api' + invitation_path + '/accept', headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 200, response.text)
        dashboard = other.get('/dashboard', follow_redirects=False)
        self.assertEqual(dashboard.status_code, 303)
        self.assertEqual(dashboard.headers['location'], '/workspaces/' + self.w)
        self.assertEqual(other.get('/dashboard?overview=1', follow_redirects=False).status_code, 200)
