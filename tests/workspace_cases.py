"""Behavioral cases run against LoginTests' isolated PostgreSQL fixture."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4


class WorkspaceCases:
    def ws_setup(self):
        csrf = self.login()
        self.headers = {"X-CSRF-Token": csrf}
        r = self.client.post(
            "/api/workspaces",
            headers=self.headers,
            json={"name": "Music studio", "workspace_type": "INDIVIDUAL"},
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
        self.assertEqual(r.status_code, 409, r.text)
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
        self.assertEqual(other.get('/dashboard', follow_redirects=False).status_code, 200)
