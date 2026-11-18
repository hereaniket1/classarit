import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4
from datetime import date, datetime, timezone
from fastapi import HTTPException

from app.routes import student
from app.routes.student import PlannerTaskInput
from app.auth import repository
from app.services import admissions
from app.routes.admissions import InterestInput
from app.workspaces.access import access
from app.workspaces.services import organizations, catalog
from app.workspaces.routes.teaching import class_student, ClassStudentInput, discovery, DiscoveryInput


class StudentPortalTests(unittest.TestCase):
    def setUp(self):
        self.user={'id':uuid4(),'account_type':'STUDENT','email_verified':True,
                   'email':'student@example.com','full_name':'Student','user_type':'MEMBER'}
        self.workspace={'id':uuid4(),'timezone':'Asia/Kolkata'}
        self.program={'id':uuid4(),'status':'ACTIVE','program_kind':'COURSE','student_discoverable':True,'capacity':1}
        self.record={'id':uuid4(),'status':'ACTIVE'}
        self.db=MagicMock()
        self.db.get.return_value=self.program

    def test_student_admission_and_approved_type(self):
        self.assertEqual(repository.resolve_account_type('STUDENT','STUDENT'),'STUDENT')
        InterestInput(full_name='Student',email='student@example.com',country='IN',usage_type='STUDENT')
        with self.assertRaises(repository.AccountUnavailable):
            repository.resolve_account_type('ORGANIZATION','STUDENT')
        conn=MagicMock()
        conn.execute.return_value.mappings.return_value.first.return_value={'usage_type':'STUDENT'}
        with patch.object(admissions,'setting_enabled',return_value=True):
            self.assertEqual(admissions.admission_type(conn,'student@example.com'),'STUDENT')
        conn.execute.return_value.mappings.return_value.first.return_value=None
        with patch.object(admissions,'setting_enabled',return_value=True), self.assertRaises(repository.AccountUnavailable):
            admissions.admission_type(conn,'student@example.com')
        with patch.object(admissions,'setting_enabled',return_value=False):
            self.assertIsNone(admissions.admission_type(conn,'student@example.com'))

    def test_student_cannot_create_or_access_workspace_or_accept_staff_invite(self):
        for call in [lambda:organizations.create_workspace(self.db,self.user,None),
                     lambda:access(self.workspace['id'],SimpleNamespace(method='POST'),self.db,self.user),
                     lambda:organizations.accept_invite(self.db,self.user,'staff-token')]:
            with self.assertRaises(HTTPException) as error: call()
            self.assertEqual(error.exception.status_code,403)
        self.db.execute.assert_not_called()

    def test_non_student_cannot_use_student_api(self):
        with self.assertRaises(HTTPException): student.require_student({'account_type':'INDIVIDUAL'})

    def test_unverified_cannot_enroll(self):
        with self.assertRaises(HTTPException):
            student.self_enroll(self.program['id'],{**self.user,'email_verified':False},self.db)
        self.db.first.assert_not_called()

    def test_student_can_verify_when_optional_verification_is_disabled(self):
        conn=MagicMock()
        row={**self.user,'verified_at':None}
        conn.execute.return_value.mappings.return_value.first.return_value=row
        engine=MagicMock();engine.begin.return_value.__enter__.return_value=conn
        with patch.object(repository,'setting_enabled',return_value=False), patch.object(repository,'auth_engine',return_value=engine), patch.object(repository,'_new_challenge',return_value={'challenge_id':'otp'}):
            self.assertEqual(repository.start_email_verification(self.user['id'])['challenge_id'],'otp')
            row['account_type']='INDIVIDUAL'
            with self.assertRaises(repository.AccountUnavailable):
                repository.start_email_verification(self.user['id'])

    def test_private_inactive_and_event_cannot_enroll(self):
        self.db.first.return_value=self.workspace
        for changes in [{'student_discoverable':False},{'status':'ARCHIVED'},{'program_kind':'EVENT'}]:
            self.db.get.return_value={**self.program,**changes}
            with self.assertRaises(HTTPException) as error:
                student.self_enroll(self.program['id'],self.user,self.db)
            self.assertEqual(error.exception.status_code,404)
        self.db.insert.assert_not_called()

    def test_duplicate_enrollment_is_idempotent(self):
        self.db.first.side_effect=[self.workspace,self.record,{'id':'already','status':'ACTIVE'}]
        result=student.self_enroll(self.program['id'],self.user,self.db)
        self.assertTrue(result['already_enrolled'])
        self.db.insert.assert_not_called()

    def test_enrollment_uses_authenticated_identity_and_shared_rules(self):
        self.db.first.side_effect=[self.workspace,None,None]
        self.db.insert.return_value=self.record
        with patch.object(student,'enroll_student',return_value={'id':'enrolled'}) as enroll:
            student.self_enroll(self.program['id'],self.user,self.db)
        self.assertEqual(self.db.insert.call_args.kwargs['linked_user_id'],self.user['id'])
        self.assertEqual(enroll.call_args.args[2].student_id,self.record['id'])
        self.assertFalse(hasattr(enroll.call_args.args[0],'roles'))
        self.assertIn('FOR UPDATE OF w',self.db.first.call_args_list[0].args[0])

    def test_shared_capacity_check(self):
        a=SimpleNamespace(db=self.db,id=self.workspace['id'],workspace=self.workspace)
        self.db.get.return_value=self.record
        self.db.first.return_value={'n':1}
        with self.assertRaises(HTTPException) as error:
            catalog.enroll_student(a,self.program,SimpleNamespace(student_id=self.record['id'],starts_on=date.today(),ends_on=None))
        self.assertEqual(error.exception.status_code,409)
        self.db.insert.assert_not_called()

    def test_upcoming_is_scoped_to_linked_student(self):
        self.db.all.return_value=[]
        student.upcoming(self.user,self.db)
        for call in self.db.all.call_args_list:
            self.assertTrue('st.linked_user_id=:u' in call.args[0] or 'student_user_id=:u' in call.args[0])
            self.assertEqual(call.kwargs['u'],self.user['id'])

    def test_calendar_uses_local_month_boundaries_and_scopes_overlapping_items(self):
        self.db.all.return_value = []
        student.calendar_month('2026-11', self.user, self.db, tz='America/New_York')
        sessions, tasks = self.db.all.call_args_list
        for query in (sessions, tasks):
            self.assertEqual(query.kwargs['u'], self.user['id'])
            self.assertEqual(query.kwargs['start'], datetime(2026, 11, 1, 4, tzinfo=timezone.utc))
            self.assertEqual(query.kwargs['end'], datetime(2026, 12, 1, 5, tzinfo=timezone.utc))
            self.assertIn('ends_at>:start', query.args[0])
            self.assertIn('starts_at<:end', query.args[0])
        self.assertIn("st.linked_user_id=:u AND sp.status='BOOKED'", sessions.args[0])
        self.assertIn("cs.status IN ('SCHEDULED','COMPLETED')", sessions.args[0])
        self.assertIn('student_user_id=:u', tasks.args[0])

    def test_calendar_rejects_invalid_month_or_timezone(self):
        for month, tz in [('2026-13', 'Asia/Kolkata'), ('2026-11', 'Not/AZone')]:
            with self.assertRaises(HTTPException) as error:
                student.calendar_month(month, self.user, self.db, tz=tz)
            self.assertEqual(error.exception.status_code, 422)
        self.db.all.assert_not_called()

    def test_planner_task_is_personal_and_defaults_to_one_hour(self):
        self.db.insert.return_value={'id':'task-1'}
        payload=PlannerTaskInput(title='School',starts_at=datetime(2026,11,20,9),timezone='Asia/Kolkata')
        result=student.create_planner_task(payload,self.user,self.db)
        self.assertEqual(result['id'],'task-1')
        self.assertEqual(self.db.insert.call_args.kwargs['student_user_id'],self.user['id'])
        self.assertEqual((self.db.insert.call_args.kwargs['ends_at']-self.db.insert.call_args.kwargs['starts_at']).total_seconds(),3600)

    def test_planner_task_rejects_invalid_timezone_and_range(self):
        with self.assertRaises(HTTPException):
            student.create_planner_task(PlannerTaskInput(title='School',starts_at=datetime(2026,11,20,9),timezone='Not/AZone'),self.user,self.db)
        with self.assertRaises(HTTPException):
            student.create_planner_task(PlannerTaskInput(title='School',starts_at=datetime(2026,11,20,10),ends_at=datetime(2026,11,20,9),timezone='Asia/Kolkata'),self.user,self.db)
        self.db.insert.assert_not_called()

    def test_planner_weekdays_use_shared_recurrence_and_batch_insert(self):
        payload = PlannerTaskInput(
            title='Study', starts_at=datetime(2026, 11, 23, 17, 30),
            timezone='Asia/Kolkata', duration_minutes=45, repeat='WEEKLY',
            repeat_weekdays=['MON', 'THU'], repeat_months=1)
        result = student.create_planner_task(payload, self.user, self.db)
        table, rows = self.db.insert_many.call_args.args
        self.assertEqual(table, 'student_planner_tasks')
        self.assertEqual(len(rows), 9)
        self.assertEqual(result['count'], len(rows))
        self.assertEqual(rows[0]['starts_at'], datetime(2026, 11, 23, 12, tzinfo=timezone.utc))
        self.assertEqual(rows[-1]['starts_at'].date(), date(2026, 12, 21))
        self.assertTrue(all(row['starts_at'].weekday() in (0, 3) for row in rows))
        self.assertTrue(all(row['student_user_id'] == self.user['id'] for row in rows))
        self.assertTrue(all((row['ends_at'] - row['starts_at']).total_seconds() == 2700 for row in rows))
        self.db.insert.assert_not_called()

    def test_planner_repeats_keep_local_time_across_dst(self):
        payload = PlannerTaskInput(
            title='Study', starts_at=datetime(2026, 10, 26, 9),
            timezone='America/New_York', repeat='WEEKLY',
            repeat_weekdays=['MON'], repeat_months=1)
        student.create_planner_task(payload, self.user, self.db)
        rows = self.db.insert_many.call_args.args[1]
        self.assertEqual(rows[0]['starts_at'].hour, 13)
        self.assertEqual(rows[1]['starts_at'].hour, 14)

    def test_planner_rejects_missing_repeat_days_before_insert(self):
        payload = PlannerTaskInput(title='Study', starts_at=datetime(2026, 11, 23, 9),
                                   repeat='WEEKLY', repeat_months=3)
        with self.assertRaises(HTTPException):
            student.create_planner_task(payload, self.user, self.db)
        self.db.insert.assert_not_called()
        self.db.insert_many.assert_not_called()

    def test_delete_planner_task_is_owner_scoped(self):
        self.db.first.return_value=None
        with self.assertRaises(HTTPException) as error:
            student.delete_planner_task(uuid4(),self.user,self.db)
        self.assertEqual(error.exception.status_code,404)
        self.assertEqual(self.db.first.call_args.kwargs['u'],self.user['id'])

    def test_search_is_paginated_and_hides_meeting_links(self):
        self.db.all.return_value=[{'id':str(i)} for i in range(21)]
        result=student.search_classes('math','Pune','IN_PERSON',0,self.user,self.db)
        self.assertEqual(len(result['classes']),20)
        self.assertTrue(result['has_more'])
        query=self.db.all.call_args.args[0]
        self.assertNotIn('meeting_url',query)
        self.assertIn('p.student_discoverable',query)
        self.assertEqual(self.db.all.call_args.kwargs['place'],'%Pune%')

    def test_teacher_must_have_assigned_class(self):
        a=MagicMock();a.program.side_effect=HTTPException(403,'Not assigned')
        with self.assertRaises(HTTPException):
            class_student(self.program['id'],ClassStudentInput(full_name='Student',email='student@example.com',starts_on=date.today()),a)
        with self.assertRaises(HTTPException):
            discovery(self.program['id'],DiscoveryInput(student_discoverable=True),a)
        a.db.insert.assert_not_called();a.db.execute.assert_not_called()


if __name__=='__main__': unittest.main()
