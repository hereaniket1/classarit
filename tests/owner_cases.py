"""Account overview, one subscription owner and exclusive APPOWNER tests."""

from datetime import datetime, timedelta, timezone


class OwnerCases:
    def another_user(self, subject="bob"):
        client = self.client_type(self.app, base_url="http://127.0.0.1:8000")
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        csrf = self.login(client, subject, subject + "@example.com")
        return client, {"X-CSRF-Token": csrf}

    def test_owner_dashboard_ranking_and_explicit_navigation(self):
        self.ws_setup()
        one = self.post("/students", {"full_name": "One"})
        two = self.post("/students", {"full_name": "Two"})
        piano = self.new_program("Piano")
        singing = self.new_program("Singing")
        for student in [one, two]:
            self.post(
                "/programs/" + piano["id"] + "/enrollments",
                {"student_id": student["id"], "starts_on": "2020-01-01"},
            )
        self.post(
            "/programs/" + singing["id"] + "/enrollments",
            {"student_id": one["id"], "starts_on": "2020-01-01"},
        )
        session = self.new_session(singing)
        from app.auth.database import auth_engine
        from sqlalchemy import text

        with auth_engine().begin() as c:
            c.execute(
                text(
                    "UPDATE classarit.class_sessions SET starts_at=CURRENT_TIMESTAMP-interval '2 days',ends_at=CURRENT_TIMESTAMP-interval '47 hours',status='COMPLETED' WHERE id=:s"
                ),
                {"s": session["id"]},
            )
        second = self.client.post(
            "/api/workspaces",
            headers=self.headers,
            json={"name": "Second business", "workspace_type": "INSTITUTE"},
        ).json()
        self.client.get("/dashboard?workspace=" + self.w)
        default_redirect = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(default_redirect.status_code, 303, default_redirect.text)
        self.assertEqual(default_redirect.headers["location"], "/workspaces/" + self.w)
        page = self.client.get("/dashboard?overview=1", follow_redirects=False)
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn("Overview", page.text)
        self.assertIn("Second business", page.text)
        self.assertIn("Manage workspace", page.text)
        self.assertIn("Default", page.text)
        self.assertIn("Make default", page.text)
        self.assertNotIn('id="workspace-content"', page.text)
        changed_default = self.client.post(
            "/api/account/default-workspace",
            headers=self.headers,
            json={"workspace_id": second["id"]},
        )
        self.assertEqual(changed_default.status_code, 200, changed_default.text)
        default_redirect = self.client.get("/dashboard", follow_redirects=False)
        self.assertEqual(default_redirect.status_code, 303, default_redirect.text)
        self.assertEqual(default_redirect.headers["location"], "/workspaces/" + second["id"])
        self.assertEqual(
            self.client.post(
                "/api/account/default-workspace",
                headers=self.headers,
                json={"workspace_id": "00000000-0000-0000-0000-000000000000"},
            ).status_code,
            404,
        )
        info = self.client.get("/api/dashboard/overview").json()
        self.assertEqual(info["totals"]["workspaces"], 2)
        self.assertEqual(info["totals"]["students"], 2)
        card = next(w for w in info["owned_workspaces"] if w["id"] == self.w)
        self.assertEqual(card["popular"][0]["id"], piano["id"])
        self.assertEqual(card["popular"][0]["students"], 2)
        self.assertEqual(card["most_used"][0]["id"], singing["id"])
        detail = self.client.get("/workspaces/" + self.w)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertIn("Switch workspace", detail.text)
        self.assertIn('aria-label="Open main dashboard"', detail.text)
        self.assertEqual(
            self.client.get(
                "/dashboard?workspace=invalid", follow_redirects=False
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/workspaces/" + second["id"]).status_code, 200
        )

    def test_teacher_overview_has_only_assignments(self):
        self.ws_setup()
        invite = self.post(
            "/invitations", {"email": "bob@example.com", "roles": ["TEACHER"]}
        )
        other, headers = self.another_user()
        self.assertEqual(
            other.post(
                "/api/invitations/" + invite["url"].rsplit("/", 1)[1] + "/accept",
                headers=headers,
            ).status_code,
            200,
        )
        mid = other.get(self.base + "/snapshot").json()["membership_id"]
        self.new_program("Visible piano", teacher_ids=[mid])
        self.new_program("Hidden company class")
        self.post("/venues", {"name": "Private office", "address": "Private road"})
        redirect = other.get("/dashboard", follow_redirects=False)
        self.assertEqual(redirect.status_code, 303)
        self.assertEqual(redirect.headers["location"], "/workspaces/" + self.w)
        page = other.get("/dashboard?overview=1")
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn("Visible piano", page.text)
        self.assertNotIn("Hidden company class", page.text)
        self.assertNotIn("Classes attracting", page.text)
        self.assertNotIn("Create workspace", page.text)
        data = other.get("/api/dashboard/overview").json()
        self.assertEqual(data["owned_workspaces"], [])
        self.assertEqual(data["totals"]["students"], 0)
        detail = other.get("/workspaces/" + self.w).text
        for forbidden in [
            'data-tab="team"',
            'data-tab="venues"',
            'data-tab="makeups"',
            'data-tab="calendar"',
            'data-tab="reporting"',
        ]:
            self.assertNotIn(forbidden, detail)
        snapshot = other.get(self.base + "/snapshot").json()
        self.assertEqual(snapshot["venues"], [])
        self.assertIsNone(snapshot["policy"])
        self.assertEqual(other.get("/legacy/dashboard").status_code, 404)
        self.assertEqual(other.get("/workspaces/new").status_code, 403)
        self.assertEqual(
            other.post(
                "/api/workspaces",
                headers=headers,
                json={"name": "Forbidden", "workspace_type": "INDIVIDUAL"},
            ).status_code,
            409,
        )
        foreign, foreign_headers = self.another_user("charlie")
        self.assertEqual(foreign.get("/workspaces/" + self.w).status_code, 404)

    def test_workspace_type_controls_staff_roles(self):
        self.ws_setup()
        self.assertEqual(
            self.client.post(
                self.base + "/invitations",
                headers=self.headers,
                json={"email": "admin@example.com", "roles": ["ADMIN"]},
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                self.base + "/invitations",
                headers=self.headers,
                json={"email": "ops@example.com", "roles": ["OPERATOR"]},
            ).status_code,
            422,
        )
        owner_member = self.client.get(self.base + "/snapshot").json()["membership_id"]
        self.assertEqual(
            self.client.patch(
                self.base + "/members/" + owner_member,
                headers=self.headers,
                json={"roles": [], "status": "ACTIVE"},
            ).status_code,
            409,
        )
        invite = self.post(
            "/invitations", {"email": "bob@example.com", "roles": ["TEACHER"]}
        )
        other, headers = self.another_user()
        self.assertEqual(
            other.post(
                "/api/invitations/" + invite["url"].rsplit("/", 1)[1] + "/accept",
                headers=headers,
            ).status_code,
            200,
        )
        teacher_member = other.get(self.base + "/snapshot").json()["membership_id"]
        self.assertEqual(
            self.client.patch(
                self.base + "/members/" + teacher_member,
                headers=self.headers,
                json={"roles": ["OPERATOR"], "status": "ACTIVE"},
            ).status_code,
            422,
        )

        institute = self.client.post(
            "/api/workspaces",
            headers=self.headers,
            json={"name": "Institute", "workspace_type": "INSTITUTE"},
        ).json()
        institute_base = "/api/workspaces/" + institute["id"]
        self.assertEqual(
            self.client.post(
                institute_base + "/invitations",
                headers=self.headers,
                json={
                    "email": "admin@example.com",
                    "roles": ["ADMIN", "OPERATOR", "TEACHER"],
                },
            ).status_code,
            201,
        )
        operator_invite = self.client.post(
            institute_base + "/invitations",
            headers=self.headers,
            json={"email": "operator@example.com", "roles": ["OPERATOR"]},
        ).json()
        operator, operator_headers = self.another_user("operator")
        self.assertEqual(
            operator.post(
                "/api/invitations/"
                + operator_invite["url"].rsplit("/", 1)[1]
                + "/accept",
                headers=operator_headers,
            ).status_code,
            200,
        )
        institute_snapshot = self.client.get(institute_base + "/snapshot").json()
        owner_teacher = institute_snapshot["membership_id"]
        self.assertEqual(
            operator.post(
                institute_base + "/students",
                headers=operator_headers,
                json={"full_name": "Operator student"},
            ).status_code,
            201,
        )
        program = operator.post(
            institute_base + "/programs",
            headers=operator_headers,
            json={
                "name": "Operator class",
                "activity_name": "Maths",
                "default_meeting_url": "https://meet.example.com/operator",
                "teacher_ids": [owner_teacher],
            },
        )
        self.assertEqual(program.status_code, 201, program.text)
        self.assertEqual(
            operator.post(
                institute_base + "/invitations",
                headers=operator_headers,
                json={"email": "blocked@example.com", "roles": ["TEACHER"]},
            ).status_code,
            403,
        )
        self.assertEqual(
            operator.put(
                institute_base + "/makeup-policy",
                headers=operator_headers,
                json={
                    "teacher_cancellation_eligible": True,
                    "student_absence_eligible": False,
                    "minimum_notice_hours": 0,
                    "validity_days": 30,
                    "included_in_original_fee": True,
                },
            ).status_code,
            403,
        )


    def test_active_staff_must_be_deactivated_before_becoming_owner(self):
        self.ws_setup("INSTITUTE")
        invite = self.post(
            "/invitations", {"email": "bob@example.com", "roles": ["ADMIN"]}
        )
        other, headers = self.another_user()
        self.assertEqual(
            other.post(
                "/api/invitations/" + invite["url"].rsplit("/", 1)[1] + "/accept",
                headers=headers,
            ).status_code,
            200,
        )
        bob_membership = other.get(self.base + "/snapshot").json()["membership_id"]
        active_attempt = other.post(
            "/api/workspaces",
            headers=headers,
            json={"name": "Bob studio", "workspace_type": "INDIVIDUAL"},
        )
        self.assertEqual(active_attempt.status_code, 409, active_attempt.text)
        suspended = self.client.patch(
            self.base + "/members/" + bob_membership,
            headers=self.headers,
            json={"roles": ["ADMIN"], "status": "SUSPENDED"},
        )
        self.assertEqual(suspended.status_code, 200, suspended.text)
        created = other.post(
            "/api/workspaces",
            headers=headers,
            json={"name": "Bob studio", "workspace_type": "INDIVIDUAL"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(
            self.client.post(
                self.base + "/invitations",
                headers=self.headers,
                json={"email": "bob@example.com", "roles": ["TEACHER"]},
            ).status_code,
            409,
        )
        from app.auth.database import auth_engine
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        with self.assertRaises(IntegrityError):
            with auth_engine().begin() as c:
                c.execute(
                    text(
                        "UPDATE classarit.workspace_memberships SET status='ACTIVE' WHERE id=:m"
                    ),
                    {"m": bob_membership},
                )

    def test_single_subscription_owner_in_api_and_database(self):
        self.ws_setup("INSTITUTE")
        invite = self.post(
            "/invitations", {"email": "bob@example.com", "roles": ["ADMIN"]}
        )
        other, headers = self.another_user()
        other.post(
            "/api/invitations/" + invite["url"].rsplit("/", 1)[1] + "/accept",
            headers=headers,
        )
        mid = other.get(self.base + "/snapshot").json()["membership_id"]
        changed = self.client.patch(
            self.base + "/members/" + mid,
            headers=self.headers,
            json={"roles": ["OWNER", "ADMIN"]},
        )
        self.assertEqual(changed.status_code, 422, changed.text)
        from app.auth.database import auth_engine
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        with self.assertRaises(IntegrityError):
            with auth_engine().begin() as c:
                c.execute(
                    text(
                        "INSERT INTO classarit.membership_roles(workspace_id,membership_id,role) VALUES (:w,:m,'OWNER')"
                    ),
                    {"w": self.w, "m": mid},
                )
        with self.assertRaises(IntegrityError):
            with auth_engine().begin() as c:
                c.execute(
                    text(
                        "DELETE FROM classarit.membership_roles WHERE workspace_id=:w AND role='OWNER'"
                    ),
                    {"w": self.w},
                )
        with self.assertRaises(IntegrityError):
            with auth_engine().begin() as c:
                c.execute(
                    text(
                        "UPDATE classarit.app_users SET user_type='APPOWNER' WHERE id=(SELECT owner_user_id FROM classarit.workspaces WHERE id=:w)"
                    ),
                    {"w": self.w},
                )

    def test_appowner_is_exclusive_and_has_no_business_access(self):
        self.ws_setup()
        invite = self.post(
            "/invitations", {"email": "bob@example.com", "roles": ["TEACHER"]}
        )
        other, headers = self.another_user()
        from app.auth.database import auth_engine
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        with auth_engine().begin() as c:
            uid = c.execute(
                text(
                    "SELECT app_user_id FROM classarit.user_emails WHERE email='bob@example.com'"
                )
            ).scalar_one()
            c.execute(
                text("UPDATE classarit.app_users SET user_type='APPOWNER' WHERE id=:u"),
                {"u": uid},
            )
        page = other.get("/dashboard")
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn("Product performance", page.text)
        self.assertIn("Coming later", page.text)
        self.assertNotIn("Manage workspace", page.text)
        for route in [
            "/api/workspaces",
            "/api/dashboard/overview",
            self.base + "/snapshot",
            "/api/students",
            "/workspaces/new",
        ]:
            self.assertEqual(other.get(route).status_code, 403, route)
        self.assertEqual(
            other.post(
                "/api/invitations/" + invite["url"].rsplit("/", 1)[1] + "/accept",
                headers=headers,
            ).status_code,
            403,
        )
        with self.assertRaises(IntegrityError):
            with auth_engine().begin() as c:
                c.execute(
                    text(
                        "INSERT INTO classarit.workspace_memberships(workspace_id,user_id) VALUES (:w,:u)"
                    ),
                    {"w": self.w, "u": uid},
                )
        with self.assertRaises(IntegrityError):
            with auth_engine().begin() as c:
                c.execute(
                    text(
                        "UPDATE classarit.app_users SET user_type='MEMBER' WHERE id=:u"
                    ),
                    {"u": uid},
                )

    def test_old_workspace_creation_remains_compatible_during_rollout(self):
        csrf = self.login()
        from app.auth.database import auth_engine
        from sqlalchemy import text

        with auth_engine().begin() as c:
            uid = c.execute(
                text(
                    "SELECT app_user_id FROM classarit.user_emails WHERE email='alice@example.com'"
                )
            ).scalar_one()
            wid = c.execute(
                text(
                    "INSERT INTO classarit.workspaces(name,workspace_type,created_by) VALUES ('Old code','INDIVIDUAL',:u) RETURNING id"
                ),
                {"u": uid},
            ).scalar_one()
            mid = c.execute(
                text(
                    "INSERT INTO classarit.workspace_memberships(workspace_id,user_id) VALUES (:w,:u) RETURNING id"
                ),
                {"w": wid, "u": uid},
            ).scalar_one()
            c.execute(
                text(
                    "INSERT INTO classarit.membership_roles(workspace_id,membership_id,role) VALUES (:w,:m,'OWNER')"
                ),
                {"w": wid, "m": mid},
            )
            c.execute(
                text(
                    "INSERT INTO classarit.membership_roles(workspace_id,membership_id,role) VALUES (:w,:m,'TEACHER')"
                ),
                {"w": wid, "m": mid},
            )
        self.assertIn("Overview", self.client.get("/dashboard?overview=1").text)

    def test_active_teachers_count_unique_people_across_owned_workspaces(self):
        self.ws_setup()
        first=self.w
        second=self.client.post('/api/workspaces',headers=self.headers,json={'name':'Second','workspace_type':'INSTITUTE'}).json()['id']
        other,headers=self.another_user()
        memberships=[]
        for wid in [first,second]:
            invitation=self.client.post('/api/workspaces/'+wid+'/invitations',headers=self.headers,json={'email':'bob@example.com','roles':['TEACHER']}).json()
            response=other.post('/api/invitations/'+invitation['url'].rsplit('/',1)[1]+'/accept',headers=headers)
            self.assertEqual(response.status_code,200,response.text)
            memberships.append(other.get('/api/workspaces/'+wid+'/snapshot').json()['membership_id'])
        data=self.client.get('/api/dashboard/overview').json()
        self.assertEqual(data['totals']['active_teachers'],2)  # Owner and Bob, each once.
        self.assertEqual([w['teacher_count'] for w in data['owned_workspaces']],[2,2])
        self.client.patch('/api/workspaces/'+first+'/members/'+memberships[0],headers=self.headers,json={'roles':['TEACHER'],'status':'SUSPENDED'})
        self.assertEqual(self.client.get('/api/dashboard/overview').json()['totals']['active_teachers'],2)
        from app.auth.database import auth_engine
        from sqlalchemy import text
        with auth_engine().begin() as c:
            c.execute(text("UPDATE classarit.app_users SET status='BLOCKED' WHERE id=(SELECT app_user_id FROM classarit.user_emails WHERE email='bob@example.com')"))
        data=self.client.get('/api/dashboard/overview').json()
        self.assertEqual(data['totals']['active_teachers'],1)
        self.assertEqual([w['teacher_count'] for w in data['owned_workspaces']],[1,1])
        page=self.client.get('/dashboard?overview=1').text
        self.assertNotIn('My workspaces',page)
        self.assertNotIn('YOUR BUSINESS AT A GLANCE',page)
        self.assertNotIn('Upcoming sessions',page)
        self.assertEqual(page.count('class="icon-button manage-workspace"'),2)
        sidebar=page.split('<aside',1)[1].split('</aside>',1)[0]
        self.assertNotIn('Create workspace',sidebar)
